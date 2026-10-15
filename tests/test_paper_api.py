"""QED-068 B 步：论文探索服务化四端点与 adopt 书本化（8901 HTTP 面）。

默认测试不访问公网：arXiv 提供者与百炼顾问都是注入的假实现；库用临时 SQLite。
契约正本=本仓 `docs/plans/2026-09-14-paper-pipeline-alignment.md`「B 步设计节点」节。
"""

from __future__ import annotations

import re
import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.api.main import create_app
from qed_tracker.config import load_settings
from qed_tracker.db.engine import utc_now
from qed_tracker.db.knowledge_repository import KnowledgeRepository
from qed_tracker.db.models import Base, QedCourse, QedDomain
from qed_tracker.models import Candidate, PaperAssessment, PaperSearch

DOMAIN_ID = "math-advanced"
COURSE_ID = "advanced_mathematics"
ARXIV_ONE = "2601.00001"
ARXIV_TWO = "2601.00002"


def _candidate(identifier: str, title: str) -> Candidate:
    return Candidate(
        "arxiv", identifier, title, ("Ada",), "en", "2026",
        page_url=f"https://arxiv.org/abs/{identifier}",
        download_url=f"https://arxiv.org/pdf/{identifier}",
        identifiers={"arxiv": identifier}, abstract=f"Abstract for {title}",
        subjects=("math.CA",),
        published_at="2026-01-03T00:00:00+00:00", updated_at="2026-01-03T00:00:00+00:00",
    )


class FakeArxiv:
    def __init__(self, candidates):
        self.candidates = candidates
        self.closed = False

    def search_terms(self, terms, *, category, limit=10, sort_by="date", overfetch=False):
        return list(self.candidates)

    def search(self, query="", *, category="", author="", limit=10, sort_by="date"):
        return list(self.candidates)

    def get(self, identifier):
        return next(item for item in self.candidates if item.provider_id == identifier)

    def close(self):
        self.closed = True


class FakePaperAdvisor:
    """plan 用领域分类首项，assess 子分 5/4/3（合成 86 ≥ 推荐阈值 70）。"""

    def __init__(self):
        self.assessed = []
        self.closed = False

    def plan(self, profile, goal, allowed_categories):
        return [PaperSearch(("series convergence",), allowed_categories[0], "覆盖目标")]

    def assess(self, profile, goal, candidates):
        self.assessed = list(candidates)
        return [PaperAssessment(item.provider_id, 5, 4, 3, f"评估 {item.provider_id}") for item in candidates]

    def metadata(self):
        return {"model": "fake", "contract_version": "paper-selection-v1", "calls": 2, "usage": [], "response_sha256": []}

    def close(self):
        self.closed = True


@pytest.fixture
def repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'papers.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = utc_now()
    with factory() as session:
        session.add(QedDomain(
            domain_id=DOMAIN_ID, name="高等数学与级数", description="极限、级数收敛与多元微积分",
            stages=["本科基础"], exploration_stage="已完成", created_at=now, updated_at=now,
        ))
        session.add(QedCourse(
            course_id=COURSE_ID, domain_id=DOMAIN_ID, sort_order=1, name="数学分析 advanced",
            aliases=[], stage="本科基础", prerequisites=[], related_targets=[],
            description="级数与函数项级数", created_at=now, updated_at=now,
        ))
        session.commit()
    yield KnowledgeRepository(lambda: factory())
    engine.dispose()


@pytest.fixture
def client(tmp_path, repo):
    settings = load_settings(data_root=tmp_path)
    arxiv = FakeArxiv([_candidate(ARXIV_ONE, "Series Convergence I"), _candidate(ARXIV_TWO, "Fourier Series II")])
    advisor = FakePaperAdvisor()
    fastapi_app = create_app(
        settings, knowledge_repository=repo, papers_provider=arxiv, paper_advisor=advisor,
    )
    with TestClient(fastapi_app) as test_client:
        test_client.arxiv = arxiv
        test_client.advisor = advisor
        test_client.application = fastapi_app._application
        yield test_client


