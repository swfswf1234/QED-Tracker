"""五层模型 API 端点定向测试（QED-031）：knowledge/books/sources 契约 + 彻底隐藏。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.api.main import create_app
from qed_tracker.config import load_settings
from qed_tracker.db.knowledge_repository import KnowledgeRepository
from qed_tracker.db.models import Base, BookStatus, KnowledgeStatus, QedCourse, QedDomain


@pytest.fixture
def repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'kn.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    from qed_tracker.database import utc_now

    now = utc_now()
    session.add(QedDomain(domain_id="math", name="数学", description="d", stages=["本科基础"],
                          created_at=now, updated_at=now))
    session.add(QedCourse(course_id="01_math_analysis", domain_id="math", sort_order=1, name="数学分析",
                          aliases=[], stage="本科基础", prerequisites=[], related_targets=[],
                          created_at=now, updated_at=now))
    session.add(QedCourse(course_id="02_linear_algebra", domain_id="math", sort_order=2, name="高等代数",
                          aliases=["线性代数"], stage="本科基础", prerequisites=["01_math_analysis"],
                          related_targets=["LAG1"], created_at=now, updated_at=now))
    session.commit()
    repo = KnowledgeRepository(lambda: factory())
    yield repo
    engine.dispose()


@pytest.fixture
def client(tmp_path, repo):
    settings = load_settings(data_root=tmp_path)
    app = create_app(settings, knowledge_repository=repo)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client_no_db(tmp_path):
    # 无 DB 凭据降级路径（同 test_api.make_client）：五层端点应 409，不尝试连接 MySQL。
    from dataclasses import replace

    settings = replace(load_settings(data_root=tmp_path), db_password="")
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _seed_knowledge(repo: KnowledgeRepository, *, name: str = "数学分析 套一", status: str = "draft"):
    knowledge = repo.create_knowledge(
        domain_id="math", course_id="01_math_analysis", kind="tutorial", set_no="1", name=name,
    )
    if status == "confirmed":
        repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref={"title": "微积分学教程"},
                               exercise_ref={"title": "习题集"})
    elif status == "rejected":
        repo.reject_knowledge(knowledge.knowledge_id, reason="版本旧", by="web")
    return knowledge


def test_knowledge_list_filters_hidden(client, repo):
    _seed_knowledge(repo)
    _seed_knowledge(repo, name="坏书", status="rejected")
    response = client.get("/api/v1/knowledge")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_knowledge_detail_with_books(client, repo):
    knowledge = _seed_knowledge(repo)
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="微积分学教程",
                            authors=["菲赫金哥尔茨"])
    response = client.get(f"/api/v1/knowledge/{knowledge.knowledge_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["knowledge_id"] == knowledge.knowledge_id
    assert len(body["books"]) == 1
    assert body["books"][0]["book_id"] == book.book_id


def test_knowledge_tutorial_standard_name_flows_through(client, repo):
    """QED-036：教程行规范命名（教程{set_no}：书名（作者））经 API 原样透出。"""
    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="1", name="教程1：数学分析（Rudin）")
    response = client.get(f"/api/v1/knowledge/{knowledge.knowledge_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "教程1：数学分析（Rudin）"
    assert body["set_no"] == "1"


def test_knowledge_confirm(client, repo):
    knowledge = _seed_knowledge(repo)
    response = client.post(f"/api/v1/knowledge/{knowledge.knowledge_id}/confirm", json={
        "textbook_ref": {"title": "微积分学教程", "version": "第8版"},
        "textbook_intro": "经典三卷本。",
    })
    assert response.status_code == 200
    assert response.json()["status"] == KnowledgeStatus.CONFIRMED.value


def test_knowledge_reject_requires_reason(client, repo):
    knowledge = _seed_knowledge(repo)
    response = client.post(f"/api/v1/knowledge/{knowledge.knowledge_id}/reject", json={})
    assert response.status_code == 422
    response = client.post(f"/api/v1/knowledge/{knowledge.knowledge_id}/reject",
                           json={"reason": "版本旧"})
    assert response.status_code == 200


def test_knowledge_invalid_transition_409(client, repo):
    knowledge = _seed_knowledge(repo, status="confirmed")
    response = client.post(f"/api/v1/knowledge/{knowledge.knowledge_id}/complete")
    assert response.status_code == 409  # 无书行，不能 completed


def test_book_create_and_transitions(client, repo):
    knowledge = _seed_knowledge(repo)
    response = client.post("/api/v1/books", json={
        "knowledge_id": knowledge.knowledge_id, "kind": "textbook", "title": "微积分学教程",
        "part": "第一册", "authors": ["菲赫金哥尔茨"],
    })
    assert response.status_code == 200
    book_id = response.json()["book_id"]
    assert client.post(f"/api/v1/books/{book_id}/decide").status_code == 200
    assert client.post(f"/api/v1/books/{book_id}/start").status_code == 200
    r = client.post(f"/api/v1/books/{book_id}/complete", json={
        "sha256": "c" * 64, "relative_path": "raw/books/x.pdf", "page_count": 100,
    })
    assert r.status_code == 200
    assert r.json()["status"] == BookStatus.DOWNLOADED.value
    assert client.post(f"/api/v1/books/{book_id}/verify").status_code == 200


def test_book_register_manual_direct(client, repo, tmp_path, pdf_bytes):
    knowledge = _seed_knowledge(repo)
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="微积分学教程",
                            authors=["菲赫金哥尔茨"])
    rel = "raw/books/manual.pdf"
    target = tmp_path / rel
    target.parent.mkdir(parents=True)
    target.write_bytes(pdf_bytes)
    response = client.post(f"/api/v1/books/{book.book_id}/register", json={"relative_path": rel})
    assert response.status_code == 200
    assert response.json()["status"] == BookStatus.DOWNLOADED.value


def test_book_reject_hidden(client, repo):
    knowledge = _seed_knowledge(repo)
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="坏书")
    response = client.post(f"/api/v1/books/{book.book_id}/reject", json={"reason": "不适用"})
    assert response.status_code == 200
    assert client.get(f"/api/v1/knowledge/{knowledge.knowledge_id}").json()["books"] == []


def test_sources_endpoint(client, repo):
    knowledge = _seed_knowledge(repo)
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="微积分学教程")
    response = client.post(f"/api/v1/books/{book.book_id}/sources", json={
        "channel": "manual", "ok": True, "download_url": "http://x",
    })
    assert response.status_code == 200
    rows = client.get(f"/api/v1/books/{book.book_id}/sources").json()
    assert len(rows) == 1
    assert rows[0]["channel"] == "manual"


def test_knowledge_detail_unknown_404(client):
    assert client.get("/api/v1/knowledge/kn_nope").status_code == 404


def test_book_transition_unknown_404(client):
    assert client.post("/api/v1/books/bk_nope/decide").status_code == 404


def test_book_register_rejects_non_pdf(client, repo, tmp_path):
    knowledge = _seed_knowledge(repo)
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="微积分学教程")
    rel = "raw/books/not_pdf.txt"
    target = tmp_path / rel
    target.parent.mkdir(parents=True)
    target.write_text("not a pdf", encoding="utf-8")
    response = client.post(f"/api/v1/books/{book.book_id}/register", json={"relative_path": rel})
    assert response.status_code == 400
    assert repo.get_book(book.book_id).status == BookStatus.CANDIDATE.value  # 状态不变


def test_book_register_rejects_path_traversal(client, repo):
    knowledge = _seed_knowledge(repo)
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="微积分学教程")
    response = client.post(f"/api/v1/books/{book.book_id}/register", json={"relative_path": "../escape.pdf"})
    assert response.status_code == 400


def test_complete_validates_sha256_format(client, repo):
    knowledge = _seed_knowledge(repo)
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="微积分学教程")
    response = client.post(f"/api/v1/books/{book.book_id}/complete",
                           json={"sha256": "not-hex", "relative_path": "raw/books/x.pdf"})
    assert response.status_code == 422


def test_knowledge_rejected_hidden_in_list(client, repo):
    _seed_knowledge(repo)
    _seed_knowledge(repo, name="坏书", status="rejected")
    response = client.get("/api/v1/knowledge?status=rejected")
    assert response.status_code == 200
    assert response.json() == []


# ---------------- QED-033：课程体系只读端点（GET /courses，透出 qed_domain/qed_course） ----------------

_COURSE_FIELDS = {"course_id", "name", "aliases", "track", "stage", "prerequisites", "related_targets", "description", "exploration_stage"}


def test_courses_list_returns_domain_grouped_curricula(client):
    response = client.get("/api/v1/courses")
    assert response.status_code == 200
    domains = response.json()
    assert len(domains) == 1
    domain = domains[0]
    assert domain["domain_id"] == "math"
    assert domain["name"] == "数学"
    assert domain["description"] == "d"
    assert domain["stages"] == ["本科基础"]
    courses = domain["courses"]
    assert [c["course_id"] for c in courses] == ["01_math_analysis", "02_linear_algebra"]  # sort_order 有序
    assert courses[0]["name"] == "数学分析"
    assert courses[1]["stage"] == "本科基础"
    assert courses[1]["aliases"] == ["线性代数"]
    assert courses[1]["prerequisites"] == ["01_math_analysis"]
    assert courses[1]["related_targets"] == ["LAG1"]
    # 契约守卫：课程字段与 courses.py Course dataclass 一致，不透出 DB 审计列
    assert set(courses[0]) == _COURSE_FIELDS


def test_courses_detail_returns_single_domain(client):
    response = client.get("/api/v1/courses/math")
    assert response.status_code == 200
    domain = response.json()
    assert domain["domain_id"] == "math"
    assert [c["course_id"] for c in domain["courses"]] == ["01_math_analysis", "02_linear_algebra"]


def test_courses_detail_unknown_domain_404(client):
    assert client.get("/api/v1/courses/phys").status_code == 404


def test_courses_requires_db_config_409(client_no_db):
    assert client_no_db.get("/api/v1/courses").status_code == 409
    assert client_no_db.get("/api/v1/courses/math").status_code == 409


# ---------------- QED-026 B2：领域/课程管理端点探索字段补齐 ----------------


def test_create_domain_accepts_exploration_fields(client):
    resp = client.post("/api/v1/domains", json={
        "name": "Physics",
        "description": "物理学科",
        "stages": ["基础", "进阶"],
        "level": "本科-硕士",
        "scope": "边界说明",
        "classic_tracks": [{"name": "理论物理", "summary": "s"}],
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["level"] == "本科-硕士"
    assert body["scope"] == "边界说明"
    assert body["classic_tracks"] == [{"name": "理论物理", "summary": "s"}]


def test_patch_domain_updates_level_scope_and_tracks(client):
    resp = client.patch("/api/v1/domains/math", json={
        "level": "本科",
        "scope": "更新边界",
        "classic_tracks": [{"name": "分析学", "summary": "s1"}],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["level"] == "本科"
    assert body["scope"] == "更新边界"
    assert body["classic_tracks"] == [{"name": "分析学", "summary": "s1"}]


def test_create_course_accepts_exploration_fields(client):
    resp = client.post("/api/v1/domains/math/courses", json={
        "name": "概率论与数理统计",
        "stage": "基础",
        "sort_order": 3,
        "description": "课程介绍",
        "aliases": ["概率统计"],
        "track": "概率与统计",
        "prerequisites": ["01_math_analysis"],
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["description"] == "课程介绍"
    assert body["aliases"] == ["概率统计"]
    assert body["track"] == "概率与统计"
    assert body["prerequisites"] == ["01_math_analysis"]


def test_patch_course_updates_track_prereqs_aliases(client):
    resp = client.patch("/api/v1/courses/02_linear_algebra", json={
        "track": "代数学",
        "prerequisites": [],
        "aliases": ["线性代数", "高等代数"],
        "description": "更新介绍",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["track"] == "代数学"
    assert body["prerequisites"] == []
    assert body["aliases"] == ["线性代数", "高等代数"]
    assert body["description"] == "更新介绍"


def test_create_domain_accepts_optional_domain_id(client):
    resp = client.post("/api/v1/domains", json={
        "name": "Physics",
        "domain_id": "phys",
    })
    assert resp.status_code == 201
    assert resp.json()["domain_id"] == "phys"
    # 重复指定同一 id → 409（幂等插入语义在此端点收敛为显式冲突）
    resp_dup = client.post("/api/v1/domains", json={"name": "Physics II", "domain_id": "phys"})
    assert resp_dup.status_code == 409


def test_courses_view_exposes_level_and_tracks(client):
    """GET /courses 领域视图透出 level/classic_tracks（学习中心消费）。"""
    client.patch("/api/v1/domains/math", json={
        "level": "本科-硕士",
        "classic_tracks": [{"name": "分析学", "summary": "s"}],
    })
    body = client.get("/api/v1/courses").json()[0]
    assert body["level"] == "本科-硕士"
    assert body["classic_tracks"] == [{"name": "分析学", "summary": "s"}]


def test_patch_domain_updates_path_results_and_stage(client):
    """A3（QED-048）：探索产物 path_results 与 exploration_stage 经本仓库端点落库。"""
    resp = client.patch("/api/v1/domains/math", json={
        "path_results": {
            "notes": "先修在前",
            "edges": [{"from": "01_math_analysis", "to": "09_abstract_algebra"}],
            "graph_td": "graph TD\n",
        },
        "exploration_stage": "已生成",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["path_results"]["notes"] == "先修在前"
    assert body["path_results"]["edges"][0]["to"] == "09_abstract_algebra"
    assert body["exploration_stage"] == "已生成"


def test_courses_view_exposes_exploration_stage_and_path_results(client):
    """事项四（QED-048）：领域行补 exploration_stage/path_results（前端探索状态机与路径图）。"""
    client.patch("/api/v1/domains/math", json={
        "path_results": {"notes": "n", "edges": [], "graph_td": "graph TD"},
        "exploration_stage": "已完成",
    })
    body = client.get("/api/v1/courses").json()[0]
    assert body["exploration_stage"] == "已完成"
    assert body["path_results"] == {"notes": "n", "edges": [], "graph_td": "graph TD"}


# ---------------- QED-026（A2）：课程知识采纳端点 ----------------


def _tutorial(set_no: str = "1",
              set_name: str = "菲赫金哥尔茨《微积分学教程》+ 吉米多维奇习题集",
              exercise: bool = True,
              textbook_title: str = "微积分学教程") -> dict:
    item = {
        "set_no": set_no,
        "set_name": set_name,
        "textbook": {"title": textbook_title, "original_title": "Курс дифференциального исчисления",
                     "roles": ["textbook"], "position": "comprehensive",
                     "intro": "苏版经典三卷本，中文翻译成熟，适合系统学习分析学地基，" * 5},
        "reason": "苏版经典，与国内大纲最接近",
    }
    if exercise:
        item["exercise"] = {"title": "吉米多维奇数学分析习题集", "original_title": "",
                            "roles": ["exercises"], "position": "comprehensive",
                            "intro": "题量巨大的经典习题集，配套解答齐全，训练强度高，" * 5}
    else:
        item["textbook"]["roles"] = ["textbook", "exercises"]
    return item


def test_adopt_knowledge_creates_prefilled_drafts(client):
    resp = client.post("/api/v1/courses/01_math_analysis/knowledge", json={
        "tutorials": [_tutorial("1"),
                      _tutorial("2", "Rudin《数学分析原理》+ 配套习题集",
                                textbook_title="数学分析原理")],
    })
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["created"]) == 2
    assert all(item["status"] == "draft" for item in body["created"])
    rows = client.get("/api/v1/knowledge", params={"course_id": "01_math_analysis"}).json()
    by_set = {r["set_no"]: r for r in rows}
    assert by_set["1"]["name"].startswith("菲赫金哥尔茨")
    assert by_set["1"]["textbook_ref"]["title"] == "微积分学教程"
    assert by_set["1"]["exercise_ref"]["title"] == "吉米多维奇数学分析习题集"
    assert by_set["1"]["textbook_intro"].startswith("苏版经典")
    assert by_set["2"]["textbook_ref"]["title"] == "数学分析原理"


def test_adopt_knowledge_idempotent_same_set(client):
    payload = {"tutorials": [_tutorial("1")]}
    first = client.post("/api/v1/courses/01_math_analysis/knowledge", json=payload).json()
    second = client.post("/api/v1/courses/01_math_analysis/knowledge", json=payload).json()
    assert second["created"][0]["existing"] is True
    assert second["created"][0]["knowledge_id"] == first["created"][0]["knowledge_id"]


def test_adopt_knowledge_set_no_conflict_409(client):
    client.post("/api/v1/courses/01_math_analysis/knowledge", json={"tutorials": [_tutorial("1")]})
    resp = client.post("/api/v1/courses/01_math_analysis/knowledge",
                       json={"tutorials": [_tutorial("1", "另一套不同名教材")]})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "SET_NO_CONFLICT"


def test_adopt_knowledge_same_source_exercise_optional(client):
    resp = client.post("/api/v1/courses/01_math_analysis/knowledge",
                       json={"tutorials": [_tutorial("1", exercise=False)]})
    assert resp.status_code == 201
    row = client.get("/api/v1/knowledge", params={"course_id": "01_math_analysis"}).json()[0]
    assert row["exercise_ref"] is None
    assert row["textbook_ref"]["roles"] == ["textbook", "exercises"]


def test_adopt_knowledge_validations(client):
    base = "/api/v1/courses/01_math_analysis/knowledge"
    assert client.post(base, json={"tutorials": []}).status_code == 422
    assert client.post(base, json={"tutorials": [_tutorial("")]}).status_code == 422
    bad = _tutorial("1")
    bad["textbook"] = {"roles": ["textbook"]}
    assert client.post(base, json={"tutorials": [bad]}).status_code == 422
    assert client.post("/api/v1/courses/nope/knowledge",
                       json={"tutorials": [_tutorial()]}).status_code == 404


def test_create_domain_rejects_invalid_domain_id(client):
    resp = client.post("/api/v1/domains", json={"name": "Chemistry", "domain_id": "invalid id!"})
    assert resp.status_code == 422


def test_create_course_accepts_optional_course_id(client):
    resp = client.post("/api/v1/domains/math/courses", json={
        "name": "微分几何",
        "course_id": "14_differential_geometry",
    })
    assert resp.status_code == 201
    assert resp.json()["course_id"] == "14_differential_geometry"
    resp_dup = client.post("/api/v1/domains/math/courses", json={
        "name": "微分几何二", "course_id": "14_differential_geometry",
    })
    assert resp_dup.status_code == 409


# ---------------- 自动取书（方案 A 2026-08-28）：fetch / cancel ----------------


class _FetchFakeProvider:
    def __init__(self, candidate):
        self.name = "fake"
        self.candidate = candidate

    def search(self, query, limit=10):
        return [self.candidate]

    def resolve(self, candidate):
        return candidate

    def close(self):
        return None


def _fetch_client(tmp_path, repo, candidate, pdf: bytes):
    """带假 book_service_factory 的 client：fetch 任务全程离线。"""
    import httpx as _httpx

    from qed_tracker.application.books import BookService
    from qed_tracker.application.resources import ResourceService
    from qed_tracker.downloader import DownloadManager
    from qed_tracker.inventory import Inventory

    def factory():
        manager = DownloadManager(retries=1)
        manager.client.close()

        def handler(request):
            return _httpx.Response(200, content=pdf, request=request)

        manager.client = _httpx.Client(transport=_httpx.MockTransport(handler))
        return BookService([_FetchFakeProvider(candidate)], ResourceService(Inventory(tmp_path), manager))

    from dataclasses import replace as _replace

    settings = _replace(load_settings(data_root=tmp_path), db_password="")
    app = create_app(settings, knowledge_repository=repo, book_service_factory=factory)
    return TestClient(app)


def _make_candidate():
    from qed_tracker.models import Availability, Candidate

    return Candidate(
        "fake", "fake-1", "微积分学教程", ("作者",), "zh", year="2024",
        download_url="https://example.com/fake.pdf",
        availability=Availability.DOWNLOADABLE,
    )


def _wait(client, task_id, timeout=5.0):
    import time as _time

    deadline = _time.time() + timeout
    while _time.time() < deadline:
        record = client.get(f"/api/v1/tasks/{task_id}").json()
        if record["status"] in ("succeeded", "failed"):
            return record
        _time.sleep(0.05)
    raise AssertionError("任务未在超时内结束")


def test_book_fetch_submits_task_and_downloads(client, repo, tmp_path, pdf_bytes):
    knowledge = _seed_knowledge(repo)
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="微积分学教程",
                            authors=["作者"])
    with _fetch_client(tmp_path, repo, _make_candidate(), pdf_bytes) as fetch_client:
        resp = fetch_client.post(f"/api/v1/books/{book.book_id}/fetch")
        assert resp.status_code == 202
        record = _wait(fetch_client, resp.json()["task_id"])
        assert record["status"] == "succeeded", record
        assert record["result"]["ok"] is True
    detail = client.get(f"/api/v1/knowledge/{knowledge.knowledge_id}").json()
    target = next(b for b in detail["books"] if b["book_id"] == book.book_id)
    assert target["status"] == BookStatus.DOWNLOADED.value
    sources = client.get(f"/api/v1/books/{book.book_id}/sources")
    assert sources.status_code == 200
    assert sources.json()[0]["ok"] is True


def test_book_fetch_rejects_non_fetchable_status(client, repo, tmp_path, pdf_bytes):
    knowledge = _seed_knowledge(repo)
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="微积分学教程")
    client.post(f"/api/v1/books/{book.book_id}/decide")
    client.post(f"/api/v1/books/{book.book_id}/start")
    with _fetch_client(tmp_path, repo, _make_candidate(), pdf_bytes) as fetch_client:
        resp = fetch_client.post(f"/api/v1/books/{book.book_id}/fetch")
        assert resp.status_code == 409


def test_book_cancel_resets_stuck_downloading(client, repo):
    knowledge = _seed_knowledge(repo)
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="微积分学教程")
    client.post(f"/api/v1/books/{book.book_id}/decide")
    client.post(f"/api/v1/books/{book.book_id}/start")
    resp = client.post(f"/api/v1/books/{book.book_id}/cancel", json={"note": "失联复位"})
    assert resp.status_code == 200
    assert resp.json()["status"] == BookStatus.DECIDED.value
    # 复位后可重新 start
    assert client.post(f"/api/v1/books/{book.book_id}/start").status_code == 200


def test_book_cancel_rejects_candidate(client, repo):
    knowledge = _seed_knowledge(repo)
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="微积分学教程")
    resp = client.post(f"/api/v1/books/{book.book_id}/cancel", json={"note": "x"})
    assert resp.status_code == 409
