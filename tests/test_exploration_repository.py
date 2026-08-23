"""探索运行仓储（qt_explore_runs）行为契约：CRUD、幂等查重与状态机守卫。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.db.exploration_repository import ExplorationRepository, InvalidRunState
from qed_tracker.db.models import Base


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield ExplorationRepository(lambda: factory())
    engine.dispose()


def test_create_course_run_defaults(repo) -> None:
    row = repo.create_run("course", course_id="01_math_analysis", params={"mode": "direct"})
    assert row.run_id.startswith("exp_")
    assert row.scope == "course"
    assert row.status == "running"
    assert row.params == {"mode": "direct"}
    assert row.proposals is None
    assert row.adopted_ids == []
    assert row.conflicts is None
    assert row.error is None
    assert row.created_by == "web"


def test_create_curriculum_run_requires_domain_name(repo) -> None:
    row = repo.create_run("curriculum", domain_name="高等数学", params={"mode": "doc"})
    assert row.course_id is None
    assert row.domain_name == "高等数学"
    with pytest.raises(ValueError, match="course_id"):
        repo.create_run("course", params={"mode": "direct"})
    with pytest.raises(ValueError, match="domain_name"):
        repo.create_run("curriculum", params={"mode": "direct"})


def test_get_run_and_missing(repo) -> None:
    row = repo.create_run("course", course_id="01_math_analysis", params={"mode": "text", "ref_text": "x"})
    fetched = repo.get_run(row.run_id)
    assert fetched is not None and fetched.run_id == row.run_id
    assert repo.get_run("exp_missing") is None


def test_find_running_scopes_by_target(repo) -> None:
    first = repo.create_run("course", course_id="01_math_analysis", params={})
    repo.create_run("course", course_id="02_linear_algebra", params={})
    running = repo.find_running("course", "01_math_analysis")
    assert running is not None and running.run_id == first.run_id
    assert repo.find_running("course", "03_topology") is None
    # 终态后不再命中
    repo.finish_ready(first.run_id, proposals=[{"proposal_id": "pp_1"}], meta=None)
    assert repo.find_running("course", "01_math_analysis") is None


def test_list_runs_orders_desc_with_paging(repo) -> None:
    from datetime import UTC, datetime, timedelta

    base = datetime.now(UTC).replace(tzinfo=None)
    ids = [
        repo.create_run("course", course_id="c1", params={}, created_at=base + timedelta(seconds=i)).run_id
        for i in range(3)
    ]
    page = repo.list_runs("course", "c1", limit=2, offset=0)
    assert [r.run_id for r in page] == list(reversed(ids))[:2]
    page2 = repo.list_runs("course", "c1", limit=2, offset=2)
    assert [r.run_id for r in page2] == list(reversed(ids))[2:]
    assert repo.list_runs("course", "other", limit=20, offset=0) == []


def test_finish_ready_writes_proposals(repo) -> None:
    row = repo.create_run("course", course_id="c1", params={})
    updated = repo.finish_ready(row.run_id, proposals=[{"proposal_id": "pp_1"}], meta={"model": "qwen-plus"})
    assert updated.status == "ready"
    assert updated.proposals == [{"proposal_id": "pp_1"}]
    assert updated.meta == {"model": "qwen-plus"}
    with pytest.raises(InvalidRunState):
        repo.finish_ready(row.run_id, proposals=[], meta=None)


def test_finish_failed_records_error(repo) -> None:
    row = repo.create_run("curriculum", domain_name="d1", params={})
    updated = repo.finish_failed(row.run_id, error={"code": "LLM_UNAVAILABLE", "message": "网关不可达"})
    assert updated.status == "failed"
    assert updated.error["code"] == "LLM_UNAVAILABLE"


def test_adopt_run_moves_ready_to_adopted(repo) -> None:
    row = repo.create_run("course", course_id="c1", params={})
    repo.finish_ready(row.run_id, proposals=[{"proposal_id": "pp_1"}], meta=None)
    updated = repo.adopt_run(row.run_id, adopted_ids=["pp_1"])
    assert updated.status == "adopted"
    assert updated.adopted_ids == ["pp_1"]
    with pytest.raises(InvalidRunState):
        repo.adopt_run(row.run_id, adopted_ids=["pp_2"])


def test_discard_run_is_idempotent_on_terminal(repo) -> None:
    row = repo.create_run("course", course_id="c1", params={})
    repo.finish_ready(row.run_id, proposals=[], meta=None)
    assert repo.discard_run(row.run_id).status == "discarded"
    again = repo.discard_run(row.run_id)  # 幂等：重复 discard 返回终态对象不抛错
    assert again.status == "discarded"


def test_discard_rejects_non_ready_states(repo) -> None:
    row = repo.create_run("course", course_id="c1", params={})
    with pytest.raises(InvalidRunState):
        repo.discard_run(row.run_id)  # running 不可 discard
    failed = repo.finish_failed(repo.create_run("course", course_id="c2", params={}).run_id,
                                error={"code": "LLM_UNAVAILABLE", "message": ""})
    with pytest.raises(InvalidRunState):
        repo.discard_run(failed.run_id)


def test_apply_run_two_terminal_states(repo) -> None:
    clean = repo.create_run("curriculum", domain_name="d1", params={})
    repo.finish_ready(clean.run_id, proposals=[{"change_id": "ch_01"}], meta=None)
    applied = repo.apply_run(clean.run_id, applied_ids=["ch_01"], conflicts=[])
    assert applied.status == "applied"

    partial = repo.create_run("curriculum", domain_name="d2", params={})
    repo.finish_ready(partial.run_id, proposals=[{"change_id": "ch_01"}, {"change_id": "ch_02"}], meta=None)
    result = repo.apply_run(
        partial.run_id, applied_ids=["ch_01"],
        conflicts=[{"change_id": "ch_02", "reason": "课程 id 已存在"}],
    )
    assert result.status == "partially_applied"
    assert result.conflicts[0]["change_id"] == "ch_02"
