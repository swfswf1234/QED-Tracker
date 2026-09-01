"""后台任务层：qt_tasks 数据库表持久化、并发上限与 queued→running→succeeded/failed 状态机。

任务由 HTTP 写操作提交，线程池执行，状态与结果落盘 qt_tasks 表；
同一任务执行失败后可通过重新提交获得新任务（不隐式重试失败任务）。

2026-09-01 REQ-032：从 meta/tasks/ JSON 文件迁移到 qt_tasks 数据库表。
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from qed_tracker.db.models import QtTask

logger = logging.getLogger("qed_tracker.tasks")

ProgressCallback = Callable[[int, str], None]
TaskHandler = Callable[[dict[str, Any], ProgressCallback], dict[str, Any]]


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
    """qt_tasks 数据库表的读写层（REQ-032：替代 meta/tasks/ JSON 文件）。"""

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


class TaskManager:
    def __init__(
        self,
        store: TaskStore,
        handlers: Mapping[str, TaskHandler],
        *,
        max_workers: int = 2,
    ):
        self.store = store
        self.handlers = dict(handlers)
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="qed-task")

    def submit(self, task_type: str, params: dict[str, Any]) -> TaskRecord:
        if task_type not in self.handlers:
            raise ValueError(f"未知任务类型：{task_type}")
        now = datetime.now(UTC)
        record = TaskRecord(
            task_id=secrets.token_hex(6),
            type=task_type,
            status="queued",
            created_at=now.isoformat(),
            params=params,
            updated_at=now.isoformat(),
        )
        self.store.save(record)
        self._executor.submit(self._execute, record)
        return record

    def get(self, task_id: str) -> TaskRecord | None:
        return self.store.load(task_id)

    def list(self) -> list[TaskRecord]:
        return self.store.list()

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)

    def _update(self, record: TaskRecord, **values: Any) -> None:
        for key, value in values.items():
            setattr(record, key, value)
        record.updated_at = datetime.now(UTC).isoformat()
        self.store.save(record)

    def _execute(self, record: TaskRecord) -> None:
        started = time.monotonic()
        logger.info("任务开始：%s（%s）", record.type, record.task_id)
        self._update(record, status="running", progress=5, message="已开始")

        def progress(value: int, message: str) -> None:
            self._update(record, progress=max(0, min(100, value)), message=message)

        try:
            result = self.handlers[record.type](record.params, progress)
            self._update(record, status="succeeded", progress=100, message="完成", result=result)
            logger.info("任务成功：%s（%s）耗时 %.2fs", record.type, record.task_id, time.monotonic() - started)
        except Exception as exc:  # 任务失败不阻塞其他任务，错误原样落盘
            self._update(record, status="failed", message="失败", error=f"{type(exc).__name__}: {exc}")
            logger.error("任务失败：%s（%s）耗时 %.2fs：%s", record.type, record.task_id, time.monotonic() - started, exc)
