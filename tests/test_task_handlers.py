"""测试 domain_explore / course_explore 后台任务处理器（QED-050 re-explore 链路）。"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.api.main import create_app
from qed_tracker.config import load_settings
from qed_tracker.db.knowledge_repository import KnowledgeRepository
from qed_tracker.db.models import Base, QedCourse, QedDomain


@pytest.fixture
def repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'task_handlers.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    from qed_tracker.database import utc_now

    now = utc_now()
    # 领域：探索中（re-explore 后台任务执行时的状态）
    session.add(QedDomain(
        domain_id="math", name="数学", description="数学领域",
        stages=["本科基础"], exploration_stage="探索中",
        created_at=now, updated_at=now,
    ))
    # 课程：探索中
    session.add(QedCourse(
        course_id="c01", domain_id="math", sort_order=1, name="数学分析",
        aliases=[], stage="本科基础", prerequisites=[], related_targets=[],
        description="数学分析课程介绍",
        exploration_stage="探索中",
        created_at=now, updated_at=now,
    ))
    session.commit()
    repo = KnowledgeRepository(lambda: factory())
    yield repo
    engine.dispose()


@pytest.fixture
def client(tmp_path, repo):
    settings = load_settings(data_root=tmp_path)
    # 不传 extra_handlers，使用真实的 domain_explore / course_explore handler
    app = create_app(settings, knowledge_repository=repo)
    with TestClient(app) as test_client:
        yield test_client, app


# ===== domain_explore_handler =====


def _fake_domain_report():
    """模拟 DomainPipeline.explore() 返回值。"""
    return {
        "domain": {
            "final_name": "数学",
            "description": "数学领域",
            "level": "本科",
            "classic_tracks": [{"name": "纯数学", "kind": "main", "summary": "s"}],
            "entry_requirements": "无",
        },
        "courses": [
            {"course_id": "la", "name": "线性代数", "track": "纯数学",
             "summary": "基础课", "stage": "基础", "prerequisites": []},
            {"course_id": "ca", "name": "数学分析", "track": "纯数学",
             "summary": "核心课", "stage": "主干", "prerequisites": ["la"]},
        ],
        "path": {
            "notes": "先学线代再学数分",
            "edges": [{"from": "la", "to": "ca"}],
            "graph_td": "graph TD; la-->ca",
        },
    }


def test_domain_explore_handler_writes_pending(client, repo):
    """domain_explore 后台任务：LLM 探索 → explore_pending 写入 → 待确认。"""
    test_client, app = client
    # 获取真实的 handler
    real_handler = app._manager.handlers["domain_explore"]
    progress_log = []

    def progress(v, msg):
        progress_log.append((v, msg))

    # Mock DomainPipeline.explore 返回模拟报告
    with patch("qed_tracker.api.main.DomainPipeline") as MockPipeline:
        mock_instance = MockPipeline.return_value
        mock_instance.explore.return_value = _fake_domain_report()
        mock_instance.step_calls = []
        result = real_handler({"domain_id": "math", "mode": "direct"}, progress)

    assert result["domain_id"] == "math"
    assert result["courses_found"] == 2
    # 验证 DB 状态
    domain = repo.get_domain("math")
    assert domain.exploration_stage == "待确认"
    pending = domain.explore_pending
    assert pending["kind"] == "review_results"
    assert len(pending["courses"]) == 2
    assert pending["courses"][0]["course_id"] == "la"
    assert pending["domain_report"]["description"] == "数学领域"
    assert "path" in pending


def test_domain_explore_handler_name_confirmation(client, repo):
    """domain_explore 后台任务：名称需确认 → explore_pending 写入 name_confirmation。"""
    test_client, app = client
    real_handler = app._manager.handlers["domain_explore"]

    from qed_tracker.prompt_lab.pipeline import NameConfirmationRequired

    with patch("qed_tracker.api.main.DomainPipeline") as MockPipeline:
        mock_instance = MockPipeline.return_value
        exc = NameConfirmationRequired({"valid": False, "suggested_name": "数学学"})
        mock_instance.explore.side_effect = exc
        mock_instance.step_calls = []
        result = real_handler({"domain_id": "math"}, lambda v, m: None)

    assert result["status"] == "name_confirmation_required"
    domain = repo.get_domain("math")
    assert domain.exploration_stage == "待确认"
    assert domain.explore_pending["kind"] == "name_confirmation"


def test_domain_explore_handler_not_found(client, repo):
    """domain_explore 后台任务：领域不存在 → 抛出 ValueError。"""
    test_client, app = client
    real_handler = app._manager.handlers["domain_explore"]

    with pytest.raises(ValueError, match="领域不存在"):
        real_handler({"domain_id": "nonexist"}, lambda v, m: None)


# ===== course_explore_handler =====


def _fake_tutorials_report():
    """模拟 CoursePipeline.explore() 返回值。"""
    return {
        "course": {"course_id": "c01", "name": "数学分析"},
        "tutorials": [
            {"proposal_id": "pp_aabbcc", "set_no": "1",
             "set_name": "教程1", "reason": "经典教材"},
            {"proposal_id": "pp_ddeeff", "set_no": "2",
             "set_name": "教程2", "reason": "进阶选择"},
        ],
    }


def test_course_explore_handler_writes_pending(client, repo):
    """course_explore 后台任务：LLM 探索 → explore_pending 写入 → 待确认。"""
    test_client, app = client
    real_handler = app._manager.handlers["course_explore"]
    progress_log = []

    def progress(v, msg):
        progress_log.append((v, msg))

    with patch("qed_tracker.api.main.CoursePipeline") as MockPipeline:
        mock_instance = MockPipeline.return_value
        mock_instance.explore.return_value = _fake_tutorials_report()
        mock_instance.step_calls = []
        result = real_handler({"course_id": "c01", "mode": "direct"}, progress)

    assert result["course_id"] == "c01"
    assert result["tutorials_found"] == 2
    # 验证 DB 状态
    course = repo.get_course("c01")
    assert course.exploration_stage == "待确认"
    pending = course.explore_pending
    assert pending["kind"] == "review_results"
    assert len(pending["tutorials"]) == 2
    assert pending["tutorials"][0]["set_no"] == "1"


def test_course_explore_handler_not_found(client, repo):
    """course_explore 后台任务：课程不存在 → 抛出 ValueError。"""
    test_client, app = client
    real_handler = app._manager.handlers["course_explore"]

    with pytest.raises(ValueError, match="课程不存在"):
        real_handler({"course_id": "nonexist"}, lambda v, m: None)


# ===== re-explore 端点 → 后台任务集成 =====
# 注意：后台任务在 ThreadPoolExecutor 中执行，mock 上下文管理器无法跨线程生效。
# 集成测试通过 extra_handlers 注入模拟 handler，验证 端点 → 任务提交 → handler 调用 链路。


def _simulated_domain_explore_handler(params, progress):
    """模拟 domain_explore handler：写入 explore_pending → 待确认。"""
    domain_id = params["domain_id"]
    from qed_tracker.db.knowledge_repository import CLEAR
    # 注意：此 handler 在后台线程中运行，无法直接访问 repo。
    # 这里只验证 handler 被调用并返回正确结构。
    return {"domain_id": domain_id, "courses_found": 2, "simulated": True}


def _simulated_course_explore_handler(params, progress):
    """模拟 course_explore handler：写入 explore_pending → 待确认。"""
    course_id = params["course_id"]
    return {"course_id": course_id, "tutorials_found": 2, "simulated": True}


@pytest.fixture
def integration_client(tmp_path, repo):
    """使用模拟 handler 的测试客户端（验证端点 → 任务提交链路）。"""
    settings = load_settings(data_root=tmp_path)
    app = create_app(
        settings,
        knowledge_repository=repo,
        extra_handlers={
            "domain_explore": _simulated_domain_explore_handler,
            "course_explore": _simulated_course_explore_handler,
        },
    )
    with TestClient(app) as test_client:
        yield test_client, app


def test_domain_re_explore_endpoint_submits_task(integration_client, repo):
    """re-explore 端点 → 任务提交成功 → 返回 task_id。"""
    test_client, app = integration_client
    # 先将领域设为待确认（re-explore 的前置条件）
    session = repo._session_factory()
    from qed_tracker.database import utc_now
    domain = session.get(QedDomain, "math")
    domain.exploration_stage = "待确认"
    domain.explore_pending = {"kind": "review_results", "courses": []}
    domain.updated_at = utc_now()
    session.commit()
    session.close()

    response = test_client.post("/api/v1/domains/math/re-explore", json={
        "mode": "direct",
    })
    assert response.status_code == 202
    data = response.json()
    assert "task_id" in data
    # 验证状态变更：待确认 → 探索中
    domain = repo.get_domain("math")
    assert domain.exploration_stage == "探索中"
    assert domain.explore_pending is None
    # 等待后台任务完成
    import time
    for _ in range(50):
        record = app._manager.store.load(data["task_id"])
        if record.status in ("succeeded", "failed"):
            break
        time.sleep(0.1)
    assert record.status == "succeeded"
    assert record.result["simulated"] is True


def test_course_re_explore_endpoint_submits_task(integration_client, repo):
    """re-explore 端点 → 任务提交成功 → 返回 task_id。"""
    test_client, app = integration_client
    # 先将课程设为待确认
    session = repo._session_factory()
    from qed_tracker.database import utc_now
    course = session.get(QedCourse, "c01")
    course.exploration_stage = "待确认"
    course.explore_pending = {"kind": "review_results", "tutorials": []}
    course.updated_at = utc_now()
    session.commit()
    session.close()

    response = test_client.post("/api/v1/courses/c01/re-explore", json={
        "mode": "direct",
    })
    assert response.status_code == 202
    data = response.json()
    assert "task_id" in data
    # 验证状态变更：待确认 → 探索中
    course = repo.get_course("c01")
    assert course.exploration_stage == "探索中"
    assert course.explore_pending is None
    # 等待后台任务完成
    import time
    for _ in range(50):
        record = app._manager.store.load(data["task_id"])
        if record.status in ("succeeded", "failed"):
            break
        time.sleep(0.1)
    assert record.status == "succeeded"
    assert record.result["simulated"] is True


def test_domain_re_explore_wrong_stage_returns_409(client, repo):
    """re-explore 端点：非待确认态返回 409。"""
    test_client, app = client
    response = test_client.post("/api/v1/domains/math/re-explore", json={})
    assert response.status_code == 409


def test_course_re_explore_wrong_stage_returns_409(client, repo):
    """re-explore 端点：非待确认态返回 409。"""
    test_client, app = client
    response = test_client.post("/api/v1/courses/c01/re-explore", json={})
    assert response.status_code == 409
