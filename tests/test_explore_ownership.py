"""领域探索状态机测试（QED-051）：run_domain_explore 终态 + apply 全量落库 + API 契约。

零公网：管线以 fake 注入；repo 用 SQLite 内存；任务 handler 经 extra_handlers 替换。
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.api.main import create_app
from qed_tracker.application.domain_explore import run_domain_explore
from qed_tracker.config import load_settings
from qed_tracker.database import utc_now
from qed_tracker.db.knowledge_repository import KnowledgeRepository
from qed_tracker.db.models import Base, QedDomain
from qed_tracker.prompt_lab.pipeline import NameConfirmationRequired, PipelineError


@pytest.fixture
def repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'e.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    now = utc_now()
    session.add(QedDomain(domain_id="math", name="数学", description="d", stages=["本科基础"],
                          created_at=now, updated_at=now))
    session.commit()
    yield KnowledgeRepository(lambda: factory())
    engine.dispose()


class OkPipeline:
    """固定报告 fake；忽略管线构造。"""

    def explore(self, domain_name, *, scope_hint="", mode="direct", ref_text="", ref_doc_path="",
                confirm_name_override=""):
        return {
            "domain": {"final_name": confirm_name_override or domain_name, "description": "新描述",
                       "level": "本科", "classic_tracks": [{"name": "分析学", "kind": "main"}]},
            "courses": [
                {"slug": "analysis", "name": "数学分析", "stage": "基础", "summary": "s",
                 "track": "分析学", "aliases": [], "prerequisites": []},
            ],
            "path": {"edges": [], "graph_td": "graph TD\n"},
        }

    def close(self):
        return None


def test_success_applies_and_sets_completed(repo):
    result = run_domain_explore(repo, OkPipeline(), domain_id="math")
    assert result["outcome"] == "applied"
    domain = repo.get_domain("math")
    assert domain.exploration_stage == "已完成"
    assert domain.explore_pending is None
    assert domain.description == "新描述"
    assert domain.path_results == {"edges": [], "graph_td": "graph TD\n"}
    assert repo.get_course("analysis") is not None


def test_success_applies_course_fields(repo):
    result = run_domain_explore(repo, OkPipeline(), domain_id="math")
    assert result["courses_created"] == 1
    course = repo.get_course("analysis")
    assert course.name == "数学分析"
    assert course.stage == "基础"
    assert course.track == "分析学"
    assert course.description == "s"
    assert course.sort_order == 0


def test_confirmation_required_sets_generated(repo):
    class ConfirmPipeline(OkPipeline):
        def explore(self, *args, **kwargs):
            raise NameConfirmationRequired({"valid": False, "suggested_name": "高等数学", "reason": "r"})

    result = run_domain_explore(repo, ConfirmPipeline(), domain_id="math", confirm_name_override="")
    assert result["outcome"] == "confirmation_required"
    domain = repo.get_domain("math")
    assert domain.exploration_stage == "已生成"
    assert domain.explore_pending["kind"] == "name_confirm"
    assert domain.explore_pending["name_check"]["suggested_name"] == "高等数学"


def test_failure_sets_failed_and_reraises(repo):
    class BoomPipeline(OkPipeline):
        def explore(self, *args, **kwargs):
            raise PipelineError("boom", code="INVALID_PARAMS")

    with pytest.raises(PipelineError):
        run_domain_explore(repo, BoomPipeline(), domain_id="math")
    domain = repo.get_domain("math")
    assert domain.exploration_stage == "失败"
    assert domain.explore_pending["kind"] == "failed"
    assert domain.explore_pending["error"] == "boom"


def test_confirm_override_renames(repo):
    result = run_domain_explore(repo, OkPipeline(), domain_id="math", confirm_name_override="高等数学")
    assert result["outcome"] == "applied"
    domain = repo.get_domain("math")
    assert domain.name == "高等数学"
    assert domain.exploration_stage == "已完成"
    assert domain.explore_pending is None


def test_unknown_domain_raises(repo):
    with pytest.raises(KeyError):
        run_domain_explore(repo, OkPipeline(), domain_id="nope")


# --- API 端点契约（TestClient + 注入 SQLite repo；任务 handler 替换为假实现） ---


def _fake_explore_handler(params, progress):
    return {"outcome": "applied", "domain_id": params["domain_id"],
            "courses_created": 0, "courses_updated": 0}


@pytest.fixture
def api(tmp_path, repo):
    app = create_app(load_settings(data_root=tmp_path), knowledge_repository=repo,
                     extra_handlers={"domain_explore": _fake_explore_handler})
    return TestClient(app)


def _wait(client: TestClient, task_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/api/v1/tasks/{task_id}")
        assert resp.status_code == 200
        data = resp.json()
        if data["status"] in ("succeeded", "failed"):
            return data
        time.sleep(0.02)
    raise AssertionError("task 未结束")


def test_explore_sets_exploring_and_submits(api, repo):
    resp = api.post("/api/v1/domains/math/explore", json={})
    assert resp.status_code == 202
    assert "task_id" in resp.json()
    assert repo.get_domain("math").exploration_stage == "探索中"
    assert repo.get_domain("math").explore_pending is None
    _wait(api, resp.json()["task_id"])


def test_explore_409_when_running(api, repo):
    repo.update_domain("math", exploration_stage="探索中")
    resp = api.post("/api/v1/domains/math/explore", json={})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "DOMAIN_EXPLORING"


def test_explore_404_unknown_domain(api, repo):
    resp = api.post("/api/v1/domains/nope/explore", json={})
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "DOMAIN_NOT_FOUND"


def test_explore_rejects_bad_mode(api, repo):
    resp = api.post("/api/v1/domains/math/explore", json={"mode": "web"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVALID_PARAMS"


def test_confirm_name_exploring_gets_409(api, repo):
    repo.update_domain("math", exploration_stage="探索中")
    resp = api.post("/api/v1/domains/math/confirm-name", json={"decision": "accept"})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "INVALID_TRANSITION"


def test_confirm_name_accept_without_name_uses_suggested(api, repo):
    repo.update_domain("math", exploration_stage="已生成",
                       explore_pending={"kind": "name_confirm",
                                        "name_check": {"suggested_name": "高等数学", "valid": False, "reason": "r"}})
    resp = api.post("/api/v1/domains/math/confirm-name", json={"decision": "accept"})
    assert resp.status_code == 202
    assert repo.get_domain("math").exploration_stage == "探索中"
    assert repo.get_domain("math").explore_pending is None


def test_confirm_name_custom_requires_name(api, repo):
    repo.update_domain("math", exploration_stage="已生成")
    resp = api.post("/api/v1/domains/math/confirm-name", json={"decision": "custom"})
    assert resp.status_code == 422


def test_confirm_name_rejects_bad_decision(api, repo):
    repo.update_domain("math", exploration_stage="已生成")
    resp = api.post("/api/v1/domains/math/confirm-name", json={"decision": "keep"})
    assert resp.status_code == 422


def test_domains_view_exposes_explore_pending(api, repo):
    repo.update_domain("math", exploration_stage="失败",
                       explore_pending={"kind": "failed", "error": "boom"})
    resp = api.get("/api/v1/domains")
    row = next(d for d in resp.json() if d["domain_id"] == "math")
    assert row["explore_pending"] == {"kind": "failed", "error": "boom"}


def test_courses_view_exposes_explore_pending(api, repo):
    repo.update_domain("math", exploration_stage="已生成",
                       explore_pending={"kind": "name_confirm",
                                        "name_check": {"suggested_name": "x", "valid": False, "reason": ""}})
    resp = api.get("/api/v1/courses")
    row = next(d for d in resp.json() if d["domain_id"] == "math")
    assert row["explore_pending"]["kind"] == "name_confirm"


# --- 真 handler 离线探针（monkeypatch DomainPipeline；无 extra_handlers 注入） ---


def test_task_handler_runs_success_offline(tmp_path, repo, monkeypatch):
    from qed_tracker.api import main as api_main

    class FakePipeline:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def explore(self, *args, **kwargs):
            return {
                "domain": {"final_name": "数学", "description": "d", "level": "本科",
                           "classic_tracks": []},
                "courses": [],
                "path": {"edges": [], "graph_td": ""},
            }

        def close(self):
            self.closed = True

    monkeypatch.setattr(api_main, "DomainPipeline", FakePipeline)
    app = api_main.create_app(load_settings(data_root=tmp_path), knowledge_repository=repo)
    with TestClient(app) as client:
        resp = client.post("/api/v1/domains/math/explore", json={})
        assert resp.status_code == 202
        data = _wait(client, resp.json()["task_id"])
    assert data["status"] == "succeeded"
    assert data["result"]["outcome"] == "applied"
    assert repo.get_domain("math").exploration_stage == "已完成"
    assert repo.get_domain("math").explore_pending is None
