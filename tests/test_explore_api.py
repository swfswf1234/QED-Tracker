"""探索 API 契约测试（QED-040/041）。

覆盖冻结契约关键行为：running 幂等去重（deduplicated）、容量与锁定三态、
adopt 单事务原子性、proposal_id 严格匹配、错误结构 {detail:{code,message}}。
零公网：advisor 经 monkeypatch 替换为固定响应 fake；DB 为 SQLite 注入。
"""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.api.main import create_app
from qed_tracker.config import load_settings
from qed_tracker.db.exploration_repository import ExplorationRepository, new_run_id
from qed_tracker.db.knowledge_repository import KnowledgeRepository
from qed_tracker.db.models import Base, ExploreRunStatus, QedCourse, QedDomain, QtExploreRun, QtKnowledge

# fake advisor 的放行闸：deduplicated 测试需要首个 run 停在 running 态。
GATE = threading.Event()

_FAKE_PROPOSALS = [
    {
        "proposal_id": "pp_000000000001",
        "set_name": "套一",
        "set_no": "1",
        "textbook": {"title": "Principles of Mathematical Analysis", "authors": ["Walter Rudin"],
                     "version": {"edition": "中译本", "publisher": "机械工业出版社", "year": 2004},
                     "intro": "深入研究向经典。"},
        "exercise": None,
        "reason": "顶尖名校指定",
    },
    {
        "proposal_id": "pp_000000000002",
        "set_name": "套二",
        "set_no": "",
        "textbook": {"title": "Understanding Analysis", "authors": ["Stephen Abbott"],
                     "version": {"edition": "中译本", "publisher": "人民邮电出版社", "year": 2015},
                     "intro": "初学者友好。"},
        "exercise": {"title": "吉米多维奇数学分析习题集", "authors": ["吉米多维奇"],
                     "version": {"edition": "", "publisher": "", "year": None}, "intro": "全知识点题集。"},
        "reason": "入门配套",
    },
]


class FakeCourseAdvisor:
    def __init__(self, **kwargs):
        pass

    def propose(self, course, *, mode, ref_text="", ref_doc_path=""):
        GATE.wait(timeout=5)
        return [dict(p) for p in _FAKE_PROPOSALS]

    def close(self):
        pass

    def metadata(self):
        return {"model": "fake", "calls": 1}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """SQLite 双 repo 注入 + fake advisor patch；返回 (client, kn_repo, er_repo)。"""
    from qed_tracker.providers import explore_advisor

    engine = create_engine(f"sqlite:///{tmp_path / 'explore.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    from qed_tracker.database import utc_now

    now = utc_now()
    session.add(QedDomain(domain_id="math", name="数学", description="", stages=["本科基础"],
                          created_at=now, updated_at=now))
    session.add(QedCourse(course_id="01_math_analysis", domain_id="math", sort_order=1, name="数学分析",
                          aliases=[], stage="本科基础", prerequisites=[], related_targets=[],
                          created_at=now, updated_at=now))
    session.commit()
    kn_repo = KnowledgeRepository(lambda: factory())
    er_repo = ExplorationRepository(lambda: factory())

    monkeypatch.setattr(explore_advisor, "CourseExploreAdvisor", FakeCourseAdvisor)
    monkeypatch.setattr(explore_advisor, "CurriculumExploreAdvisor", FakeCurriculumAdvisor)
    settings = load_settings(data_root=tmp_path)
    app = create_app(settings, knowledge_repository=kn_repo, advisor=_DummyAdvisor())
    with TestClient(app) as test_client:
        yield test_client, kn_repo, er_repo
    GATE.set()
    engine.dispose()


class FakeCurriculumAdvisor:
    def __init__(self, **kwargs):
        pass

    def propose(self, domain_name, *, mode, ref_text="", ref_doc_path=""):
        GATE.wait(timeout=5)
        return []

    def close(self):
        pass

    def metadata(self):
        return {"model": "fake", "calls": 1}


class _DummyAdvisor:
    """仅满足 Application.close() 的 advisor.close() 调用。"""

    def close(self):
        pass


def _seed_knowledge(kn_repo, *, set_no: str, status: str) -> str:
    row = kn_repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                   kind="tutorial", set_no=set_no, name=f"教程{set_no}：书{set_no}")
    if status in ("confirmed", "completed"):
        row = kn_repo.confirm_knowledge(row.knowledge_id, textbook_ref={}, exercise_ref={})
    if status == "completed":
        # complete_knowledge 要求已验证书行；夹具只关心计数口径，直接落状态
        with kn_repo.session_factory() as session:
            target = session.get(QtKnowledge, row.knowledge_id)
            target.status = "completed"
            session.commit()
    return row.knowledge_id


