"""Background task scheduler: concurrency cap + queued→running→succeeded/failed state machine.

Tasks are submitted by HTTP write operations, executed on a thread pool, with
status/result persisted to the qt_tasks table (via ``TaskStore``). A failed task
is re-submitted explicitly (no implicit retry). Persistence and the query layer
live in :mod:`qed_tracker.db.tasks_repository`; this module owns only the
executor + transition logic.
"""

from __future__ import annotations

import logging
import secrets
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from qed_tracker.db.tasks_repository import ActiveTaskExists, TaskRecord, TaskStore

logger = logging.getLogger("qed_tracker.tasks")

ProgressCallback = Callable[[int, str], None]
TaskHandler = Callable[[dict[str, Any], ProgressCallback], dict[str, Any]]


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

    def submit(self, task_type: str, params: dict[str, Any], *, dedup: Mapping[str, Any] | None = None) -> TaskRecord:
        """Submit a background task; ``dedup`` gives identity params for active-task dedup.

        Dedup only looks at queued/running (failed/completed tasks do not block a
        re-submit); on a hit raises ActiveTaskExists, which the caller maps to 409
        (QED-050: only one active fetch task per book).
        """
        if task_type not in self.handlers:
            raise ValueError(f"未知任务类型：{task_type}")
        if dedup:
            for record in self.list():
                if record.type != task_type or record.status not in ("queued", "running"):
                    continue
                if all(record.params.get(key) == value for key, value in dedup.items()):
                    raise ActiveTaskExists(f"同任务进行中：{task_type}（{dict(dedup)}）")
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
        except Exception as exc:  # noqa: BLE001 - 任务失败不阻塞其他任务，错误原样落盘
            self._update(record, status="failed", message="失败", error=f"{type(exc).__name__}: {exc}")
            logger.error("任务失败：%s（%s）耗时 %.2fs：%s", record.type, record.task_id, time.monotonic() - started, exc)
