"""论文选择报告的数据库持久化（REQ-032：替代 meta/selections/ JSON 文件）。"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from qed_tracker.db.models import QtSelection

SELECTION_ID_PATTERN = re.compile(r"^sel-\d{8}T\d{6}Z-[0-9a-f]{8}$")


class SelectionStoreError(RuntimeError):
    pass


class SelectionStore:
    """qt_selections 数据库表的读写层（REQ-032：替代 meta/selections/ JSON 文件）。"""

    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    def _new_session(self) -> Session:
        return self._session_factory()

    @staticmethod
    def new_id(now: datetime | None = None) -> str:
        moment = now or datetime.now(UTC)
        return f"sel-{moment.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"

    def save(self, report: dict[str, Any]) -> str:
        selection_id = str(report.get("selection_id") or "")
        if not SELECTION_ID_PATTERN.fullmatch(selection_id):
            raise ValueError("非法论文选择报告 ID")
        with self._new_session() as session:
            existing = session.get(QtSelection, selection_id)
            if existing is not None:
                # Update existing record
                for key in (
                    "schema_version", "status", "created_at", "profile", "temporary_goal",
                    "allowed_categories", "search_plan", "search_failures", "excluded_existing",
                    "candidates", "assessments", "recommendations", "model", "downloads", "error",
                ):
                    if key in report:
                        setattr(existing, key, report[key])
            else:
                row = QtSelection(
                    selection_id=selection_id,
                    schema_version=report.get("schema_version", 1),
                    status=report.get("status", ""),
                    created_at=report.get("created_at", datetime.now(UTC).isoformat()),
                    profile=report.get("profile"),
                    temporary_goal=report.get("temporary_goal", ""),
                    allowed_categories=report.get("allowed_categories"),
                    search_plan=report.get("search_plan"),
                    search_failures=report.get("search_failures"),
                    excluded_existing=report.get("excluded_existing"),
                    candidates=report.get("candidates"),
                    assessments=report.get("assessments"),
                    recommendations=report.get("recommendations"),
                    model=report.get("model"),
                    downloads=report.get("downloads"),
                    error=report.get("error", ""),
                )
                session.add(row)
            session.commit()
        return selection_id

    def load(self, selection_id: str) -> dict[str, Any]:
        if not SELECTION_ID_PATTERN.fullmatch(selection_id):
            raise ValueError("非法论文选择报告 ID")
        with self._new_session() as session:
            row = session.get(QtSelection, selection_id)
            if row is None:
                raise SelectionStoreError(f"论文选择报告不存在：{selection_id}")
            return row.to_dict()

    def list(self) -> list[dict[str, Any]]:
        with self._new_session() as session:
            rows = session.execute(
                sa.select(QtSelection).order_by(QtSelection.created_at.desc())
            ).scalars().all()
            return [row.to_dict() for row in rows]