def _wait_ready(client, run_id: str) -> dict:
    import time

    for _ in range(50):
        body = client.get(f"/api/v1/explore-runs/{run_id}").json()
        if body.get("status") != "running":
            return body
        time.sleep(0.02)
    raise AssertionError("run 未在限时内离开 running 态")


# ---------------- 注入链冒烟 ----------------

def test_explore_run_detail_missing_returns_structured_404(env):
    client, _, _ = env
    resp = client.get("/api/v1/explore-runs/exp_does_not_exist")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "RUN_NOT_FOUND"


# ---------------- 幂等去重（契约 §1/§6） ----------------

def test_course_explore_running_hit_returns_existing_with_flag(env):
    client, _, _ = env
    GATE.clear()  # 首个 run 卡在 running
    first = client.post("/api/v1/courses/01_math_analysis/explore", json={"mode": "direct"})
    assert first.status_code == 202
    second = client.post("/api/v1/courses/01_math_analysis/explore", json={"mode": "direct"})
    assert second.status_code == 202
    body = second.json()
    assert body["deduplicated"] is True
    assert body["run_id"] == first.json()["run_id"]
    assert body["task_id"] == first.json()["task_id"]
    GATE.set()


def test_curriculum_explore_running_hit_returns_existing_with_flag(env):
    client, _, _ = env
    GATE.clear()
    first = client.post("/api/v1/curriculum-explore", json={"domain_name": "高等数学", "mode": "direct"})
    assert first.status_code == 202
    second = client.post("/api/v1/curriculum-explore", json={"domain_name": "高等数学", "mode": "direct"})
    assert second.status_code == 202
    assert second.json()["deduplicated"] is True
    assert second.json()["run_id"] == first.json()["run_id"]
    GATE.set()


# ---------------- 容量 / 锁定 / 参数长度 ----------------

def test_course_explore_capacity_reached(env):
    client, kn_repo, _ = env
    for i in range(4):
        _seed_knowledge(kn_repo, set_no=str(i + 1), status="draft")
    resp = client.post("/api/v1/courses/01_math_analysis/explore", json={"mode": "direct"})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "CAPACITY_REACHED"


def test_course_explore_course_locked(env):
    client, kn_repo, _ = env
    _seed_knowledge(kn_repo, set_no="1", status="completed")
    _seed_knowledge(kn_repo, set_no="2", status="completed")
    resp = client.post("/api/v1/courses/01_math_analysis/explore", json={"mode": "direct"})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "COURSE_LOCKED"


def test_course_explore_rejects_overlong_ref_text(env):
    client, _, _ = env
    resp = client.post("/api/v1/courses/01_math_analysis/explore",
                       json={"mode": "text", "ref_text": "x" * 10001})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVALID_PARAMS"


def test_course_explore_validation_order_capacity_before_running(env):
    """校验序列：CAPACITY_REACHED 先于幂等查重。"""
    client, kn_repo, _ = env
    for i in range(4):
        _seed_knowledge(kn_repo, set_no=str(i + 1), status="draft")
    GATE.clear()
    first = client.post("/api/v1/courses/01_math_analysis/explore", json={"mode": "direct"})
    assert first.status_code == 409  # 容量拦截优先，不入队
    GATE.set()


# ---------------- adopt 正常流与强校验 ----------------

