"""后台任务层：`meta/tasks/` 持久化、并发上限与 queued→running→succeeded/failed 状态机。

任务由 HTTP 写操作提交，线程池执行，状态与结果落盘 JSON；
同一任务执行失败后可通过重新提交获得新任务（不隐式重试失败任务）。
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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


class TaskStore:
    def __init__(self, tasks_dir: Path):
        self.tasks_dir = tasks_dir

    def _path(self, task_id: str) -> Path:
        return self.tasks_dir / f"{task_id}.json"

    def save(self, record: TaskRecord) -> None:
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(record.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        target = self._path(record.task_id)
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(payload, encoding="utf-8")
        # 轮询读线程可能短暂持有目标文件的读句柄（Windows 上 rename 会被该句柄阻止），
        # 短重试后仍失败则原样抛出，由调用方决定如何兜底。
        for _ in range(5):
            try:
                os.replace(temporary, target)
                return
            except PermissionError:
                time.sleep(0.02)
        os.replace(temporary, target)

    def load(self, task_id: str) -> TaskRecord | None:
        path = self._path(task_id)
        if not path.exists():
            return None
        # 与 save() 的 os.replace 存在 Windows 读/写竞争窗口，读取侧同样短重试。
        for _ in range(5):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                return TaskRecord(**value)
            except PermissionError:
                time.sleep(0.02)
        value = json.loads(path.read_text(encoding="utf-8"))
        return TaskRecord(**value)

    def list(self) -> list[TaskRecord]:
        if not self.tasks_dir.exists():
            return []
        return [self.load(path.stem) for path in sorted(self.tasks_dir.glob("*.json"), reverse=True) if path.stem != ".tmp"]


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
        record = TaskRecord(
            task_id=secrets.token_hex(6),
            type=task_type,
            status="queued",
            created_at=datetime.now(UTC).isoformat(),
            params=params,
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
