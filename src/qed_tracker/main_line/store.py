"""主链路教材条目存储（meta/main-line/）与状态机。

与现有资源体系（meta/resources/ + qt_resources）完全解耦。每条目回答五要素：
课程 / 版本评价建议 / 渠道记录 / 验收状态。状态机：
draft → reviewed → downloading → downloaded → approved（移交根仓库）/ rejected。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"reviewed", "rejected"},
    "reviewed": {"downloading", "rejected"},
    "downloading": {"downloaded", "rejected"},
    "downloaded": {"approved", "rejected"},
    "approved": set(),
    "rejected": {"draft"},  # 人工否定后可改建议回 draft 重试
}


class MainLineStatus(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class MainLineEntry:
    entry_id: str
    course_id: str
    title: str
    authors: tuple[str, ...]
    version: dict[str, str]
    evaluation: dict[str, Any]
    advice: dict[str, str]
    channels: tuple[dict[str, Any], ...] = ()
    status: str = "draft"
    resource_id: str = ""
    final_path: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "entry_id": self.entry_id,
            "course_id": self.course_id,
            "title": self.title,
            "authors": list(self.authors),
            "version": self.version,
            "evaluation": self.evaluation,
            "advice": self.advice,
            "channels": list(self.channels),
            "status": self.status,
            "resource_id": self.resource_id,
            "final_path": self.final_path,
            "updated_at": self.updated_at,
        }


class EntryStore:
    def __init__(self, data_root: Path):
        self.data_root = data_root.resolve()
        self.main_line_dir = self.data_root / "meta" / "main-line"

    def _path(self, course_id: str, entry_id: str) -> Path:
        return self.main_line_dir / course_id / f"{entry_id}.json"

    def _read(self, course_id: str, entry_id: str) -> MainLineEntry | None:
        path = self._path(course_id, entry_id)
        if not path.is_file():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        return self._from_dict(raw)

    @staticmethod
    def _from_dict(raw: dict[str, Any]) -> MainLineEntry:
        return MainLineEntry(
            entry_id=raw["entry_id"],
            course_id=raw["course_id"],
            title=raw["title"],
            authors=tuple(raw.get("authors", [])),
            version=raw.get("version", {}),
            evaluation=raw.get("evaluation", {}),
            advice=raw.get("advice", {}),
            channels=tuple(raw.get("channels", [])),
            status=raw.get("status", "draft"),
            resource_id=raw.get("resource_id", ""),
            final_path=raw.get("final_path", ""),
            updated_at=raw.get("updated_at", ""),
        )

    def _write(self, entry: MainLineEntry) -> None:
        path = self._path(entry.course_id, entry.entry_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(entry.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, path)

    def create(self, data: dict[str, Any]) -> MainLineEntry:
        now = datetime.now(UTC).isoformat()
        entry = MainLineEntry(
            entry_id=data["entry_id"],
            course_id=data["course_id"],
            title=data["title"],
            authors=tuple(data.get("authors", [])),
            version=data.get("version", {}),
            evaluation=data.get("evaluation", {}),
            advice=data.get("advice", {}),
            status=data.get("status", MainLineStatus.DRAFT.value),
            updated_at=data.get("updated_at", now),
        )
        if self._path(entry.course_id, entry.entry_id).exists():
            raise ValueError(f"教材条目已存在：{entry.entry_id}")
        self._write(entry)
        return entry

    def get(self, course_id: str, entry_id: str) -> MainLineEntry | None:
        return self._read(course_id, entry_id)

    def list_course(self, course_id: str) -> list[MainLineEntry]:
        directory = self.main_line_dir / course_id
        if not directory.is_dir():
            return []
        entries = [self._from_dict(json.loads(path.read_text(encoding="utf-8"))) for path in sorted(directory.glob("*.json"))]
        return entries

    def transition(self, course_id: str, entry_id: str, new_status: MainLineStatus) -> MainLineEntry:
        entry = self._read(course_id, entry_id)
        if entry is None:
            raise ValueError(f"教材条目不存在：{entry_id}")
        allowed = ALLOWED_TRANSITIONS.get(entry.status, set())
        if new_status.value not in allowed:
            raise ValueError(f"非法状态迁移：{entry.status} → {new_status.value}")
        updated = MainLineEntry(
            entry_id=entry.entry_id,
            course_id=entry.course_id,
            title=entry.title,
            authors=entry.authors,
            version=entry.version,
            evaluation=entry.evaluation,
            advice=entry.advice,
            channels=entry.channels,
            status=new_status.value,
            resource_id=entry.resource_id,
            final_path=entry.final_path,
            updated_at=datetime.now(UTC).isoformat(),
        )
        self._write(updated)
        return updated

    def update(self, course_id: str, entry_id: str, **changes: Any) -> MainLineEntry:
        entry = self._read(course_id, entry_id)
        if entry is None:
            raise ValueError(f"教材条目不存在：{entry_id}")
        updated = MainLineEntry(
            entry_id=entry.entry_id,
            course_id=entry.course_id,
            title=changes.get("title", entry.title),
            authors=changes.get("authors", entry.authors),
            version=changes.get("version", entry.version),
            evaluation=changes.get("evaluation", entry.evaluation),
            advice=changes.get("advice", entry.advice),
            channels=changes.get("channels", entry.channels),
            status=entry.status,
            resource_id=changes.get("resource_id", entry.resource_id),
            final_path=changes.get("final_path", entry.final_path),
            updated_at=datetime.now(UTC).isoformat(),
        )
        self._write(updated)
        return updated
