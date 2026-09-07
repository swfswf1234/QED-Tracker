"""Background task persistence (qt_tasks): REQ-032, replaces meta/tasks/ JSON."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from qed_tracker.db.models import QtTask


class ActiveTaskExists(RuntimeError):
    """Same-task dedup hit: an active (queued/running) task with identical params exists (QED-050)."""


@dataclass(slots=True)
class TaskRecord:
    task_id: str
    type: str
    status: str
    created_at: str
    params: dict[str, Any]
    progress: int = 0
    message: str = ""
    updated_at: str = ""
    result: dict[str, Any] | None = None
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "type": self.type,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "params": self.params,
            "result": self.result,
            "error": self.error,
        }

    @classmethod
    def from_row(cls, row: QtTask) -> TaskRecord:
        return cls(
            task_id=row.task_id,
            type=row.type,
            status=row.status,
            created_at=row.created_at.isoformat(),
            params=row.params,
            progress=row.progress,
            message=row.message,
            updated_at=row.updated_at.isoformat(),
            result=row.result,
            error=row.error,
        )


class TaskStore:
    """Read/write layer for the qt_tasks table (REQ-032)."""

    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    def _new_session(self) -> Session:
        return self._session_factory()

    def save(self, record: TaskRecord) -> None:
        with self._new_session() as session:
            existing = session.get(QtTask, record.task_id)
            if existing is not None:
                existing.type = record.type
                existing.status = record.status
                existing.params = record.params
                existing.progress = record.progress
                existing.message = record.message
                existing.result = record.result
                existing.error = record.error
                existing.updated_at = datetime.fromisoformat(record.updated_at) if record.updated_at else datetime.now(UTC)
            else:
                row = QtTask(
                    task_id=record.task_id,
                    type=record.type,
                    status=record.status,
                    params=record.params,
                    progress=record.progress,
                    message=record.message,
                    result=record.result,
                    error=record.error,
                    created_at=datetime.fromisoformat(record.created_at),
                    updated_at=datetime.fromisoformat(record.updated_at) if record.updated_at else datetime.now(UTC),
                )
                session.add(row)
            session.commit()

    def load(self, task_id: str) -> TaskRecord | None:
        with self._new_session() as session:
            row = session.get(QtTask, task_id)
            if row is None:
                return None
            return TaskRecord.from_row(row)

    def list(self) -> list[TaskRecord]:
        with self._new_session() as session:
            rows = session.execute(
                sa.select(QtTask).order_by(QtTask.created_at.desc())
            ).scalars().all()
            return [TaskRecord.from_row(row) for row in rows]
