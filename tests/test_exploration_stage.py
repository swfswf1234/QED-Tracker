"""REQ-067-B12: 探索状态机 6 态 + apply-results / re-explore 端点测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.api.main import create_app
from qed_tracker.config import load_settings
from qed_tracker.db.knowledge_repository import (
    InvalidExplorationTransition,
    KnowledgeRepository,
)
from qed_tracker.db.models import Base, QedCourse, QedDomain


@pytest.fixture
def repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'exploration.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    from qed_tracker.database import utc_now

    now = utc_now()
    # 领域：待确认态（用于 apply-results / re-explore）
    session.add(QedDomain(
        domain_id="math", name="数学", description="数学领域",
        stages=["本科基础"], exploration_stage="待确认",
        explore_pending={"kind": "review_results", "courses": []},
        created_at=now, updated_at=now,
    ))
    # 领域：已完成态（用于错误码测试）
    session.add(QedDomain(
        domain_id="physics", name="物理", description="物理领域",
        stages=["本科基础"], exploration_stage="已完成",
        created_at=now, updated_at=now,
    ))
    # 课程：待确认态
    session.add(QedCourse(
        course_id="c01", domain_id="math", sort_order=1, name="数学分析",
        aliases=[], stage="本科基础", prerequisites=[], related_targets=[],
        exploration_stage="待确认",
        explore_pending={"kind": "review_results", "tutorials": []},
        created_at=now, updated_at=now,
    ))
    # 课程：已完成态
    session.add(QedCourse(
        course_id="c02", domain_id="math", sort_order=2, name="高等代数",
        aliases=[], stage="本科基础", prerequisites=[], related_targets=[],
        exploration_stage="已完成",
        created_at=now, updated_at=now,
    ))
    session.commit()
    repo = KnowledgeRepository(lambda: factory())
    yield repo
    engine.dispose()


def _domain_explore_handler(params, progress):
    """假领域探索处理器（测试用）。"""
    return {"status": "ok", "domain_id": params.get("domain_id")}


def _course_explore_handler(params, progress):
    """假课程探索处理器（测试用）。"""
    return {"status": "ok", "course_id": params.get("course_id")}


@pytest.fixture
def client(tmp_path, repo):
    settings = load_settings(data_root=tmp_path)
    app = create_app(
        settings,
        knowledge_repository=repo,
        extra_handlers={
            "domain_explore": _domain_explore_handler,
            "course_explore": _course_explore_handler,
        },
    )
    with TestClient(app) as test_client:
        yield test_client


# ===== 领域 apply-results =====

def test_domain_apply_results_success(client, repo):
    """领域 apply-results：待确认 -> 已完成，courses_kept 正确。"""
    # 创建一个待选课程
    from qed_tracker.database import utc_now
    session = repo._session_factory()
    now = utc_now()
    session.add(QedCourse(
        course_id="c_keep", domain_id="math", sort_order=3, name="待保留",
        aliases=[], stage="本科基础", prerequisites=[], related_targets=[],
        exploration_stage="未开始", created_at=now, updated_at=now,
    ))
    session.add(QedCourse(
        course_id="c_drop", domain_id="math", sort_order=4, name="待删除",
        aliases=[], stage="本科基础", prerequisites=[], related_targets=[],
        exploration_stage="未开始", created_at=now, updated_at=now,
    ))
    session.commit()
    session.close()

    response = client.post("/api/v1/domains/math/apply-results", json={
        "selected_courses": ["c_keep"],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["domain_id"] == "math"
    assert data["courses_kept"] == 1
    # 验证状态变更
    domain = repo.get_domain("math")
    assert domain.exploration_stage == "已完成"
    assert domain.explore_pending is None
    # 验证课程删除
    assert repo.get_course("c_keep") is not None
    assert repo.get_course("c_drop") is None


def test_domain_apply_results_wrong_stage(client):
    """领域 apply-results：非待确认态返回 409。"""
    response = client.post("/api/v1/domains/physics/apply-results", json={
        "selected_courses": [],
    })
    assert response.status_code == 409
    data = response.json()
    assert data["detail"]["code"] == "INVALID_TRANSITION"


def test_domain_apply_results_not_found(client):
    """领域 apply-results：领域不存在返回 404。"""
    response = client.post("/api/v1/domains/nonexist/apply-results", json={
        "selected_courses": [],
    })
    assert response.status_code == 404


def test_domain_apply_results_invalid_params(client):
    """领域 apply-results：参数校验。"""
    response = client.post("/api/v1/domains/math/apply-results", json={
        "selected_courses": "not_a_list",
    })
    assert response.status_code == 422


# ===== 领域 re-explore =====

def test_domain_re_explore_success(client, repo):
    """领域 re-explore：待确认 -> 探索中，返回 task_id。"""
    response = client.post("/api/v1/domains/math/re-explore", json={
        "description": "新描述",
        "mode": "web",
    })
    assert response.status_code == 202
    data = response.json()
    assert "task_id" in data
    # 验证状态变更
    domain = repo.get_domain("math")
    assert domain.exploration_stage == "探索中"
    assert domain.explore_pending is None
    assert domain.description == "新描述"


def test_domain_re_explore_wrong_stage(client):
    """领域 re-explore：非待确认态返回 409。"""
    response = client.post("/api/v1/domains/physics/re-explore", json={})
    assert response.status_code == 409


def test_domain_re_explore_not_found(client):
    """领域 re-explore：领域不存在返回 404。"""
    response = client.post("/api/v1/domains/nonexist/re-explore", json={})
    assert response.status_code == 404


# ===== 课程 apply-results =====

def test_course_apply_results_success(client, repo):
    """课程 apply-results：待确认 -> 已完成，tutorials_kept 正确。"""
    response = client.post("/api/v1/courses/c01/apply-results", json={
        "selected_tutorials": [],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["course_id"] == "c01"
    assert data["tutorials_kept"] == 0
    # 验证状态变更
    course = repo.get_course("c01")
    assert course.exploration_stage == "已完成"
    assert course.explore_pending is None


def test_course_apply_results_wrong_stage(client):
    """课程 apply-results：非待确认态返回 409。"""
    response = client.post("/api/v1/courses/c02/apply-results", json={
        "selected_tutorials": [],
    })
    assert response.status_code == 409


def test_course_apply_results_not_found(client):
    """课程 apply-results：课程不存在返回 404。"""
    response = client.post("/api/v1/courses/nonexist/apply-results", json={
        "selected_tutorials": [],
    })
    assert response.status_code == 404


def test_course_apply_results_invalid_params(client):
    """课程 apply-results：参数校验。"""
    response = client.post("/api/v1/courses/c01/apply-results", json={
        "selected_tutorials": "not_a_list",
    })
    assert response.status_code == 422


# ===== 课程 re-explore =====

def test_course_re_explore_success(client, repo):
    """课程 re-explore：待确认 -> 探索中，返回 task_id。"""
    response = client.post("/api/v1/courses/c01/re-explore", json={
        "description": "新描述",
        "mode": "local",
    })
    assert response.status_code == 202
    data = response.json()
    assert "task_id" in data
    # 验证状态变更
    course = repo.get_course("c01")
    assert course.exploration_stage == "探索中"
    assert course.explore_pending is None
    assert course.description == "新描述"


def test_course_re_explore_wrong_stage(client):
    """课程 re-explore：非待确认态返回 409。"""
    response = client.post("/api/v1/courses/c02/re-explore", json={})
    assert response.status_code == 409


def test_course_re_explore_not_found(client):
    """课程 re-explore：课程不存在返回 404。"""
    response = client.post("/api/v1/courses/nonexist/re-explore", json={})
    assert response.status_code == 404


# ===== 6 态流转（领域） =====

def test_six_state_domain_flow(client, repo):
    """领域探索 6 态完整流转：未开始 -> 已生成 -> 探索中 -> 待确认 -> 已完成。"""
    from qed_tracker.database import utc_now

    # 创建新领域
    session = repo._session_factory()
    now = utc_now()
    session.add(QedDomain(
        domain_id="flow_test", name="流转测试", description="d",
        stages=[], exploration_stage="未开始",
        created_at=now, updated_at=now,
    ))
    session.commit()
    session.close()

    # 未开始 -> 已生成
    repo.update_domain("flow_test", exploration_stage="已生成")
    d = repo.get_domain("flow_test")
    assert d.exploration_stage == "已生成"

    # 已生成 -> 探索中
    repo.update_domain("flow_test", exploration_stage="探索中")
    d = repo.get_domain("flow_test")
    assert d.exploration_stage == "探索中"

    # 探索中 -> 待确认（设置 explore_pending）
    repo.update_domain("flow_test", exploration_stage="待确认",
                       explore_pending={"kind": "review_results", "courses": []})
    d = repo.get_domain("flow_test")
    assert d.exploration_stage == "待确认"
    assert d.explore_pending["kind"] == "review_results"

    # 待确认 -> 已完成（通过 API）
    response = client.post("/api/v1/domains/flow_test/apply-results", json={
        "selected_courses": [],
    })
    assert response.status_code == 200
    d = repo.get_domain("flow_test")
    assert d.exploration_stage == "已完成"
    assert d.explore_pending is None


# ===== 6 态流转（课程） =====

def test_six_state_course_flow(client, repo):
    """课程探索 6 态完整流转：未开始 -> 已生成 -> 探索中 -> 待确认 -> 已完成。"""
    from qed_tracker.database import utc_now

    # 创建新课程
    session = repo._session_factory()
    now = utc_now()
    session.add(QedCourse(
        course_id="flow_c", domain_id="math", sort_order=10, name="流转课程",
        aliases=[], stage="", prerequisites=[], related_targets=[],
        exploration_stage="未开始", created_at=now, updated_at=now,
    ))
    session.commit()
    session.close()

    # 未开始 -> 已生成
    repo.update_course("flow_c", exploration_stage="已生成")
    c = repo.get_course("flow_c")
    assert c.exploration_stage == "已生成"

    # 已生成 -> 探索中
    repo.update_course("flow_c", exploration_stage="探索中")
    c = repo.get_course("flow_c")
    assert c.exploration_stage == "探索中"

    # 探索中 -> 待确认
    repo.update_course("flow_c", exploration_stage="待确认",
                       explore_pending={"kind": "review_results", "tutorials": []})
    c = repo.get_course("flow_c")
    assert c.exploration_stage == "待确认"
    assert c.explore_pending["kind"] == "review_results"

    # 待确认 -> 已完成（通过 API）
    response = client.post("/api/v1/courses/flow_c/apply-results", json={
        "selected_tutorials": [],
    })
    assert response.status_code == 200
    c = repo.get_course("flow_c")
    assert c.exploration_stage == "已完成"
    assert c.explore_pending is None


# ===== explore_pending 在 domain_view 中透出 =====

def test_domain_view_includes_explore_pending(client, repo):
    """领域列表/详情应透出 explore_pending 字段。"""
    # 域详情端点是 GET /api/v1/courses/{domain_id}
    response = client.get("/api/v1/courses/math")
    assert response.status_code == 200
    data = response.json()
    # _domain_view 不透出 explore_pending（前端不需要）
    assert "explore_pending" not in data
    # 但 to_dict() 包含（ORM 层）
    domain = repo.get_domain("math")
    d = domain.to_dict()
    assert "explore_pending" in d
    assert d["explore_pending"]["kind"] == "review_results"
