"""qt_prompt_runs 仓储契约（QED-043 Phase A）：CRUD + 状态机 + 幂等查重。

SQLite 内存库（Base.metadata），零外部依赖。
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.db.models import Base, PromptRunStatus
from qed_tracker.db.prompt_repository import InvalidRunState, PromptRunRepository


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield PromptRunRepository(factory)
    engine.dispose()


def test_create_run_defaults_running(repo) -> None:
    row = repo.create_run(task="domain_explore", subject="高等数学", params={"mode": "direct"})
    assert row.run_id.startswith("prd_")
    assert row.status == PromptRunStatus.RUNNING.value
    assert repo.get_run(row.run_id) is not None


def test_find_running_idempotent_by_subject(repo) -> None:
    repo.create_run(task="domain_explore", subject="高等数学", params={"mode": "direct"})
    repo.create_run(task="domain_explore", subject="高等数学", params={"mode": "text"})
    first = repo.find_running("domain_explore", "高等数学")
    second = repo.find_running("domain_explore", "高等数学")
    assert first is not None and first.run_id == second.run_id
    assert first.status == PromptRunStatus.RUNNING.value


def test_finish_ready_stores_report(repo) -> None:
    row = repo.create_run(task="domain_explore", subject="高等数学", params={})
    finished = repo.finish_ready(row.run_id, report={"domain": {"name": "高等数学"}})
    assert finished.status == PromptRunStatus.READY.value
    assert finished.report["domain"]["name"] == "高等数学"


def test_illegal_transition_raises(repo) -> None:
    row = repo.create_run(task="domain_explore", subject="x", params={})
    with pytest.raises(InvalidRunState):
        repo.apply_run(row.run_id)


def test_review_run_transitions(repo) -> None:
    row = repo.create_run(task="domain_explore", subject="高等数学", params={})
    repo.finish_ready(row.run_id, report={})
    reviewed = repo.review_run(row.run_id, status="approved")
    assert reviewed.review_status == "approved"


def test_list_runs_paginates(repo) -> None:
    for i in range(3):
        repo.create_run(task="course_explore", subject=f"01_math_analysis_{i}", params={})
    rows = repo.list_runs(task="course_explore", limit=2, offset=1)
    assert len(rows) == 2
