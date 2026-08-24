"""探索运行仓储（qt_explore_runs，QED-040/041）。

状态机守卫（数据库线详规 Accepted）：
- running → ready（finish_ready）/ failed（finish_failed）
- ready → adopted（adopt_run）/ discarded（discard_run）/ applied|partially_applied（apply_run）
- discard 对已 discarded 幂等成功；其余非法迁移抛 InvalidRunState。
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from qed_tracker.db.models import ExploreRunStatus, QtExploreRun


class InvalidRunState(RuntimeError):
    """运行状态机非法迁移（对齐 KnowledgeRepository.InvalidTransition 先例）。"""


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def new_run_id() -> str:
    return f"exp_{secrets.token_hex(6)}"


class ExplorationRepository:
    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    # ---------------- 查询 ----------------

    def get_run(self, run_id: str) -> QtExploreRun | None:
        with self._session_factory() as session:
            return session.get(QtExploreRun, run_id)

    def find_running(self, scope: str, target_id: str) -> QtExploreRun | None:
        """同对象幂等查重：course 按 course_id、curriculum 按 domain_name。"""
        column = QtExploreRun.course_id if scope == "course" else QtExploreRun.domain_name
        with self._session_factory() as session:
            statement = (
                select(QtExploreRun)
                .where(QtExploreRun.scope == scope, column == target_id,
                       QtExploreRun.status == ExploreRunStatus.RUNNING.value)
                .order_by(QtExploreRun.created_at.desc())
            )
            return session.scalars(statement).first()

    def list_runs(self, scope: str, target_id: str, *, limit: int = 20, offset: int = 0) -> list[QtExploreRun]:
        """探索历史：按 created_at 倒序分页。"""
        column = QtExploreRun.course_id if scope == "course" else QtExploreRun.domain_name
        with self._session_factory() as session:
            statement = (
                select(QtExploreRun)
                .where(QtExploreRun.scope == scope, column == target_id)
                .order_by(QtExploreRun.created_at.desc(), QtExploreRun.run_id.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(session.scalars(statement))

    # ---------------- 创建与迁移 ----------------

    def create_run(
        self,
        scope: str,
        *,
        params: dict[str, Any],
        course_id: str = "",
        domain_name: str = "",
        task_id: str | None = None,
        created_by: str = "web",
        created_at: datetime | None = None,
    ) -> QtExploreRun:
        if scope == "curriculum":
            if not domain_name:
                raise ValueError("领域层探索必须提供 domain_name")
        elif not course_id:
            raise ValueError("课程层探索必须提供 course_id")
        moment = created_at or _utc_now()
        row = QtExploreRun(
            run_id=new_run_id(),
            scope=scope,
            course_id=course_id or None,
            domain_name=domain_name or None,
            status=ExploreRunStatus.RUNNING.value,
            params=params,
            adopted_ids=[],
            task_id=task_id,
            created_by=created_by or "web",
            created_at=moment,
            updated_at=moment,
        )
        with self._session_factory() as session:
            session.add(row)
            session.commit()
            return row

    def _transition(
        self,
        run_id: str,
        allowed: tuple[ExploreRunStatus, ...],
        target: ExploreRunStatus,
        **fields: Any,
    ) -> QtExploreRun:
        with self._session_factory() as session:
            row = session.get(QtExploreRun, run_id)
            if row is None:
                raise KeyError(f"探索运行不存在:{run_id}")
            if ExploreRunStatus(row.status) not in allowed:
                raise InvalidRunState(
                    f"运行 {run_id} 状态为 {row.status}，不允许迁移到 {target.value}"
                )
            for key, value in fields.items():
                setattr(row, key, value)
            row.status = target.value
            row.updated_at = _utc_now()
            session.commit()
            return row

    def finish_ready(
        self, run_id: str, *, proposals: list[Any], meta: dict[str, Any] | None
    ) -> QtExploreRun:
        return self._transition(
            run_id, (ExploreRunStatus.RUNNING,), ExploreRunStatus.READY,
            proposals=proposals, meta=meta,
        )

    def finish_failed(self, run_id: str, *, error: dict[str, Any]) -> QtExploreRun:
        return self._transition(run_id, (ExploreRunStatus.RUNNING,), ExploreRunStatus.FAILED, error=error)

    def adopt_run(
        self, run_id: str, *, adopted_ids: list[str], knowledge_builder=None
    ) -> QtExploreRun:
        """ready→adopted（A1 单事务裁决）。

        knowledge_builder(session) 在与 run 迁移相同的事务内落知识行：
        任一失败整体回滚（无孤儿知识行，run 保持 ready）。
        """
        with self._session_factory() as session:
            row = session.get(QtExploreRun, run_id)
            if row is None:
                raise KeyError(f"探索运行不存在:{run_id}")
            if ExploreRunStatus(row.status) is not ExploreRunStatus.READY:
                raise InvalidRunState(f"运行状态 {row.status} 不允许采纳（需 ready）")
            if knowledge_builder is not None:
                knowledge_builder(session)
            merged = [*(row.adopted_ids or []), *adopted_ids]
            row.status = ExploreRunStatus.ADOPTED.value
            row.adopted_ids = merged
            row.updated_at = _utc_now()
            session.commit()
            session.refresh(row)
            return row

    def discard_run(self, run_id: str) -> QtExploreRun:
        try:
            return self._transition(run_id, (ExploreRunStatus.READY,), ExploreRunStatus.DISCARDED)
        except InvalidRunState:
            current = self.get_run(run_id)
            if current is not None and ExploreRunStatus(current.status) is ExploreRunStatus.DISCARDED:
                return current  # 幂等：重复 discard 返回终态对象（契约 §4）
            raise

    def apply_run(
        self, run_id: str, *, applied_ids: list[str], conflicts: list[dict[str, Any]]
    ) -> QtExploreRun:
        """应用课程体系变更：全成功 applied / 有冲突 partially_applied（冲突清单随行记录）。"""
        target = ExploreRunStatus.PARTIALLY_APPLIED if conflicts else ExploreRunStatus.APPLIED
        existing = self.get_run(run_id)
        merged = [*(existing.adopted_ids if existing else []), *applied_ids]
        return self._transition(
            run_id, (ExploreRunStatus.READY,), target, adopted_ids=merged, conflicts=conflicts,
        )

    def attach_task(self, run_id: str, task_id: str) -> QtExploreRun:
        with self._session_factory() as session:
            row = session.get(QtExploreRun, run_id)
            if row is None:
                raise KeyError(f"探索运行不存在:{run_id}")
            row.task_id = task_id
            row.updated_at = _utc_now()
            session.commit()
            return row
