"""论文选择报告的本地原子存储。"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SELECTION_ID_PATTERN = re.compile(r"^sel-\d{8}T\d{6}Z-[0-9a-f]{8}$")


class SelectionStoreError(RuntimeError):
    pass


class SelectionStore:
    def __init__(self, data_root: Path):
        self.root = data_root.resolve() / "meta" / "selections"

    @staticmethod
    def new_id(now: datetime | None = None) -> str:
        moment = now or datetime.now(UTC)
        return f"sel-{moment.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"

    def save(self, report: dict[str, Any]) -> Path:
        selection_id = str(report.get("selection_id") or "")
        if not SELECTION_ID_PATTERN.fullmatch(selection_id):
            raise ValueError("非法论文选择报告 ID")
        target = self.root / f"{selection_id}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".json.tmp")
        payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, target)
        return target

    def load(self, selection_id: str) -> dict[str, Any]:
        if not SELECTION_ID_PATTERN.fullmatch(selection_id):
            raise ValueError("非法论文选择报告 ID")
        target = self.root / f"{selection_id}.json"
        if not target.is_file():
            raise SelectionStoreError(f"论文选择报告不存在：{selection_id}")
        try:
            value = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SelectionStoreError(f"论文选择报告损坏：{selection_id}") from exc
        if value.get("selection_id") != selection_id or value.get("schema_version") != 1:
            raise SelectionStoreError(f"论文选择报告损坏：{selection_id}")
        return value

    def list(self) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        reports = [self.load(path.stem) for path in self.root.glob("sel-*.json")]
        return sorted(reports, key=lambda item: (str(item.get("created_at", "")), item["selection_id"]), reverse=True)
