"""五层模型 API 端点定向测试（QED-031/QED-050/QED-060/QED-061/QED-062）。

覆盖：knowledge/books/sources 契约、课程体系只读端点、领域/课程管理、A2 采纳、
下载生命周期端点（start/fail/verify/cancel）、探索产物落盘收口、有意义 ID 生成。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.api.main import create_app
from qed_tracker.application.domain_file import (
    read_course_tutorials_file,
    read_domain_file,
    write_domain_courses_file,
    write_domain_file,
)
from qed_tracker.config import load_settings
from qed_tracker.db.knowledge_repository import KnowledgeRepository
from qed_tracker.db.models import Base, BookStatus, KnowledgeStatus, QedCourse, QedDomain

COURSE = "math_analysis"


@pytest.fixture
def repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'kn.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    from qed_tracker.db.engine import utc_now

    now = utc_now()
    session.add(QedDomain(domain_id="math", name="数学", description="d", stages=["本科基础"],
                          created_at=now, updated_at=now))
    session.add(QedCourse(course_id="math_analysis", domain_id="math", sort_order=1, name="数学分析",
                          aliases=[], stage="本科基础", prerequisites=[], related_targets=[],
                          created_at=now, updated_at=now))
    session.add(QedCourse(course_id="linear_algebra", domain_id="math", sort_order=2, name="高等代数",
                          aliases=["线性代数"], stage="本科基础", prerequisites=["math_analysis"],
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


def _seed_knowledge(repo: KnowledgeRepository, *, set_no: str = "1", name: str = "数学分析 套一",
                    status: str = "draft"):
    knowledge = repo.create_knowledge(course_id=COURSE, set_no=set_no, name=name)
    if status == "confirmed":
        repo.confirm_knowledge(knowledge.knowledge_id)
    return knowledge


def _make_book(repo: KnowledgeRepository, book_id: str = "mathanalysis-b01",
               title: str = "微积分学教程", **extra):
    return repo.create_book(
        book_id, title=title, authors=[{"name": "菲赫金哥尔茨", "role": "author"}],
        language="zh", domain_id="math", **extra,
    )


# ---------------- knowledge ----------------


def test_knowledge_list_returns_rows(client, repo):
    _seed_knowledge(repo, set_no="1")
    _seed_knowledge(repo, set_no="2", name="数学分析 套二")
    response = client.get("/api/v1/knowledge")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_knowledge_detail_with_books(client, repo):
    knowledge = _seed_knowledge(repo)
    book = _make_book(repo)
    knowledge.textbook_ref = [{"book_id": book.book_id, "title": book.title}]
    session = repo.session_factory()
    session.merge(knowledge)
    session.commit()
    session.close()
    response = client.get(f"/api/v1/knowledge/{knowledge.knowledge_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["knowledge_id"] == knowledge.knowledge_id
    assert len(body["books"]) == 1
    assert body["books"][0]["book_id"] == book.book_id


def test_knowledge_tutorial_standard_name_flows_through(client, repo):
    """QED-036：教程行规范命名经 API 原样透出。"""
    knowledge = repo.create_knowledge(course_id=COURSE, set_no="1", name="教程1：数学分析（Rudin）")
    response = client.get(f"/api/v1/knowledge/{knowledge.knowledge_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "教程1：数学分析（Rudin）"
    assert body["set_no"] == "1"


def test_knowledge_confirm(client, repo):
    knowledge = _seed_knowledge(repo)
    response = client.post(f"/api/v1/knowledge/{knowledge.knowledge_id}/confirm")
    assert response.status_code == 200
    assert response.json()["status"] == KnowledgeStatus.CONFIRMED.value


def test_knowledge_confirm_twice_409(client, repo):
    knowledge = _seed_knowledge(repo)
    assert client.post(f"/api/v1/knowledge/{knowledge.knowledge_id}/confirm").status_code == 200
    assert client.post(f"/api/v1/knowledge/{knowledge.knowledge_id}/confirm").status_code == 409


def test_knowledge_detail_unknown_404(client):
    assert client.get("/api/v1/knowledge/kn_nope").status_code == 404


# ---------------- books ----------------


def test_book_create_and_transitions(client, repo):
    response = client.post("/api/v1/books", json={
        "book_id": "mathanalysis-b01", "title": "微积分学教程", "part": "第一册",
        "authors": [{"name": "菲赫金哥尔茨", "role": "author"}],
        "language": "zh", "roles": ["textbook"], "status": "decided", "domain_id": "math",
    })
    assert response.status_code == 201
    book_id = response.json()["book_id"]
    assert client.post(f"/api/v1/books/{book_id}/start").json()["status"] == BookStatus.DOWNLOADING.value
    repo.mark_owned(book_id, file_path="raw/math/math_analysis/x.pdf", status="downloaded")
    assert client.post(f"/api/v1/books/{book_id}/verify").json()["status"] == BookStatus.VERIFIED.value


def test_book_register_manual_direct(client, repo, tmp_path, pdf_bytes):
    book = _make_book(repo)
    rel = "raw/math/math_analysis/manual.pdf"
    target = tmp_path / rel
    target.parent.mkdir(parents=True)
    target.write_bytes(pdf_bytes)
    response = client.post(f"/api/v1/books/{book.book_id}/register", json={"relative_path": rel})
    assert response.status_code == 200
    assert response.json()["status"] == BookStatus.DOWNLOADED.value


def test_sources_endpoint(client, repo):
    book = _make_book(repo)
    response = client.post(f"/api/v1/books/{book.book_id}/sources", json={
        "channel": "manual", "ok": True, "download_url": "http://x",
    })
    assert response.status_code == 200
    rows = client.get(f"/api/v1/books/{book.book_id}/sources").json()
    assert len(rows) == 1
    assert rows[0]["channel"] == "manual"


def test_book_transition_unknown_404(client):
    assert client.post("/api/v1/books/bk_nope/start").status_code == 404


def test_book_register_rejects_non_pdf(client, repo, tmp_path):
    book = _make_book(repo)
    rel = "raw/math/math_analysis/not_pdf.txt"
    target = tmp_path / rel
    target.parent.mkdir(parents=True)
    target.write_text("not a pdf", encoding="utf-8")
    response = client.post(f"/api/v1/books/{book.book_id}/register", json={"relative_path": rel})
    assert response.status_code == 400
    assert repo.get_book(book.book_id).status == BookStatus.CANDIDATE.value  # 状态不变


def test_book_register_rejects_path_traversal(client, repo):
    book = _make_book(repo)
    response = client.post(f"/api/v1/books/{book.book_id}/register", json={"relative_path": "../escape.pdf"})
    assert response.status_code == 400


# ---------------- 课程体系只读端点（QED-033） ----------------

_COURSE_FIELDS = {"course_id", "name", "aliases", "track", "stage", "prerequisites", "related_targets", "description", "exploration_stage"}


def test_courses_list_returns_domain_grouped_curricula(client):
    response = client.get("/api/v1/courses")
    assert response.status_code == 200
    domains = response.json()
    assert len(domains) == 1
    domain = domains[0]
    assert domain["domain_id"] == "math"
    assert domain["name"] == "数学"
    courses = domain["courses"]
    assert [c["course_id"] for c in courses] == ["math_analysis", "linear_algebra"]  # sort_order 有序
    assert courses[1]["prerequisites"] == ["math_analysis"]
    assert courses[1]["related_targets"] == ["LAG1"]
    assert set(courses[0]) == _COURSE_FIELDS


def test_courses_detail_returns_single_domain(client):
    response = client.get("/api/v1/courses/math")
    assert response.status_code == 200
    assert [c["course_id"] for c in response.json()["courses"]] == ["math_analysis", "linear_algebra"]


def test_courses_detail_unknown_domain_404(client):
    assert client.get("/api/v1/courses/phys").status_code == 404


def test_courses_requires_db_config_409(client_no_db):
    assert client_no_db.get("/api/v1/courses").status_code == 409
    assert client_no_db.get("/api/v1/courses/math").status_code == 409


# ---------------- 领域/课程管理（QED-026 B2） ----------------


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
        "course_id": "probability",
        "stage": "本科基础",
        "sort_order": 3,
        "description": "课程介绍",
        "aliases": ["概率统计"],
        "track": "概率与统计",
        "prerequisites": ["math_analysis"],
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["course_id"] == "probability"
    assert body["prerequisites"] == ["math_analysis"]


def test_patch_course_updates_track_prereqs_aliases(client):
    resp = client.patch("/api/v1/courses/linear_algebra", json={
        "track": "代数学", "prerequisites": [], "aliases": ["线性代数", "高等代数"], "description": "更新介绍",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["track"] == "代数学"
    assert body["aliases"] == ["线性代数", "高等代数"]


def test_patch_course_supports_exploration_stage_and_pending(client):
    """REQ-077：PATCH /courses 支持 exploration_stage 与 explore_pending。"""
    resp = client.patch("/api/v1/courses/linear_algebra", json={
        "exploration_stage": "探索中",
        "explore_pending": {"kind": "review_results", "tutorials": []},
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["exploration_stage"] == "探索中"
    assert body["explore_pending"]["kind"] == "review_results"


def test_patch_course_rejects_generated_and_unknown_stage(client):
    """REQ-076/077：课程 exploration_stage 拒绝「已生成」与未知值（422）。"""
    for bad in ("已生成", "未知态"):
        resp = client.patch("/api/v1/courses/linear_algebra", json={"exploration_stage": bad})
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "INVALID_PARAMS"


def test_patch_course_absent_explore_pending_is_noop(client):
    """缺省 explore_pending 不清空既有值（PATCH no-op 语义）。"""
    client.patch("/api/v1/courses/linear_algebra", json={
        "explore_pending": {"kind": "review_results", "tutorials": []},
    })
    resp = client.patch("/api/v1/courses/linear_algebra", json={"description": "仅改描述"})
    assert resp.status_code == 200
    assert resp.json()["explore_pending"]["kind"] == "review_results"


def test_create_domain_accepts_optional_domain_id(client):
    resp = client.post("/api/v1/domains", json={"name": "Physics", "domain_id": "phys"})
    assert resp.status_code == 201
    assert resp.json()["domain_id"] == "phys"
    resp_dup = client.post("/api/v1/domains", json={"name": "Physics II", "domain_id": "phys"})
    assert resp_dup.status_code == 409


def test_courses_view_exposes_level_and_tracks(client):
    client.patch("/api/v1/domains/math", json={"level": "本科-硕士", "classic_tracks": [{"name": "分析学", "summary": "s"}]})
    body = client.get("/api/v1/courses").json()[0]
    assert body["level"] == "本科-硕士"
    assert body["classic_tracks"] == [{"name": "分析学", "summary": "s"}]


def test_patch_domain_updates_path_results_and_stage(client):
    resp = client.patch("/api/v1/domains/math", json={
        "path_results": {"notes": "先修在前", "edges": [{"from": "math_analysis", "to": "linear_algebra"}], "graph_td": "graph TD\n"},
        "exploration_stage": "已生成",
    })
    assert resp.status_code == 200
    assert resp.json()["exploration_stage"] == "已生成"


def test_courses_view_exposes_exploration_stage_and_path_results(client):
    client.patch("/api/v1/domains/math", json={
        "path_results": {"notes": "n", "edges": [], "graph_td": "graph TD"}, "exploration_stage": "已完成",
    })
    body = client.get("/api/v1/courses").json()[0]
    assert body["exploration_stage"] == "已完成"


def test_create_domain_rejects_invalid_domain_id(client):
    resp = client.post("/api/v1/domains", json={"name": "Chemistry", "domain_id": "invalid id!"})
    assert resp.status_code == 422


def test_create_course_accepts_optional_course_id(client):
    resp = client.post("/api/v1/domains/math/courses", json={"name": "微分几何", "course_id": "differential_geometry"})
    assert resp.status_code == 201
    assert resp.json()["course_id"] == "differential_geometry"
    resp_dup = client.post("/api/v1/domains/math/courses", json={"name": "微分几何二", "course_id": "differential_geometry"})
    assert resp_dup.status_code == 409


# ---------------- A2 课程知识采纳 ----------------


def _tutorial(set_no: str = "1", name: str | None = None, textbook_title: str = "微积分学教程",
              exercise: bool = True) -> dict:
    if name is None:
        name = f"教程{set_no}：菲赫金哥尔茨《{textbook_title}》"
    item = {
        "set_no": set_no,
        "kind": "tutorial",
        "name": name,
        "position": "beginner",
        "intro": "苏版经典三卷本，中文翻译成熟，适合系统学习分析学地基。" * 5,
        "textbook_ref": [{
            "title": textbook_title, "part": "",
            "authors": [{"name": "菲赫金哥尔茨", "role": "author"}],
            "publisher": "高等教育出版社", "edition": "第8版", "year": 2006,
            "language": "zh", "roles": ["textbook"],
        }],
        "exercise_ref": None,
        "parallel_ref": None,
    }
    if exercise:
        item["exercise_ref"] = [{
            "title": "吉米多维奇数学分析习题集", "part": "",
            "authors": [{"name": "吉米多维奇", "role": "author"}],
            "publisher": "高等教育出版社", "edition": "", "year": None,
            "language": "zh", "roles": ["exercises"],
        }]
    return item


def test_adopt_knowledge_creates_prefilled_drafts(client):
    resp = client.post(f"/api/v1/courses/{COURSE}/knowledge", json={
        "tutorials": [_tutorial("1"), _tutorial("2", name="教程2：Rudin《数学分析原理》", textbook_title="数学分析原理")],
    })
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["created"]) == 2
    assert all(item["status"] == "draft" for item in body["created"])
    rows = client.get("/api/v1/knowledge", params={"course_id": COURSE}).json()
    by_set = {r["set_no"]: r for r in rows}
    assert by_set["1"]["name"] == "教程1：菲赫金哥尔茨《微积分学教程》"
    assert by_set["1"]["textbook_ref"][0]["title"] == "微积分学教程"
    assert by_set["1"]["exercise_ref"][0]["title"] == "吉米多维奇数学分析习题集"
    assert by_set["2"]["textbook_ref"][0]["title"] == "数学分析原理"


def test_adopt_knowledge_idempotent_same_set(client):
    payload = {"tutorials": [_tutorial("1")]}
    first = client.post(f"/api/v1/courses/{COURSE}/knowledge", json=payload).json()
    second = client.post(f"/api/v1/courses/{COURSE}/knowledge", json=payload).json()
    assert second["created"][0]["existing"] is True
    assert second["created"][0]["knowledge_id"] == first["created"][0]["knowledge_id"]


def test_adopt_knowledge_set_no_conflict_409(client):
    client.post(f"/api/v1/courses/{COURSE}/knowledge", json={"tutorials": [_tutorial("1")]})
    resp = client.post(f"/api/v1/courses/{COURSE}/knowledge",
                       json={"tutorials": [_tutorial("1", name="教程1：另一套不同名教材")]})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "SET_NO_CONFLICT"


def test_adopt_knowledge_same_source_exercise_optional(client):
    resp = client.post(f"/api/v1/courses/{COURSE}/knowledge", json={"tutorials": [_tutorial("1", exercise=False)]})
    assert resp.status_code == 201
    row = client.get("/api/v1/knowledge", params={"course_id": COURSE}).json()[0]
    assert row["exercise_ref"] is None


def test_adopt_knowledge_validations(client):
    base = f"/api/v1/courses/{COURSE}/knowledge"
    assert client.post(base, json={"tutorials": []}).status_code == 422
    assert client.post(base, json={"tutorials": [_tutorial("")]}).status_code == 422
    bad = _tutorial("1")
    bad["textbook_ref"] = []
    assert client.post(base, json={"tutorials": [bad]}).status_code == 422
    assert client.post("/api/v1/courses/nope/knowledge", json={"tutorials": [_tutorial()]}).status_code == 404


# ---------------- 自动取书与下载生命周期（QED-060） ----------------


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
    import httpx as _httpx

    from qed_tracker.application.books import BookService
    from qed_tracker.application.resources import ResourceService
    from qed_tracker.downloader import DownloadManager
    from qed_tracker.inventory import Inventory

    def factory():
        manager = DownloadManager(retries=1)
        manager.client.close()
        manager.client = _httpx.Client(transport=_httpx.MockTransport(
            lambda request: _httpx.Response(200, content=pdf, request=request)
        ))
        return BookService([_FetchFakeProvider(candidate)], ResourceService(Inventory(tmp_path), manager))

    from dataclasses import replace as _replace

    settings = _replace(
        load_settings(data_root=tmp_path), db_password="",
        book_min_pages=1, book_min_size_bytes=1, book_llm_confirm=False, book_llm_query=False,
    )
    app = create_app(settings, knowledge_repository=repo, book_service_factory=factory)
    return TestClient(app)


def _make_candidate():
    from qed_tracker.models import Availability, Candidate

    return Candidate(
        "fake", "fake-1", "微积分学教程", ("菲赫金哥尔茨",), "zh", year="2024",
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
    book = _make_book(repo)
    with _fetch_client(tmp_path, repo, _make_candidate(), pdf_bytes) as fetch_client:
        resp = fetch_client.post(f"/api/v1/books/{book.book_id}/fetch")
        assert resp.status_code == 202
        record = _wait(fetch_client, resp.json()["task_id"])
        assert record["status"] == "succeeded", record
        assert record["result"]["ok"] is True
    assert repo.get_book(book.book_id).status == BookStatus.DOWNLOADED.value
    sources = client.get(f"/api/v1/books/{book.book_id}/sources")
    assert sources.status_code == 200
    assert sources.json()[0]["ok"] is True


def test_book_fetch_rejects_non_fetchable_status(client, repo, tmp_path, pdf_bytes):
    book = _make_book(repo)
    repo.decide_book(book.book_id)
    repo.start_download(book.book_id)
    with _fetch_client(tmp_path, repo, _make_candidate(), pdf_bytes) as fetch_client:
        resp = fetch_client.post(f"/api/v1/books/{book.book_id}/fetch")
        assert resp.status_code == 202
        record = _wait(fetch_client, resp.json()["task_id"])
        assert record["status"] == "failed"


def test_book_cancel_resets_stuck_downloading(client, repo):
    book = _make_book(repo)
    repo.decide_book(book.book_id)
    repo.start_download(book.book_id)
    resp = client.post(f"/api/v1/books/{book.book_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == BookStatus.DECIDED.value
    assert client.post(f"/api/v1/books/{book.book_id}/start").status_code == 200


def test_book_cancel_rejects_candidate(client, repo):
    book = _make_book(repo)
    resp = client.post(f"/api/v1/books/{book.book_id}/cancel")
    assert resp.status_code == 409


# ---------------- PATCH / DELETE knowledge (L-15/L-16) ----------------


def test_patch_knowledge_updates_fields(client, repo):
    kn = repo.create_knowledge(course_id=COURSE, set_no="1", name="原始名称", position="beginner")
    response = client.patch(f"/api/v1/knowledge/{kn.knowledge_id}", json={"name": "新名称", "position": "intermediate"})
    assert response.status_code == 200
    assert response.json()["name"] == "新名称"


def test_patch_knowledge_nonexistent_404(client):
    response = client.patch("/api/v1/knowledge/nonexistent-id", json={"name": "新名称"})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "KNOWLEDGE_NOT_FOUND"


def test_patch_knowledge_partial_update(client, repo):
    kn = repo.create_knowledge(course_id=COURSE, set_no="1", name="原始名称", position="beginner", intro="简介")
    response = client.patch(f"/api/v1/knowledge/{kn.knowledge_id}", json={"name": "新名称"})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "新名称"
    assert data["position"] == "beginner"
    assert data["intro"] == "简介"


def test_delete_knowledge(client, repo):
    kn = repo.create_knowledge(course_id=COURSE, set_no="1", name="待删除")
    response = client.delete(f"/api/v1/knowledge/{kn.knowledge_id}")
    assert response.status_code == 200
    assert response.json() == {"ok": "true"}
    assert repo.get_knowledge(kn.knowledge_id) is None


def test_delete_knowledge_nonexistent_404(client):
    response = client.delete("/api/v1/knowledge/nonexistent-id")
    assert response.status_code == 404


# ---------------- QED-061：探索产物落盘收口 ----------------


def test_adopt_course_knowledge_writes_course_file(client, repo, tmp_path):
    resp = client.post(f"/api/v1/courses/{COURSE}/knowledge", json={"tutorials": [_tutorial("1")]})
    assert resp.status_code == 201
    data = read_course_tutorials_file(tmp_path, "math", COURSE)
    assert data["course_id"] == COURSE
    assert len(data["tutorials"]) == 1
    assert data["tutorials"][0]["knowledge_id"].startswith("kt-")
    assert data["tutorials"][0]["textbook_ref"][0]["book_id"]


def test_apply_course_results_finalizes_tutorials_file(client, repo, tmp_path):
    client.post(f"/api/v1/courses/{COURSE}/knowledge",
                json={"tutorials": [_tutorial("1"), _tutorial("2", name="教程2：Rudin《数学分析原理》", textbook_title="数学分析原理")]})
    repo.update_course(COURSE, exploration_stage="待确认")
    rows = client.get("/api/v1/knowledge", params={"course_id": COURSE}).json()
    keep = [r["knowledge_id"] for r in rows if r["set_no"] == "1"]
    resp = client.post(f"/api/v1/courses/{COURSE}/apply-results", json={"selected_tutorials": keep})
    assert resp.status_code == 200
    data = read_course_tutorials_file(tmp_path, "math", COURSE)
    assert [t["set_no"] for t in data["tutorials"]] == ["1"]
    assert repo.get_course(COURSE).exploration_stage == "已完成"


def test_apply_domain_results_backwrites_domains_json(client, repo, tmp_path):
    repo.update_domain("math", exploration_stage="待确认")
    write_domain_file(tmp_path, "math", {
        "domain": "math", "name": "数学", "description": "d", "level": "本科", "scope": "",
        "stages": ["本科基础"], "classic_tracks": [], "courses": [],
    })
    write_domain_courses_file(tmp_path, "math", {
        "domain_id": "math",
        "courses": [
            {"course_id": "math_analysis", "name": "数学分析", "track": "", "stage": "本科基础", "aliases": [], "summary": "", "prerequisites": []},
            {"course_id": "linear_algebra", "name": "高等代数", "track": "", "stage": "本科基础", "aliases": [], "summary": "", "prerequisites": ["math_analysis"]},
        ],
        "path": {"notes": "n", "edges": [], "graph_td": "graph TD"},
    })
    resp = client.post("/api/v1/domains/math/apply-results", json={"selected_courses": ["math_analysis"]})
    assert resp.status_code == 200
    data = read_domain_file(tmp_path, "math")
    assert [c["course_id"] for c in data["courses"]] == ["math_analysis"]
    assert data["path"]["graph_td"] == "graph TD"
    assert not (tmp_path / "raw" / "math" / "courses.json").exists()


# ---------------- QED-062：有意义 ID 生成 ----------------


def test_create_domain_derives_slug_from_ascii_name(client):
    response = client.post("/api/v1/domains", json={"name": "Computer Science"})
    assert response.status_code == 201
    assert response.json()["domain_id"] == "computer-science"


def test_create_domain_rejects_non_ascii_name_without_id(client):
    response = client.post("/api/v1/domains", json={"name": "物理学"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_PARAMS"


def test_create_course_derives_slug_from_ascii_name(client):
    response = client.post("/api/v1/domains/math/courses", json={"name": "Data Structures"})
    assert response.status_code == 201
    assert response.json()["course_id"] == "data_structures"


def test_create_course_rejects_non_ascii_name_without_id(client):
    response = client.post("/api/v1/domains/math/courses", json={"name": "数据结构"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_PARAMS"
