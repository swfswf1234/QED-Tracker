"""prompt 优化探索运行仓储（qt_prompt_runs，QED-043）。

状态机守卫（与 ExplorationRepository 同风格）：
- running → ready（finish_ready，写入报告）/ failed（finish_failed）
- ready → applied（应用领域/课程报告落共享表）/ review_run 任意态可标注（独立于状态机）
- 其余非法迁移抛 InvalidRunState。
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from qed_tracker.db.models import PromptRunReview, PromptRunStatus


class InvalidRunState(RuntimeError):
    """运行状态机非法迁移（对齐 ExplorationRepository.InvalidRunState 先例）。"""


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def new_run_id() -> str:
    return f"prd_{secrets.token_hex(6)}"


class PromptRunRepository:
    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    # ---------------- 查询 ----------------

    def get_run(self, run_id: str) -> Any | None:
        from qed_tracker.db.models import QtPromptRun

        with self._session_factory() as session:
            return session.get(QtPromptRun, run_id)

    def find_running(self, task: str, subject: str) -> Any | None:
        """同对象幂等查重：task+subject 存在 running 时返回最近一行。"""
        from qed_tracker.db.models import QtPromptRun

        with self._session_factory() as session:
            statement = (
                select(QtPromptRun)
                .where(
                    QtPromptRun.task == task,
                    QtPromptRun.subject == subject,
                    QtPromptRun.status == PromptRunStatus.RUNNING.value,
                )
                .order_by(QtPromptRun.created_at.desc(), QtPromptRun.run_id.desc())
            )
            return session.scalars(statement).first()

    def list_runs(
        self,
        *,
        task: str = "",
        status: str = "",
        review_status: str = "",
        limit: int = 20,
        offset: int = 0,
    ) -> list[Any]:
        from qed_tracker.db.models import QtPromptRun

        with self._session_factory() as session:
            statement = select(QtPromptRun)
            if task:
                statement = statement.where(QtPromptRun.task == task)
            if status:
                statement = statement.where(QtPromptRun.status == status)
            if review_status:
                statement = statement.where(QtPromptRun.review_status == review_status)
            statement = (
                statement.order_by(QtPromptRun.created_at.desc(), QtPromptRun.run_id.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(session.scalars(statement))

    # ---------------- 创建与迁移 ----------------

    def create_run(
        self,
        task: str,
        subject: str,
        *,
        scope_hint: str = "",
        params: dict[str, Any],
        task_id: str | None = None,
        created_at: datetime | None = None,
    ) -> Any:
        from qed_tracker.db.models import QtPromptRun

        moment = created_at or _utc_now()
        row = QtPromptRun(
            run_id=new_run_id(),
            task=task,
            subject=subject,
            scope_hint=scope_hint,
            params=params,
            status=PromptRunStatus.RUNNING.value,
            review_status=PromptRunReview.UNREVIEWED.value,
            calls_review=[],
            task_id=task_id,
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
        allowed: tuple[PromptRunStatus, ...],
        target: PromptRunStatus,
        **fields: Any,
    ) -> Any:
        from qed_tracker.db.models import QtPromptRun

        with self._session_factory() as session:
            row = session.get(QtPromptRun, run_id)
            if row is None:
                raise KeyError(f"prompt 运行不存在:{run_id}")
            if PromptRunStatus(row.status) not in allowed:
                raise InvalidRunState(
                    f"运行 {run_id} 状态为 {row.status}，不允许迁移到 {target.value}"
                )
            for key, value in fields.items():
                setattr(row, key, value)
            row.status = target.value
            row.updated_at = _utc_now()
            session.commit()
            return row

    def finish_ready(self, run_id: str, *, report: dict[str, Any]) -> Any:
        return self._transition(
            run_id, (PromptRunStatus.RUNNING,), PromptRunStatus.READY, report=report
        )

    def finish_failed(self, run_id: str, *, error: dict[str, Any]) -> Any:
        return self._transition(
            run_id, (PromptRunStatus.RUNNING,), PromptRunStatus.FAILED, error=error
        )

    def apply_run(self, run_id: str) -> Any:
        return self._transition(run_id, (PromptRunStatus.READY,), PromptRunStatus.APPLIED)

    def review_run(self, run_id: str, *, status: str) -> Any:
        """run 级审核标注（ready 后可标注，approved 才允许 apply）。"""
        from qed_tracker.db.models import QtPromptRun

        if status not in {r.value for r in PromptRunReview}:
            raise ValueError(f"非法审核态：{status}")
        with self._session_factory() as session:
            row = session.get(QtPromptRun, run_id)
            if row is None:
                raise KeyError(f"prompt 运行不存在:{run_id}")
            row.review_status = status
            row.updated_at = _utc_now()
            session.commit()
            return row
