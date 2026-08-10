"""qt_resources 状态机与查询索引的数据访问。

状态机（docs/design/tracker-service.md QED-012 + QED-017 人工评估三态）：
candidate → confirmed → downloading → downloaded → approved/rejected
            └──backup（备选）→ confirmed / rejected     └──failed → downloading（可重试）
pending_manual → confirmed（人工补书扫描）→ backup（挂备选）；not_found 为评估判定终态。

同 sha256 幂等；reject 必填原因并留痕；rejected 行永不删除。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from qed_tracker.database import utc_now
from qed_tracker.db.models import QtResource, ResourceStatus


class InvalidTransition(RuntimeError):
    """状态机非法迁移（API 层映射为 409）。"""


class RejectedSameSource(RuntimeError):
    """同 catalog_ref + title 的候选此前已被拒（评估任务跳过，不重复推荐）。"""


_TRANSITIONS: dict[ResourceStatus, set[ResourceStatus]] = {
    ResourceStatus.CANDIDATE: {ResourceStatus.CONFIRMED, ResourceStatus.REJECTED, ResourceStatus.PENDING_MANUAL, ResourceStatus.NOT_FOUND, ResourceStatus.BACKUP},
    ResourceStatus.CONFIRMED: {ResourceStatus.DOWNLOADING, ResourceStatus.REJECTED},
    ResourceStatus.DOWNLOADING: {ResourceStatus.DOWNLOADED, ResourceStatus.FAILED},
    ResourceStatus.DOWNLOADED: {ResourceStatus.APPROVED, ResourceStatus.REJECTED},
    ResourceStatus.FAILED: {ResourceStatus.DOWNLOADING},
    ResourceStatus.PENDING_MANUAL: {ResourceStatus.CONFIRMED, ResourceStatus.BACKUP},
    ResourceStatus.BACKUP: {ResourceStatus.CONFIRMED, ResourceStatus.REJECTED},
    ResourceStatus.APPROVED: set(),
    ResourceStatus.REJECTED: set(),
    ResourceStatus.NOT_FOUND: set(),
}


def _candidate_id(provider: str, provider_id: str, title: str, catalog_ref: dict | None = None) -> str:
    key = json.dumps([provider, provider_id, title, catalog_ref], ensure_ascii=False, sort_keys=True)
    return "cand_" + hashlib.md5(key.encode("utf-8")).hexdigest()


class ResourceRepository:
    """qt_resources 数据访问；session_factory 注入以便单元测试用 SQLite mock。"""

    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    # ---- 查询 ----

    def get(self, resource_id: str) -> QtResource | None:
        with self._session_factory() as session:
            return session.get(QtResource, resource_id)

    def list(
        self,
        *,
        status: str | None = None,
        course_id: str | None = None,
        kind: str | None = None,
        language: str | None = None,
    ) -> list[QtResource]:
        with self._session_factory() as session:
            statement = select(QtResource).order_by(QtResource.created_at)
            if status:
                statement = statement.where(QtResource.status == status)
            if course_id:
                statement = statement.where(QtResource.catalog_ref["course_id"].as_string() == course_id)
            if kind:
                statement = statement.where(QtResource.kind == kind)
            if language:
                statement = statement.where(QtResource.language == language)
            return list(session.scalars(statement))

    def exists_sha256(self, digest: str) -> bool:
        with self._session_factory() as session:
            return session.scalar(select(QtResource.resource_id).where(QtResource.sha256 == digest)) is not None

    def find_rejected_same_source(self, *, catalog_ref: dict | None, title: str) -> bool:
        """同 catalog_ref + title 已存在 rejected 行（评估任务据此跳过同源候选）。"""
        if not catalog_ref:
            return False
        with self._session_factory() as session:
            rows = session.scalars(select(QtResource).where(QtResource.status == ResourceStatus.REJECTED.value, QtResource.title == title))
            for row in rows:
                if row.catalog_ref and row.catalog_ref.get("catalog_id") == catalog_ref.get("catalog_id") and row.catalog_ref.get("target_id") == catalog_ref.get("target_id"):
                    return True
            return False

    def find_by_ref(self, catalog_ref: dict | None) -> QtResource | None:
        """按 catalog_ref（catalog_id + target_id + course_id）查找行，已决策行优先。

        评估任务据此判断目标是否已有人工决策（backup/approved/rejected/confirmed 等），
        避免把已决策行重置回 candidate（QED-017）。2026-08-09：同一目标可能存在
        旧的 pending_manual 行 + 新的已决策行（如 fikhtengolts-v2/v3），必须优先返回
        已决策行，否则评估会把 confirmed 行 upsert 降级回 candidate。
        """
        if not catalog_ref:
            return None
        decided = (
            ResourceStatus.CONFIRMED.value, ResourceStatus.APPROVED.value,
            ResourceStatus.DOWNLOADING.value, ResourceStatus.DOWNLOADED.value,
            ResourceStatus.BACKUP.value, ResourceStatus.REJECTED.value, ResourceStatus.FAILED.value,
        )
        with self._session_factory() as session:
            rows = session.scalars(select(QtResource))
            matches = [
                row for row in rows
                if row.catalog_ref and row.catalog_ref.get("catalog_id") == catalog_ref.get("catalog_id")
                and row.catalog_ref.get("target_id") == catalog_ref.get("target_id")
            ]
            if not matches:
                return None

            def _priority(row: QtResource) -> int:
                if row.status in decided:
                    return 0
                if row.status == ResourceStatus.CANDIDATE.value:
                    return 1
                return 2  # pending_manual / not_found（评估应重试并允许升级为 candidate）

            return min(matches, key=_priority)

    def find_candidate_by_ref(self, catalog_ref: dict | None) -> QtResource | None:
        """按 catalog_ref（catalog_id + target_id + course_id）查找候选行。"""
        if not catalog_ref:
            return None
        with self._session_factory() as session:
            rows = session.scalars(select(QtResource).where(QtResource.status == ResourceStatus.CANDIDATE.value))
            for row in rows:
                if row.catalog_ref and row.catalog_ref.get("catalog_id") == catalog_ref.get("catalog_id") and row.catalog_ref.get("target_id") == catalog_ref.get("target_id"):
                    return row
            return None

    # ---- 候选（评估任务落库） ----

    def upsert_candidate(
        self,
        *,
        title: str,
        authors: Iterable[str] = (),
        language: str = "",
        year: str = "",
        edition: str = "",
        kind: str = "book",
        source: dict[str, Any] | None = None,
        llm_evaluation: dict[str, Any] | None = None,
        catalog_ref: dict[str, str] | None = None,
    ) -> QtResource:
        provider = (source or {}).get("provider", "")
        provider_id = (source or {}).get("provider_id", "")
        resource_id = _candidate_id(provider, provider_id, title, catalog_ref)
        with self._session_factory() as session:
            row = session.get(QtResource, resource_id)
            if row is None:
                row = QtResource(resource_id=resource_id, kind=kind, title=title, created_at=utc_now())
                session.add(row)
            row.kind = kind
            row.title = title
            row.authors = list(authors)
            row.language = language
            row.year = year
            row.edition = edition
            row.source = source or {}
            if llm_evaluation is not None:
                row.llm_evaluation = llm_evaluation
            if catalog_ref is not None:
                row.catalog_ref = catalog_ref
            row.status = ResourceStatus.CANDIDATE.value
            session.commit()
            return row

    # ---- 状态迁移（带合法校验） ----

    def _set_status(self, resource_id: str, target: ResourceStatus, **fields: Any) -> QtResource:
        with self._session_factory() as session:
            row = session.get(QtResource, resource_id)
            if row is None:
                raise KeyError(f"资源不存在：{resource_id}")
            current = ResourceStatus(row.status)
            if target not in _TRANSITIONS[current]:
                raise InvalidTransition(f"状态迁移非法：{current.value} → {target.value}")
            row.status = target.value
            for key, value in fields.items():
                setattr(row, key, value)
            session.commit()
            return row

    def confirm(self, resource_id: str, *, note: str = "") -> QtResource:
        return self._set_status(resource_id, ResourceStatus.CONFIRMED, confirmed_at=utc_now(), review_note=note.strip())

    def mark_pending_manual(self, resource_id: str) -> QtResource:
        return self._set_status(resource_id, ResourceStatus.PENDING_MANUAL)

    def mark_not_found(self, resource_id: str) -> QtResource:
        return self._set_status(resource_id, ResourceStatus.NOT_FOUND)

    def mark_backup(self, resource_id: str, *, note: str = "") -> QtResource:
        """人工评估「备选」：不下载，可后续转正（confirm）或放弃（reject）。"""
        return self._set_status(resource_id, ResourceStatus.BACKUP, review_note=note.strip())

    def start_download(self, resource_id: str) -> QtResource:
        return self._set_status(resource_id, ResourceStatus.DOWNLOADING)

    def fail(self, resource_id: str) -> QtResource:
        return self._set_status(resource_id, ResourceStatus.FAILED)

    def approve(self, resource_id: str) -> QtResource:
        return self._set_status(resource_id, ResourceStatus.APPROVED, approved_at=utc_now())

    def reject(self, resource_id: str, *, reason: str, by: str, note: str = "") -> QtResource:
        if not reason.strip():
            raise ValueError("拒绝必须提供原因（reject_reason 必填）")
        return self._set_status(
            resource_id,
            ResourceStatus.REJECTED,
            rejected_at=utc_now(),
            reject_reason=reason.strip(),
            rejected_by=by,
            review_note=note.strip(),
        )

    def promote_from_manual(self, resource_id: str, *, sha256: str, relative_path: str, page_count: int) -> QtResource:
        return self._set_status(resource_id, ResourceStatus.CONFIRMED, sha256=sha256, relative_path=relative_path, page_count=page_count, confirmed_at=utc_now())

    # ---- 下载完成（回填 + 幂等 + 主键迁移） ----

    def complete_download(
        self,
        resource_id: str,
        *,
        sha256: str,
        relative_path: str,
        page_count: int,
    ) -> QtResource:
        """下载成功回填：cand_* 行迁移主键为 sha256:<digest>；同 sha256 已存在则复用既有行。"""
        final_id = f"sha256:{sha256}"
        with self._session_factory() as session:
            existing = session.scalar(select(QtResource).where(QtResource.sha256 == sha256))
            if existing is not None and existing.resource_id != resource_id:
                # 同内容已登记：移除本次候选行，复用既有行（幂等）
                row = session.get(QtResource, resource_id)
                if row is not None:
                    session.delete(row)
                session.commit()
                return existing
            row = session.get(QtResource, resource_id)
            if row is None:
                raise KeyError(f"资源不存在：{resource_id}；直接下载请用 upsert_downloaded")
            current = ResourceStatus(row.status)
            if current not in (
                ResourceStatus.DOWNLOADING,
                ResourceStatus.CONFIRMED,
                ResourceStatus.CANDIDATE,
                ResourceStatus.PENDING_MANUAL,  # QED-021：人工下载后登记直转 downloaded
            ):
                raise InvalidTransition(f"状态迁移非法：{current.value} → downloaded")
            if row.resource_id != final_id:
                # 主键迁移（无外键，直接 UPDATE 主键）
                session.execute(text("UPDATE qt_resources SET resource_id = :new WHERE resource_id = :old"), {"new": final_id, "old": row.resource_id})
                session.expire_all()
                row = session.get(QtResource, final_id)
            row.sha256 = sha256
            row.relative_path = relative_path
            row.page_count = page_count
            row.status = ResourceStatus.DOWNLOADED.value
            row.downloaded_at = utc_now()
            session.commit()
            return row

    def update_source(self, resource_id: str, source: dict[str, Any]) -> QtResource:
        """回填/更新来源信息（如下载时解析出的真实 download_url），保留其余列。"""
        with self._session_factory() as session:
            row = session.get(QtResource, resource_id)
            if row is None:
                raise KeyError(f"资源不存在：{resource_id}")
            row.source = source
            session.commit()
            return row

    def upsert_downloaded(
        self,
        *,
        resource_id: str,
        sha256: str,
        relative_path: str,
        page_count: int,
        kind: str,
        title: str,
        authors: Iterable[str] = (),
        language: str = "",
        year: str = "",
        edition: str = "",
        source: dict[str, Any] | None = None,
        catalog_ref: dict[str, str] | None = None,
    ) -> QtResource:
        """无候选行的直接下载（fetch-url / 老下载链路）双写入口：幂等 upsert。"""
        final_id = f"sha256:{sha256}"
        with self._session_factory() as session:
            existing = session.scalar(select(QtResource).where(QtResource.sha256 == sha256))
            if existing is not None:
                existing.kind = kind
                existing.title = title
                existing.authors = list(authors)
                existing.language = language
                existing.year = year
                existing.edition = edition
                existing.source = source or {}
                existing.relative_path = relative_path
                existing.page_count = page_count
                if catalog_ref is not None:
                    existing.catalog_ref = catalog_ref
                existing.status = ResourceStatus.DOWNLOADED.value
                existing.downloaded_at = utc_now()
                session.commit()
                return existing
            row = session.get(QtResource, resource_id)
            if row is not None and row.resource_id != final_id:
                session.execute(text("UPDATE qt_resources SET resource_id = :new WHERE resource_id = :old"), {"new": final_id, "old": row.resource_id})
                session.expire_all()
                row = session.get(QtResource, final_id)
            elif row is None:
                row = QtResource(resource_id=final_id, kind=kind, title=title, created_at=utc_now())
                session.add(row)
            row.kind = kind
            row.title = title
            row.authors = list(authors)
            row.language = language
            row.year = year
            row.edition = edition
            row.source = source or {}
            if catalog_ref is not None:
                row.catalog_ref = catalog_ref
            row.sha256 = sha256
            row.relative_path = relative_path
            row.page_count = page_count
            row.status = ResourceStatus.DOWNLOADED.value
            row.downloaded_at = utc_now()
            session.commit()
            return row