def test_adopt_flow_creates_draft_rows_and_reports_remaining(env):
    client, kn_repo, _ = env
    run = client.post("/api/v1/courses/01_math_analysis/explore", json={"mode": "direct"}).json()
    ready = _wait_ready(client, run["run_id"])
    assert ready["status"] == "ready" and len(ready["proposals"]) == 2

    adopted = client.post(f"/api/v1/explore-runs/{run['run_id']}/adopt",
                          json={"selected": ["pp_000000000001", "pp_000000000002"]})
    assert adopted.status_code == 200
    body = adopted.json()
    assert len(body["adopted"]) == 2 and body["remaining_slots"] == 2
    assert body["run"]["status"] == "adopted"
    rows = kn_repo.list_knowledge(course_id="01_math_analysis", kind="tutorial")
    drafts = [r for r in rows if r.status == "draft"]
    assert len(drafts) == 2


def test_adopt_rejects_set_no_masquerading_as_proposal_id(env):
    """proposal_id 严格匹配：set_no 兜底不得误通过。"""
    client, kn_repo, _ = env
    run = client.post("/api/v1/courses/01_math_analysis/explore", json={"mode": "direct"}).json()
    _wait_ready(client, run["run_id"])
    resp = client.post(f"/api/v1/explore-runs/{run['run_id']}/adopt", json={"selected": ["1"]})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVALID_PARAMS"


def test_adopt_twice_conflicts(env):
    client, _, _ = env
    run = client.post("/api/v1/courses/01_math_analysis/explore", json={"mode": "direct"}).json()
    _wait_ready(client, run["run_id"])
    first = client.post(f"/api/v1/explore-runs/{run['run_id']}/adopt",
                        json={"selected": ["pp_000000000002"]})
    assert first.status_code == 200
    second = client.post(f"/api/v1/explore-runs/{run['run_id']}/adopt",
                         json={"selected": ["pp_000000000001"]})
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "RUN_STATE_CONFLICT"


# ---------------- adopt 单事务原子性（A1 裁决，repo 层） ----------------

