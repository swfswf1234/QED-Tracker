"""一次性存量迁移：qt_resources + meta/resources JSON + 主链路 JSON → 三表（QED-028）。

映射规则事实源：docs/design/three-table-schema.md §一次性迁移。
- 分组：qt_resources 行按 (course_id, 套键) 分组；套键 = catalog_ref.target_id 剥离
  `-v\\d+` / `-answers` 卷后缀（`-zh`/`-en` 保留为独立版本条目）。
- 组内状态优先级：approved > downloaded > confirmed > pending_manual > candidate >
  backup > downloading/failed > not_found/rejected。
- 幂等：selection_id/download_id/source_id 确定性生成（md5），重跑覆盖既有行；
  成功标志 `meta/migrations/three_table.marker`（存在且未 --force 则跳过）。
- 主链路 JSON 迁移后**只备份不删除**（2026-08-13 用户裁决：备份快照确认后人工删除）。

本脚本不触发任何状态机迁移（三表初始化直接写入终态）；qt_resources 表与
meta/resources/ JSON 保持只读不动。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from qed_tracker.database import utc_now
from qed_tracker.db.models import QtDownload, QtResource, QtSelection, QtSource

_VOL_SUFFIX = re.compile(r"-(v\d+|answers)$")
_SOLUTION_HINTS = ("answer", "解答", "答案", "题解", "解析")

_STATUS_PRIORITY = {
    "approved": 0,
    "downloaded": 1,
    "confirmed": 2,
    "pending_manual": 3,
    "candidate": 4,
    "backup": 5,
    "downloading": 6,
    "failed": 6,
    "not_found": 7,
    "rejected": 7,
}

_SELECTION_STATUS_MAP = {
    "approved": "confirmed",
    "downloaded": "confirmed",
    "confirmed": "confirmed",
    "pending_manual": "candidate",
    "candidate": "candidate",
    "backup": "backup",
    "downloading": "candidate",
    "failed": "candidate",
    "not_found": "rejected",
    "rejected": "rejected",
}


@dataclass(frozen=True, slots=True)
class MigrationReport:
    selections: int
    downloads: int
    sources: int
    mainline_entries: int
    skipped: bool = False


def group_key(target_id: str) -> tuple[str, str]:
    """返回 (套键, 卷后缀)；-zh/-en 不归并（独立版本）。"""
    if not target_id:
        return "", ""
    match = _VOL_SUFFIX.search(target_id)
    if match:
        return target_id[: match.start()], match.group(1)
    return target_id, ""


def _vol_sort_key(vol: str):
    """数字卷（v1/v2）排在命名册（answers）前；空卷最前。"""
    if not vol:
        return (0, "")
    if re.match(r"v\d+$", vol):
        return (1, int(vol[1:]))
    return (2, vol)


def _id(prefix: str, *parts: Any) -> str:
    key = json.dumps(parts, ensure_ascii=False, sort_keys=True)
    return f"{prefix}_{__import__('hashlib').md5(key.encode('utf-8')).hexdigest()}"


def _load_meta_json(data_root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """meta/resources/*.json → {sha256: payload}；meta/main-line/**/*.json → 主链路条目。"""
    resources: dict[str, dict[str, Any]] = {}
    mainline: dict[str, dict[str, Any]] = {}
    resources_dir = data_root / "meta" / "resources"
    if resources_dir.is_dir():
        for path in resources_dir.glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            sha = (payload.get("file") or {}).get("sha256")
            if sha:
                resources[sha] = payload
    mainline_dir = data_root / "meta" / "main-line"
    if mainline_dir.is_dir():
        for path in mainline_dir.glob("*/*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            mainline[path.stem] = payload
    return resources, mainline


def migrate_legacy_to_three_table(session_factory, data_root: Path, *, force: bool = False) -> MigrationReport:
    data_root = Path(data_root)
    marker = data_root / "meta" / "migrations" / "three_table.marker"
    if marker.is_file() and not force:
        return MigrationReport(selections=0, downloads=0, sources=0, mainline_entries=0, skipped=True)

    meta_by_sha, mainline_entries = _load_meta_json(data_root)
    now = utc_now()

    with session_factory() as session:
        legacy_rows = list(session.scalars(select(QtResource)))
        grouped: dict[tuple[str, str], list[QtResource]] = {}
        for row in legacy_rows:
            catalog_ref = row.catalog_ref or {}
            target_id = catalog_ref.get("target_id", "") or ""
            course_id = catalog_ref.get("course_id", "") or row.title
            key, _vol = group_key(target_id)
            grouped.setdefault((course_id, key), []).append(row)

        selections = downloads = sources = 0
        for (course_id, key), rows in grouped.items():
            best = min(rows, key=lambda r: _STATUS_PRIORITY.get(r.status, 9))
            meta = meta_by_sha.get(best.sha256 or "", {}) if best.sha256 else None
            title = (meta or {}).get("title") or best.title
            # roles 权威来自 meta/resources JSON；无 meta 时按 kind 推导（QtResource 无 roles 列）
            roles = (meta or {}).get("roles") or _derive_roles(best.kind)
            version = {
                "edition": best.edition or "",
                "language": (meta or {}).get("language") or best.language,
                "year": (meta or {}).get("year") or best.year,
                "publisher": "",
                "detail": "",
            }
            file_rows = [r for r in rows if r.sha256 and r.status in ("approved", "downloaded")]
            vols = []
            for r in sorted(
                file_rows, key=lambda r: _vol_sort_key(group_key((r.catalog_ref or {}).get("target_id", ""))[1])
            ):
                _key, vol = group_key((r.catalog_ref or {}).get("target_id", ""))
                vols.append(vol or "")

            selection_id = _id("cand", course_id, key, title, version)
            selection = QtSelection(
                selection_id=selection_id,
                course_id=course_id,
                title=title,
                authors=best.authors or (list((meta or {}).get("authors") or [])),
                roles=roles,
                version=version,
                vols=vols,
                note=(best.review_note or "")[:1000],
                status=_SELECTION_STATUS_MAP.get(best.status, "candidate"),
                created_at=best.created_at or now,
            )
            if best.status in ("rejected", "not_found"):
                selection.reject_reason = best.reject_reason or (
                    "存量迁移：not_found 判定" if best.status == "not_found" else ""
                )
                selection.rejected_by = best.rejected_by
                selection.rejected_at = best.rejected_at or now
            if best.status in ("approved", "downloaded", "confirmed"):
                selection.confirmed_at = best.confirmed_at or best.created_at or now
            if best.llm_evaluation:
                selection.evaluation = best.llm_evaluation
            session.merge(selection)
            selections += 1

            for r in file_rows:
                _key, vol = group_key((r.catalog_ref or {}).get("target_id", ""))
                meta_r = meta_by_sha.get(r.sha256 or "", {})
                file_info = meta_r.get("file") or {}
                relative_path = file_info.get("relative_path") or r.relative_path
                page_count = file_info.get("page_count") or r.page_count
                vol_roles = meta_r.get("roles") or _derive_volume_roles(
                    vol, r.file_hint if hasattr(r, "file_hint") else "", r.kind, roles
                )
                download_id = _id("download", selection_id, vol, relative_path)
                download = QtDownload(
                    download_id=download_id,
                    selection_id=selection_id,
                    vol=vol,
                    roles=vol_roles,
                    file_hint=r.relative_path if hasattr(r, "relative_path") else "",
                    sha256=r.sha256,
                    relative_path=relative_path,
                    page_count=page_count,
                    status=r.status,
                    created_at=r.created_at or now,
                )
                if r.status == "approved":
                    download.approved_at = r.approved_at or now
                if r.status in ("approved", "downloaded"):
                    download.downloaded_at = r.downloaded_at or r.created_at or now
                session.merge(download)
                downloads += 1

                source = r.source or {}
                if source:
                    providers = {
                        "internet_archive": "internet_archive",
                        "open_library": "open_library",
                        "google_books": "google_books",
                        "libgen_li": "libgen_li",
                    }
                    source_id = _id(
                        "src",
                        download_id,
                        source.get("provider", "manual"),
                        source.get("provider_id", ""),
                        str(r.retrieved_at or now),
                    )
                    session.merge(
                        QtSource(
                            source_id=source_id,
                            download_id=download_id,
                            channel=providers.get(source.get("provider", ""), "manual"),
                            provider_id=str(source.get("provider_id", "")),
                            page_url=str(source.get("page_url", "")),
                            download_url=str(source.get("download_url", "")),
                            ok=1,
                            note=r.review_note[:1000] if r.review_note else "",
                            attempted_at=r.retrieved_at or now,
                        )
                    )
                    sources += 1

        mainline_count = _migrate_mainline(session, mainline_entries, now)
        mainline_entries_total = mainline_count

        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps(
                {
                    "migrated_at": now.isoformat(),
                    "selections": selections,
                    "downloads": downloads,
                    "sources": sources,
                    "mainline": mainline_entries_total,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        session.commit()

    return MigrationReport(
        selections=selections, downloads=downloads, sources=sources, mainline_entries=mainline_entries_total
    )


def _derive_roles(kind: str) -> list[str]:
    return {"book": ["textbook"], "exercise": ["exercises"], "supplement": ["solutions"]}.get(kind, [])


def _derive_volume_roles(vol: str, file_hint: str, kind: str, inherited: list[str]) -> list[str]:
    hint_text = f"{vol} {file_hint}".lower()
    if any(token in hint_text for token in _SOLUTION_HINTS):
        return ["solutions"]
    return inherited or _derive_roles(kind)


def _migrate_mainline(session: Session, entries: dict[str, dict[str, Any]], now: datetime) -> int:
    """主链路 JSON → 表1 条目 + channels[] → 表3。

    仅备份不删除（2026-08-13 用户裁决：备份快照确认后人工删除旧文件由 CLI/用户执行）。
    """
    imported = 0
    for entry_id, payload in entries.items():
        course_id = payload.get("course_id", "")
        title = payload.get("title", entry_id)
        version = payload.get("version", {})
        roles = payload.get("roles") or []
        status_map = {
            "reviewed": ("confirmed", None),
            "downloading": ("confirmed", "downloading"),
            "downloaded": ("confirmed", "downloaded"),
            "approved": ("confirmed", "approved"),
            "rejected": ("rejected", None),
            "draft": ("candidate", None),
        }
        selection_status, _download_status = status_map.get(payload.get("status", "draft"), ("candidate", None))
        selection_id = _id("cand", course_id, entry_id, title, version)
        session.merge(
            QtSelection(
                selection_id=selection_id,
                course_id=course_id,
                title=title,
                authors=list(payload.get("authors") or []),
                roles=roles,
                version=version or {},
                vols=[],
                note=(payload.get("advice") or {}).get("comment", "")[:1000]
                or (payload.get("advice") or {}).get("summary", "")[:1000],
                evaluation=payload.get("evaluation") or None,
                status=selection_status,
                created_at=now,
                confirmed_at=now if selection_status == "confirmed" else None,
            )
        )
        imported += 1
        final_path = payload.get("final_path", "")
        if final_path and payload.get("status") in ("downloaded", "approved"):
            download_id = _id("download", selection_id, "", final_path)
            download_status = "downloaded" if payload.get("status") == "downloaded" else "approved"
            session.merge(
                QtDownload(
                    download_id=download_id,
                    selection_id=selection_id,
                    vol="",
                    roles=roles,
                    relative_path=final_path,
                    status=download_status,
                    created_at=now,
                    downloaded_at=now,
                    approved_at=now if download_status == "approved" else None,
                )
            )
        for attempt in payload.get("channels") or []:
            channel = attempt.get("channel", "manual")
            source_id = _id(
                "src", download_id if final_path else selection_id, channel, str(attempt.get("attempted_at", ""))
            )
            session.merge(
                QtSource(
                    source_id=source_id,
                    download_id=download_id if final_path else "",
                    channel=channel,
                    ok=1 if attempt.get("ok") else 0,
                    note=str(attempt.get("note", ""))[:1000],
                    attempted_at=now,
                )
            )
    return imported
