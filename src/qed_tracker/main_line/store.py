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
    roles: tuple[str, ...] = ()
    """书籍角色（方案 A，多值）：textbook/exercises/solutions/reference；空时按 kind 推导。"""
    resource_id: str = ""
    final_path: str = ""
    reject_reason: str = ""
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
            "roles": list(self.roles),
            "resource_id": self.resource_id,
            "final_path": self.final_path,
            "reject_reason": self.reject_reason,
            "updated_at": self.updated_at,
        }


class EntryStore:
    def __init__(self, data_root: Path):
        self.data_root = data_root.resolve()
        self.main_line_dir = self.data_root / "meta" / "main-line"

    @staticmethod
    def _validate_ids(course_id: str, entry_id: str) -> None:
        for name, value in (("course_id", course_id), ("entry_id", entry_id)):
            if value in (".", "..") or Path(value).name != value:
                raise ValueError(f"非法的 {name}：{value}")

    def _path(self, course_id: str, entry_id: str) -> Path:
        self._validate_ids(course_id, entry_id)
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
            roles=tuple(raw.get("roles", [])),
            resource_id=raw.get("resource_id", ""),
            final_path=raw.get("final_path", ""),
            reject_reason=raw.get("reject_reason", ""),
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
        course_id = data["course_id"]
        entry_id = data["entry_id"]
        self._validate_ids(course_id, entry_id)
        raw_status = data.get("status", MainLineStatus.DRAFT.value)
        try:
            status = MainLineStatus(raw_status).value
        except ValueError:
            raise ValueError(f"非法的 status：{raw_status}") from None
        now = datetime.now(UTC).isoformat()
        entry = MainLineEntry(
            entry_id=entry_id,
            course_id=course_id,
            title=data["title"],
            authors=tuple(data.get("authors", [])),
            version=data.get("version", {}),
            evaluation=data.get("evaluation", {}),
            advice=data.get("advice", {}),
            channels=tuple(data.get("channels", [])),
            status=status,
            roles=tuple(data.get("roles", [])),
            resource_id=data.get("resource_id", ""),
            final_path=data.get("final_path", ""),
            reject_reason=data.get("reject_reason", ""),
            updated_at=data.get("updated_at", now),
        )
        if self._path(course_id, entry_id).exists():
            raise ValueError(f"教材条目已存在：{entry_id}")
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

    def transition(self, course_id: str, entry_id: str, new_status: MainLineStatus, reason: str = "") -> MainLineEntry:
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
            roles=entry.roles,
            resource_id=entry.resource_id,
            final_path=entry.final_path,
            reject_reason=reason if new_status == MainLineStatus.REJECTED else entry.reject_reason,
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
            roles=changes.get("roles", entry.roles),
            resource_id=changes.get("resource_id", entry.resource_id),
            final_path=changes.get("final_path", entry.final_path),
            reject_reason=changes.get("reject_reason", entry.reject_reason),
            updated_at=datetime.now(UTC).isoformat(),
        )
        self._write(updated)
        return updated

    def record_channel(self, course_id: str, entry_id: str, channel: str, ok: bool, note: str = "") -> MainLineEntry:
        entry = self._read(course_id, entry_id)
        if entry is None:
            raise ValueError(f"教材条目不存在：{entry_id}")
        record = {
            "channel": channel,
            "attempted_at": datetime.now(UTC).isoformat(),
            "ok": bool(ok),
            "note": note,
        }
        return self.update(course_id, entry_id, channels=entry.channels + (record,))

    def channel_stats(self) -> dict[str, dict[str, int]]:
        """跨全部课程条目聚合渠道成功/失败统计。"""
        stats: dict[str, dict[str, int]] = {}
        if not self.main_line_dir.is_dir():
            return stats
        for course_dir in self.main_line_dir.iterdir():
            for path in course_dir.glob("*.json"):
                entry = self._from_dict(json.loads(path.read_text(encoding="utf-8")))
                for channel in entry.channels:
                    name = channel.get("channel", "?")
                    bucket = stats.setdefault(name, {"ok": 0, "fail": 0})
                    if channel.get("ok"):
                        bucket["ok"] += 1
                    else:
                        bucket["fail"] += 1
        return stats
