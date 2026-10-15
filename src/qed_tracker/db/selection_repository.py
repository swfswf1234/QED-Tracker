"""Paper selection report persistence (qt_selections): REQ-032, replaces meta/selections/ JSON."""

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

# QED-068-3：v2 增量字段（plan_index/fetched/kept）折进 search_plan JSON 条目落盘，
# 顶层 plan_coverage 由读侧重建（零表结构改动，B-4 边界）。
SUPPORTED_SCHEMA_VERSIONS = {1, 2}


def plan_coverage_from_search_plan(search_plan: Any) -> list[dict[str, Any]]:
    if not isinstance(search_plan, list):
        return []
    coverage: list[dict[str, Any]] = []
    for entry in search_plan:
        if not isinstance(entry, dict) or "fetched" not in entry or "kept" not in entry:
            return []  # v1 旧契约无覆盖统计
        coverage.append(
            {
                "plan_index": entry.get("plan_index"),
                "terms": list(entry.get("terms") or []),
                "category": entry.get("category", ""),
                "fetched": entry.get("fetched", 0),
                "kept": entry.get("kept", 0),
            }
        )
    return coverage


class SelectionStoreError(RuntimeError):
    pass


def _scope_of(report: dict) -> dict:
    """报告 model JSON 里的探索 scope（domain_id/recipe）；无 scope 的历史报告返回空表。"""
    model = report.get("model")
    scope = model.get("scope") if isinstance(model, dict) else None
    return scope if isinstance(scope, dict) else {}


class SelectionStore:
    """Read/write layer for the qt_selections table (REQ-032)."""

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
        # QED-068 B 步：探索 scope（领域/配方）折进 model JSON 落盘（零表结构改动，
        # 与 plan_source 同法）；读侧由 load() 重建顶层 domain_id/recipe。
        scope = {
            "domain_id": str(report.get("domain_id") or ""),
            "recipe": str(report.get("recipe") or ""),
        }
        if any(scope.values()):
            model = dict(report.get("model") or {})
            model["scope"] = scope
            report["model"] = model
        # QED-068 C 步：查重双报清单折进 model JSON 落盘（零表结构改动，同 scope/plan_source 手法）。
        duplicates = report.get("duplicates")
        if isinstance(duplicates, dict) and any(duplicates.get(key) for key in ("same_content", "same_name")):
            folded_model = dict(report.get("model") or {})
            folded_model["duplicates"] = duplicates
            report["model"] = folded_model
        with self._new_session() as session:
            existing = session.get(QtSelection, selection_id)
            if existing is not None:
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
            report = row.to_dict()
        version = report.get("schema_version", 1)
        if version not in SUPPORTED_SCHEMA_VERSIONS:
            raise SelectionStoreError(f"不支持的报告 schema_version：{version}（支持 {sorted(SUPPORTED_SCHEMA_VERSIONS)}）")
        report.setdefault("plan_coverage", plan_coverage_from_search_plan(report.get("search_plan")))
        # QED-068-2：plan_source 折进 model JSON 落盘（零表结构改动），读侧重建顶层字段；
        # 无标记的历史报告按 llm 口径回填（S3 之前只有模型计划一条路径）。
        if not report.get("plan_source"):
            model = report.get("model") if isinstance(report.get("model"), dict) else {}
            report["plan_source"] = model.get("plan_source") or "llm"
        scope = report.get("model", {}).get("scope") if isinstance(report.get("model"), dict) else None
        scope = scope if isinstance(scope, dict) else {}
        report["domain_id"] = str(scope.get("domain_id") or "")
        report["recipe"] = str(scope.get("recipe") or "")
        # QED-068 C 步：顶层 duplicates 由 model JSON 重建（历史报告补空两桶，读侧形状恒定）。
        stored = report.get("model") if isinstance(report.get("model"), dict) else {}
        stored = stored.get("duplicates") if isinstance(stored.get("duplicates"), dict) else {}
        report["duplicates"] = {
            key: list(stored.get(key) or []) for key in ("same_content", "same_name")
        }
        return report

    def list(self, *, domain_id: str = "", recipe: str = "") -> list[dict[str, Any]]:
        """列报告摘要；`domain_id`/`recipe` 为 AND 过滤（空值不过滤，scope 取自 model JSON）。"""
        with self._new_session() as session:
            rows = session.execute(
                sa.select(QtSelection).order_by(QtSelection.created_at.desc())
            ).scalars().all()
            items = [row.to_dict() for row in rows]
        if not domain_id and not recipe:
            return items
        wanted = {"domain_id": domain_id, "recipe": recipe}
        return [
            item for item in items
            if all(
                not expected or _scope_of(item).get(key) == expected
                for key, expected in wanted.items()
            )
        ]

    def downloaded_arxiv_ids(self) -> set[str]:
        """QED-071 B-W3（D2/D14）：论文去重从 qt_selections.downloads 派生，资源岛不再是数据源。"""
        ids: set[str] = set()
        for report in self.list():
            for entry in report.get("downloads") or []:
                if entry.get("status") == "downloaded" and entry.get("arxiv_id"):
                    ids.add(str(entry["arxiv_id"]))
        return ids