def _seed(repo: KnowledgeRepository, *, domain: dict | None = None, course: dict | None = None) -> None:
    now = utc_now()
    with repo._session_factory() as session:
        if domain is not None:
            session.add(QedDomain(stages=[], exploration_stage="已完成", created_at=now, updated_at=now, **domain))
        if course is not None:
            session.add(QedCourse(aliases=[], stage="本科基础", prerequisites=[], related_targets=[],
                                  exploration_stage="已完成", created_at=now, updated_at=now, **course))
        session.commit()


def _wait(test_client: TestClient, task_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        record = test_client.get(f"/api/v1/tasks/{task_id}").json()
        if record["status"] in ("succeeded", "failed"):
            return record
        time.sleep(0.05)
    raise AssertionError("任务未在超时内结束")


def _recommend(test_client: TestClient, **body) -> str:
    """发起探索并等任务收尾，返回 selection_id（失败即抛出任务错误）。"""
    payload = {"domain_id": DOMAIN_ID, "recipe": "frontier", "goal": "级数收敛判据"}
    payload.update(body)
    response = test_client.post("/api/v1/papers/recommend", json=payload)
    assert response.status_code == 202, response.text
    record = _wait(test_client, response.json()["task_id"])
    assert record["status"] == "succeeded", record
    return record["result"]["selection_id"]


# ---------------- recommend ----------------


def test_recommend_returns_task_and_report_carries_scope(client):
    selection_id = _recommend(client)
    detail = client.get(f"/api/v1/papers/selections/{selection_id}")
    assert detail.status_code == 200
    report = detail.json()
    assert report["selection_id"] == selection_id
    assert report["domain_id"] == DOMAIN_ID
    assert report["recipe"] == "frontier"
    assert report["recommendations"]
    assert client.advisor.assessed


def test_recommend_without_domain_is_422(client):
    response = client.post("/api/v1/papers/recommend", json={"recipe": "frontier"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_PARAMS"


def test_recommend_with_unregistered_domain_is_422(client):
    response = client.post("/api/v1/papers/recommend", json={"domain_id": "no-such-domain", "recipe": "frontier"})
    assert response.status_code == 422
    assert "no-such-domain" in response.json()["detail"]["message"]


def test_recommend_with_unknown_recipe_is_422(client):
    response = client.post("/api/v1/papers/recommend", json={"domain_id": DOMAIN_ID, "recipe": "weekly"})
    assert response.status_code == 422


def test_recommend_with_unmappable_domain_requires_categories(client, repo):
    """待裁项 #4 裁决：映射不到分类即 422 要求显式 categories；显式给出即可发起。"""
    _seed(repo, domain={"domain_id": "weird", "name": "符号逻辑史", "description": ""})
    missing = client.post("/api/v1/papers/recommend", json={"domain_id": "weird", "recipe": "core"})
    assert missing.status_code == 422
    assert "categories" in missing.json()["detail"]["message"]
    explicit = client.post(
        "/api/v1/papers/recommend", json={"domain_id": "weird", "recipe": "core", "categories": ["math.HO"]},
    )
    assert explicit.status_code == 202


# ---------------- selections 读面 ----------------


def test_selections_list_filters_by_domain_and_recipe(client):
    first = _recommend(client)
    second = _recommend(client, recipe="core")
    listing = client.get("/api/v1/papers/selections").json()["selections"]
    ids = {item["selection_id"] for item in listing}
    assert {first, second} <= ids
    frontier = client.get(f"/api/v1/papers/selections?domain_id={DOMAIN_ID}&recipe=frontier").json()["selections"]
    assert [item["selection_id"] for item in frontier] == [first]
    other = client.get("/api/v1/papers/selections?domain_id=no-such-domain").json()["selections"]
    assert other == []
    summary = frontier[0]
    assert summary["domain_id"] == DOMAIN_ID and summary["recipe"] == "frontier"
    assert summary["recommendation_count"] >= 1


def test_selection_detail_unknown_is_404(client):
    response = client.get("/api/v1/papers/selections/sel-20260101T000000Z-deadbeef")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "SELECTION_NOT_FOUND"


# ---------------- adopt 书本化 ----------------


def _adopt(client, selection_id: str, picks: list[dict]) -> dict:
    response = client.post(f"/api/v1/papers/selections/{selection_id}/adopt", json={"picks": picks})
    assert response.status_code == 202, response.text
    record = _wait(client, response.json()["task_id"])
    assert record["status"] == "succeeded", record
    return record["result"]


def test_adopt_creates_paper_book_rows_with_arxiv_identity(client, repo):
    selection_id = _recommend(client)
    result = _adopt(client, selection_id, [{"rank": 1, "domain_id": DOMAIN_ID, "course_id": COURSE_ID}])
    entry = result["adopted"][0]
    assert entry["status"] == "created"
    assert entry["arxiv_id"] == ARXIV_ONE
    assert re.fullmatch(r"[0-9a-z]+-b\d{2,}", entry["book_id"]), entry["book_id"]
    row = repo.get_book(entry["book_id"])
    assert row.kind == "paper" and row.domain_id == DOMAIN_ID and row.course_id == COURSE_ID
    assert row.title == "Series Convergence I" and row.status == "candidate"
    sources = [item for item in repo.list_sources(entry["book_id"]) if item.channel == "arxiv"]
    assert len(sources) == 1
    assert sources[0].provider_id == ARXIV_ONE
    assert sources[0].download_url == f"https://arxiv.org/pdf/{ARXIV_ONE}"
    enumerated = client.get(f"/api/v1/books?kind=paper&course_id={COURSE_ID}").json()
    assert [item["book_id"] for item in enumerated] == [entry["book_id"]]


def test_adopt_is_idempotent_for_repeated_rank(client, repo):
    selection_id = _recommend(client)
    picks = [{"rank": 1, "domain_id": DOMAIN_ID, "course_id": ""}]
    first = _adopt(client, selection_id, picks)["adopted"][0]
    second = _adopt(client, selection_id, picks)["adopted"][0]
    assert first["status"] == "created"
    assert second["status"] == "duplicated"
    assert second["book_id"] == first["book_id"]
    assert len(client.get("/api/v1/books?kind=paper").json()) == 1


def test_adopt_dedupes_against_library_across_selections(client, repo):
    first_selection = _recommend(client)
    created = _adopt(client, first_selection, [{"rank": 1, "domain_id": DOMAIN_ID, "course_id": ""}])["adopted"][0]
    second_selection = _recommend(client, recipe="core")
    again = _adopt(client, second_selection, [{"rank": 1, "domain_id": DOMAIN_ID, "course_id": ""}])["adopted"][0]
    assert again["status"] == "duplicated" and again["book_id"] == created["book_id"]


def test_adopt_reports_every_pick_in_one_task(client, repo):
    selection_id = _recommend(client)
    result = _adopt(client, selection_id, [
        {"rank": 1, "domain_id": DOMAIN_ID, "course_id": ""},
        {"rank": 2, "domain_id": DOMAIN_ID, "course_id": COURSE_ID},
    ])
    assert [item["rank"] for item in result["adopted"]] == [1, 2]
    assert {item["status"] for item in result["adopted"]} == {"created"}
    assert len(client.get(f"/api/v1/books?kind=paper&domain_id={DOMAIN_ID}").json()) == 2


def test_adopt_rejects_rank_outside_recommendations(client):
    selection_id = _recommend(client)
    response = client.post(
        f"/api/v1/papers/selections/{selection_id}/adopt",
        json={"picks": [{"rank": 99, "domain_id": DOMAIN_ID, "course_id": ""}]},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_PARAMS"


def test_adopt_rejects_empty_picks_and_unknown_selection(client):
    assert client.post("/api/v1/papers/selections/sel-20260101T000000Z-deadbeef/adopt", json={"picks": []}).status_code == 404
    selection_id = _recommend(client)
    response = client.post(f"/api/v1/papers/selections/{selection_id}/adopt", json={"picks": []})
    assert response.status_code == 422


def test_adopt_validates_landing_before_submitting_task(client):
    """⑤′ 判据在端点侧同样生效：缺领域/领域不存在/课程不属于该领域 → 422，且不建任务。"""
    selection_id = _recommend(client)
    base = client.get("/api/v1/tasks").json()
    for picks in (
        [{"rank": 1, "domain_id": "", "course_id": ""}],
        [{"rank": 1, "domain_id": "no-such-domain", "course_id": ""}],
        [{"rank": 1, "domain_id": DOMAIN_ID, "course_id": COURSE_ID},
         {"rank": 1, "domain_id": "no-such-domain", "course_id": ""}],
    ):
        response = client.post(f"/api/v1/papers/selections/{selection_id}/adopt", json={"picks": picks})
        assert response.status_code == 422, picks
    assert client.get("/api/v1/tasks").json() == base


def test_adopt_rejects_course_of_another_domain(client, repo):
    _seed(repo,
          domain={"domain_id": "other", "name": "其它领域", "description": ""},
          course={"course_id": "foreign_course", "domain_id": "other", "sort_order": 2,
                  "name": "外域课程", "description": ""})
    selection_id = _recommend(client)
    response = client.post(
        f"/api/v1/papers/selections/{selection_id}/adopt",
        json={"picks": [{"rank": 1, "domain_id": DOMAIN_ID, "course_id": "foreign_course"}]},
    )
    assert response.status_code == 422
    assert "foreign_course" in response.json()["detail"]["message"]


def test_adopt_rejects_unowned_course(client, repo):
    """领域级发起但落位到无人认领的课程（不存在课程）同样 422。"""
    selection_id = _recommend(client)
    response = client.post(
        f"/api/v1/papers/selections/{selection_id}/adopt",
        json={"picks": [{"rank": 1, "domain_id": DOMAIN_ID, "course_id": "ghost_course"}]},
    )
    assert response.status_code == 422


def test_adopt_is_deduped_per_selection(tmp_path, repo):
    """同 selection 的 adopt 只允许一个活动任务（409 TASK_ALREADY_RUNNING）。"""
    started, release = threading.Event(), threading.Event()

    def blocking(params, progress):
        started.set()
        release.wait(timeout=10)
        return {"adopted": []}

    settings = load_settings(data_root=tmp_path)
    fastapi_app = create_app(
        settings, knowledge_repository=repo,
        papers_provider=FakeArxiv([_candidate(ARXIV_ONE, "Series Convergence I"),
                                   _candidate(ARXIV_TWO, "Fourier Series II")]),
        paper_advisor=FakePaperAdvisor(), extra_handlers={"paper_adopt": blocking},
    )
    with TestClient(fastapi_app) as busy:
        selection_id = _recommend(busy)
        picks = [{"rank": 1, "domain_id": DOMAIN_ID, "course_id": ""}]
        response = busy.post(f"/api/v1/papers/selections/{selection_id}/adopt", json={"picks": picks})
        assert response.status_code == 202
        assert started.wait(timeout=5)
        conflict = busy.post(f"/api/v1/papers/selections/{selection_id}/adopt", json={"picks": picks})
        release.set()
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "TASK_ALREADY_RUNNING"


# ---------------- F2 / ⑤′ 注入 ----------------


def test_http_side_paper_service_carries_advisor_and_domain_checker(client):
    application = client.application
    assert application.papers.advisor is client.advisor
    assert application.papers.domain_exists is not None
    assert application.papers.domain_exists(DOMAIN_ID) is True
    assert application.papers.domain_exists("no-such-domain") is False