def test_adopt_run_builder_failure_rolls_back_everything(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'atomic.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    from qed_tracker.database import utc_now

    now = utc_now()
    session.add(QtExploreRun(run_id=new_run_id(), scope="course", course_id="c1", status="ready",
                             params={}, proposals=[], adopted_ids=[], created_at=now, updated_at=now))
    session.commit()
    repo = ExplorationRepository(lambda: factory())
    run_id = session.query(QtExploreRun).first().run_id

    from qed_tracker.db.models import QtKnowledge

    def builder(db_session):
        db_session.add(QtKnowledge(knowledge_id="kn_a", domain_id="d", course_id="c1", kind="tutorial",
                                   set_no="1", name="教程1：A", textbook_intro="", exercise_intro="",
                                   materials_intro="", status="draft", created_at=now, updated_at=now))
        raise RuntimeError("第二行构造爆炸")

    with pytest.raises(RuntimeError):
        repo.adopt_run(run_id, adopted_ids=["kn_a"], knowledge_builder=builder)

    checking = factory()
    assert checking.query(QtKnowledge).count() == 0, "知识行必须随事务回滚"
    assert checking.get(QtExploreRun, run_id).status == ExploreRunStatus.READY.value, \
        "builder 失败后 run 必须保持 ready"
    checking.close()
    engine.dispose()


# =====================================================================
# REQ-059 增补契约测试（Step 3）
# =====================================================================

# -------- R1/R2: GET /domains + PATCH /domains/{id} --------

def test_get_domains_returns_all(env):
    """GET /api/v1/domains 返回所有领域（插入序）。"""
    client, _, _ = env
    resp = client.get("/api/v1/domains")
    assert resp.status_code == 200
    domains = resp.json()
    assert len(domains) >= 1
    ids = [d["domain_id"] for d in domains]
    assert "math" in ids


def test_get_domains_empty(tmp_path):
    """空库返回空列表。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = load_settings(data_root=tmp_path)
    app = create_app(settings, knowledge_repository=KnowledgeRepository(lambda: factory()))
    with TestClient(app) as c:
        resp = c.get("/api/v1/domains")
        assert resp.status_code == 200
        assert resp.json() == []
    engine.dispose()


def test_patch_domain_updates_description_and_stages(env):
    """PATCH 可改 description/stages，name 不可变。"""
    client, _, _ = env
    resp = client.patch("/api/v1/domains/math", json={"description": "新简介", "stages": ["A", "B"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["description"] == "新简介"
    assert body["stages"] == ["A", "B"]
    assert body["name"] == "数学"  # name 未变


def test_patch_domain_empty_body_noop(env):
    """空 body 返回当前对象，不修改任何字段。"""
    client, _, _ = env
    before = client.get("/api/v1/domains").json()
    math_before = next(d for d in before if d["domain_id"] == "math")
    resp = client.patch("/api/v1/domains/math", json={})
    assert resp.status_code == 200
    assert resp.json()["description"] == math_before["description"]
    assert resp.json()["stages"] == math_before["stages"]


def test_patch_domain_not_found(env):
    client, _, _ = env
    resp = client.patch("/api/v1/domains/nonexistent", json={"description": "x"})
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "DOMAIN_NOT_FOUND"


# -------- R3: 重探语义（apply 分支） --------

_CURRICULUM_PROPOSALS = [
    {"change_id": "ch_000000000001", "action": "create_domain", "entity": "domain",
     "target_id": "new_domain", "payload": {"name": "新领域", "description": "新领域描述", "stages": ["本科基础"]}},
    {"change_id": "ch_000000000002", "action": "create_course", "entity": "course",
     "target_id": "c_new_001", "payload": {"name": "实变函数", "stage": "本科进阶", "sort_order": 3}},
]

# 重探场景：domain name="数学" 命中已有领域
_CURRICULUM_PROPOSALS_REEXPLORE = [
    {"change_id": "ch_000000000001", "action": "create_domain", "entity": "domain",
     "target_id": "math_new", "payload": {"name": "数学", "description": "重探", "stages": ["本科基础"]}},
    {"change_id": "ch_000000000002", "action": "create_course", "entity": "course",
     "target_id": "c_re_001", "payload": {"name": "实变函数", "stage": "本科进阶", "sort_order": 3}},
]


class FakeCurriculumWithProposals:
    """返回固定 curriculum proposals 的 fake advisor（首次探索场景）。"""

    def __init__(self, **kwargs):
        pass

    def propose(self, domain_name, *, mode, ref_text="", ref_doc_path=""):
        GATE.wait(timeout=5)
        return [dict(p) for p in _CURRICULUM_PROPOSALS]

    def close(self):
        pass

    def metadata(self):
        return {"model": "fake", "calls": 1}


class FakeCurriculumReexplore:
    """返回重探场景 proposals（domain name 命中已有领域）。"""

    def __init__(self, **kwargs):
        pass

    def propose(self, domain_name, *, mode, ref_text="", ref_doc_path=""):
        GATE.wait(timeout=5)
        return [dict(p) for p in _CURRICULUM_PROPOSALS_REEXPLORE]

    def close(self):
        pass

    def metadata(self):
        return {"model": "fake", "calls": 1}


def test_curriculum_apply_with_existing_domain_records_skipped(env, monkeypatch):
    """重探：domain_name 命中既有领域 → create_domain 记 skipped，create_course 挂靠既有领域。"""
    from qed_tracker.providers import explore_advisor
    monkeypatch.setattr(explore_advisor, "CurriculumExploreAdvisor", FakeCurriculumReexplore)

    client, _, er_repo = env
    # 发起探索
    resp = client.post("/api/v1/curriculum-explore", json={"domain_name": "数学", "mode": "direct"})
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]
    # 直接设 run 为 ready（跳过 background task 依赖）+ 注入 proposals
    from qed_tracker.db.models import QtExploreRun
    with er_repo._session_factory() as s:
        row = s.get(QtExploreRun, run_id)
        row.status = "ready"
        row.proposals = [dict(p) for p in _CURRICULUM_PROPOSALS_REEXPLORE]
        s.commit()

    # apply：ch_000000000001 是 add_domain，name="数学" 命中已有领域 → skipped
    apply_resp = client.post(f"/api/v1/curriculum-runs/{run_id}/apply",
                             json={"selected": ["ch_000000000001", "ch_000000000002"]})
    assert apply_resp.status_code == 200
    body = apply_resp.json()
    assert body["run"]["status"] == "applied"
    assert body["conflicts"] == []
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["change_id"] == "ch_000000000001"


def test_curriculum_apply_first_exploration_no_skipped(env, monkeypatch):
    """首次探索：domain_name 不命中 → create_domain 正常执行，skipped 为空。"""
    from qed_tracker.providers import explore_advisor
    monkeypatch.setattr(explore_advisor, "CurriculumExploreAdvisor", FakeCurriculumWithProposals)

    client, _, er_repo = env
    resp = client.post("/api/v1/curriculum-explore", json={"domain_name": "概率论", "mode": "direct"})
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]
    # 直接设 run 为 ready + 注入 proposals
    from qed_tracker.db.models import QtExploreRun
    with er_repo._session_factory() as s:
        row = s.get(QtExploreRun, run_id)
        row.status = "ready"
        row.proposals = [dict(p) for p in _CURRICULUM_PROPOSALS]
        s.commit()

    apply_resp = client.post(f"/api/v1/curriculum-runs/{run_id}/apply",
                             json={"selected": ["ch_000000000001", "ch_000000000002"]})
    assert apply_resp.status_code == 200
    body = apply_resp.json()
    assert body["run"]["status"] == "applied"
    assert body["skipped"] == []


# -------- 手工五端点（§11.3 字段口径） --------

def test_post_domain_server_generated_id(env):
    """POST /domains 服务端生成 domain_id，body 无需 domain_id。"""
    client, _, _ = env
    resp = client.post("/api/v1/domains", json={"name": "线性代数", "description": "线性空间", "stages": ["本科基础"]})
    assert resp.status_code == 201
    body = resp.json()
    assert body["domain_id"]  # 非空，服务端生成
    assert body["name"] == "线性代数"
    assert body["description"] == "线性空间"


def test_post_domain_missing_name_422(env):
    client, _, _ = env
    resp = client.post("/api/v1/domains", json={})
    assert resp.status_code == 422


def test_post_domain_name_conflict_409(env):
    client, _, _ = env
    resp = client.post("/api/v1/domains", json={"name": "数学"})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "DOMAIN_NAME_CONFLICT"


def test_post_course_under_domain_server_generated_id(env):
    """POST /domains/{id}/courses 服务端生成 course_id。"""
    client, _, _ = env
    resp = client.post("/api/v1/domains/math/courses",
                       json={"name": "实变函数", "stage": "本科进阶", "sort_order": 3})
    assert resp.status_code == 201
    body = resp.json()
    assert body["course_id"]  # 非空
    assert body["name"] == "实变函数"
    assert body["domain_id"] == "math"


def test_patch_course_only_stage_sort_note(env):
    """PATCH /courses/{id} 只能改 stage/sort_order/note，name 不可变。"""
    client, _, _ = env
    resp = client.patch("/api/v1/courses/01_math_analysis",
                        json={"stage": "本科进阶", "sort_order": 5, "note": "新介绍"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "本科进阶"
    assert body["sort_order"] == 5
    assert body["note"] == "新介绍"
    assert body["name"] == "数学分析"  # name 未变


def test_patch_course_not_found(env):
    client, _, _ = env
    resp = client.patch("/api/v1/courses/nonexistent", json={"stage": "x"})
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "COURSE_NOT_FOUND"


def test_delete_course_guard_has_knowledge(env, monkeypatch):
    """DELETE 有知识行的课程 → 409 COURSE_HAS_KNOWLEDGE。"""
    client, kn_repo, _ = env
    _seed_knowledge(kn_repo, set_no="1", status="draft")
    resp = client.delete("/api/v1/courses/01_math_analysis")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "COURSE_HAS_KNOWLEDGE"


def test_delete_course_not_found(env):
    client, _, _ = env
    resp = client.delete("/api/v1/courses/nonexistent")
    assert resp.status_code == 404


def test_delete_domain_guard_not_empty(env):
    """DELETE 有课程的领域 → 409 DOMAIN_NOT_EMPTY。"""
    client, _, _ = env
    resp = client.delete("/api/v1/domains/math")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "DOMAIN_NOT_EMPTY"


def test_delete_empty_domain_succeeds(env, monkeypatch):
    """DELETE 空领域（无课程）→ 200。"""
    client, _, _ = env
    # 先建一个空领域
    post_resp = client.post("/api/v1/domains", json={"name": "空领域"})
    assert post_resp.status_code == 201
    domain_id = post_resp.json()["domain_id"]
    # 删掉
    del_resp = client.delete(f"/api/v1/domains/{domain_id}")
    assert del_resp.status_code == 200
