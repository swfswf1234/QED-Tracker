"""三表模型（qt_selections / qt_downloads / qt_sources）数据访问与状态机。

结构（docs/design/three-table-schema.md，QED-028）：
表1 qt_selections 一条=一套书；表2 qt_downloads 册级；表3 qt_sources 渠道尝试。

状态机：
- 表1：candidate → confirmed / backup / rejected；confirmed → superseded；backup ⇄ confirmed。
  rejected / superseded 为终态（彻底隐藏：任何查询默认过滤）。
- 表2：candidate → downloading → downloaded；downloaded → approved / rejected；
  downloading → failed（可重试 → downloading）；candidate → downloaded 仅人工 register
  直转（QED-021 延续，需 sha256+path 非空）。approved / rejected 为终态（默认过滤）。

彻底隐藏语义在数据层实现（列表/详情接口默认过滤），前端不依赖展示层过滤。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from qed_tracker.database import utc_now
from qed_tracker.db.models import DownloadStatus, QtDownload, QtSelection, QtSource, SelectionStatus
from qed_tracker.db.repository import InvalidTransition

_HIDDEN_SELECTION_STATUSES = {SelectionStatus.REJECTED.value, SelectionStatus.SUPERSEDED.value}
_HIDDEN_DOWNLOAD_STATUSES = {DownloadStatus.REJECTED.value, DownloadStatus.FAILED.value}

_SELECTION_TRANSITIONS: dict[SelectionStatus, set[SelectionStatus]] = {
    SelectionStatus.CANDIDATE: {SelectionStatus.CONFIRMED, SelectionStatus.BACKUP, SelectionStatus.REJECTED},
    # backup ⇄ confirmed 可逆（2026-08-13 用户裁决 D9：与旧 qt_resources 三态语义一致）
    SelectionStatus.CONFIRMED: {SelectionStatus.BACKUP, SelectionStatus.REJECTED, SelectionStatus.SUPERSEDED},
    SelectionStatus.BACKUP: {SelectionStatus.CONFIRMED, SelectionStatus.REJECTED},
    SelectionStatus.REJECTED: set(),
    SelectionStatus.SUPERSEDED: set(),
}

_DOWNLOAD_TRANSITIONS: dict[DownloadStatus, set[DownloadStatus]] = {
    DownloadStatus.CANDIDATE: {DownloadStatus.DOWNLOADING, DownloadStatus.DOWNLOADED, DownloadStatus.REJECTED},
    DownloadStatus.DOWNLOADING: {DownloadStatus.DOWNLOADED, DownloadStatus.FAILED, DownloadStatus.REJECTED},
    DownloadStatus.DOWNLOADED: {DownloadStatus.APPROVED, DownloadStatus.REJECTED},
    DownloadStatus.FAILED: {DownloadStatus.DOWNLOADING, DownloadStatus.REJECTED},
    DownloadStatus.APPROVED: set(),
    DownloadStatus.REJECTED: set(),
}


def _id(prefix: str, *parts: Any) -> str:
    key = json.dumps(parts, ensure_ascii=False, sort_keys=True)
    return f"{prefix}_{hashlib.md5(key.encode('utf-8')).hexdigest()}"


class ThreeTableRepository:
    """三表数据访问；session_factory 注入以便单元测试用 SQLite mock。"""

    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    # ---------------- 表1 qt_selections ----------------

    def create_selection(
        self,
        *,
        course_id: str,
        title: str,
        authors: Iterable[str] = (),
        roles: Iterable[str] = (),
        version: dict[str, Any] | None = None,
        vols: Iterable[str] = (),
        set_no: str = "",
        evaluation: dict[str, Any] | None = None,
        note: str = "",
        selection_id: str = "",
    ) -> QtSelection:
        """幂等插入候选：候选期 selection_id = cand_<md5(course,title,version)>，确认后保持稳定。"""
        version = version or {}
        selection_id = selection_id or _id("cand", course_id, title, version)
        with self._session_factory() as session:
            row = session.get(QtSelection, selection_id)
            if row is None:
                row = QtSelection(
                    selection_id=selection_id,
                    course_id=course_id,
                    title=title,
                    created_at=utc_now(),
                )
                session.add(row)
            row.authors = list(authors)
            row.roles = list(roles)
            row.version = version
            row.vols = list(vols)
            row.set_no = set_no
            if evaluation is not None:
                row.evaluation = evaluation
            row.note = note
            session.commit()
            return row

    def list_selections(
        self,
        *,
        course_id: str | None = None,
        status: str | None = None,
        include_hidden: bool = False,
    ) -> list[QtSelection]:
        """默认彻底隐藏 rejected/superseded（数据层过滤；显式 status 查询同样受隐藏约束）。"""
        with self._session_factory() as session:
            statement = select(QtSelection).order_by(QtSelection.created_at)
            if course_id:
                statement = statement.where(QtSelection.course_id == course_id)
            if status:
                statement = statement.where(QtSelection.status == status)
            if not include_hidden:
                statement = statement.where(QtSelection.status.not_in(_HIDDEN_SELECTION_STATUSES))
            return list(session.scalars(statement))

    def get_selection(self, selection_id: str, *, include_hidden: bool = False) -> QtSelection | None:
        with self._session_factory() as session:
            row = session.get(QtSelection, selection_id)
            if row is None:
                return None
            if not include_hidden and row.status in _HIDDEN_SELECTION_STATUSES:
                return None
            return row

    def _transition_selection(self, selection_id: str, target: SelectionStatus, **fields: Any) -> QtSelection:
        with self._session_factory() as session:
            row = session.get(QtSelection, selection_id)
            if row is None:
                raise KeyError(f"选课条目不存在：{selection_id}")
            current = SelectionStatus(row.status)
            if target not in _SELECTION_TRANSITIONS[current]:
                raise InvalidTransition(f"选课状态迁移非法：{current.value} → {target.value}")
            row.status = target.value
            for key, value in fields.items():
                setattr(row, key, value)
            session.commit()
            return row

    def confirm_selection(self, selection_id: str, *, note: str = "") -> QtSelection:
        """candidate → confirmed 或 backup → confirmed（backup 转正，可逆）。"""
        return self._transition_selection(
            selection_id,
            SelectionStatus.CONFIRMED,
            confirmed_at=utc_now(),
            note=note.strip(),
        )

    def backup_selection(self, selection_id: str, *, note: str = "") -> QtSelection:
        """candidate → backup（备选；可后续转正或放弃）。"""
        return self._transition_selection(selection_id, SelectionStatus.BACKUP, note=note.strip())

    def reject_selection(self, selection_id: str, *, reason: str, by: str) -> QtSelection:
        """candidate/confirmed/backup → rejected（必填原因，彻底隐藏）。"""
        if not reason.strip():
            raise ValueError("拒绝必须提供原因（reject_reason 必填）")
        return self._transition_selection(
            selection_id,
            SelectionStatus.REJECTED,
            rejected_at=utc_now(),
            reject_reason=reason.strip(),
            rejected_by=by,
        )

    def supersede_selection(self, selection_id: str, *, reason: str, by: str) -> QtSelection:
        """confirmed → superseded（被新版本替代，保留留痕，彻底隐藏）。"""
        if not reason.strip():
            raise ValueError("过时必须提供原因（supersede_reason 必填）")
        return self._transition_selection(
            selection_id,
            SelectionStatus.SUPERSEDED,
            superseded_at=utc_now(),
            supersede_reason=reason.strip(),
            rejected_by=by,
        )

    # ---------------- 表2 qt_downloads ----------------

    def create_download(
        self,
        selection_id: str,
        *,
        vol: str = "",
        file_hint: str = "",
        roles: list[str] | None = None,
    ) -> QtDownload:
        """新建表2 候选册（幂等：同 selection+vol+file_hint 复用既有行）。

        册级 roles 默认继承表1 套级 roles；显式 roles 覆盖（如 answers → ["solutions"]）。
        """
        download_id = _id("download", selection_id, vol, file_hint)
        with self._session_factory() as session:
            row = session.get(QtDownload, download_id)
            if row is None:
                selection = session.get(QtSelection, selection_id)
                if selection is None:
                    raise KeyError(f"选课条目不存在：{selection_id}")
                if roles is None:
                    roles = selection.roles or []
                row = QtDownload(
                    download_id=download_id,
                    selection_id=selection_id,
                    vol=vol,
                    roles=roles,
                    file_hint=file_hint,
                    created_at=utc_now(),
                )
                session.add(row)
            elif roles is not None:
                row.roles = roles
            session.commit()
            return row

    def list_downloads(self, selection_id: str | None = None, *, include_hidden: bool = False) -> list[QtDownload]:
        """默认隐藏 rejected/failed（数据层过滤）。"""
        with self._session_factory() as session:
            statement = select(QtDownload).order_by(QtDownload.created_at)
            if selection_id:
                statement = statement.where(QtDownload.selection_id == selection_id)
            if not include_hidden:
                statement = statement.where(QtDownload.status.not_in(_HIDDEN_DOWNLOAD_STATUSES))
            return list(session.scalars(statement))

    def get_download(self, download_id: str, *, include_hidden: bool = False) -> QtDownload | None:
        with self._session_factory() as session:
            row = session.get(QtDownload, download_id)
            if row is None:
                return None
            if not include_hidden and row.status in _HIDDEN_DOWNLOAD_STATUSES:
                return None
            return row

    def _transition_download(
        self, download_id: str, target: DownloadStatus, *, require_filed: bool = False, **fields: Any
    ) -> QtDownload:
        with self._session_factory() as session:
            row = session.get(QtDownload, download_id)
            if row is None:
                raise KeyError(f"下载明细不存在：{download_id}")
            current = DownloadStatus(row.status)
            if target not in _DOWNLOAD_TRANSITIONS[current]:
                raise InvalidTransition(f"下载状态迁移非法：{current.value} → {target.value}")
            if require_filed and not (row.sha256 and row.relative_path):
                raise InvalidTransition("进入 downloaded 前必须已登记 sha256 + relative_path")
            row.status = target.value
            for key, value in fields.items():
                setattr(row, key, value)
            session.commit()
            return row

    def start_download(self, download_id: str) -> QtDownload:
        """candidate → downloading（任务发起）；failed → downloading（重试）。"""
        return self._transition_download(download_id, DownloadStatus.DOWNLOADING)

    def fail_download(self, download_id: str) -> QtDownload:
        """downloading → failed（仅下载中可失败；candidate→failed 不允许）。"""
        return self._transition_download(download_id, DownloadStatus.FAILED)

    def retry_download(self, download_id: str) -> QtDownload:
        """failed → downloading（重试）。"""
        return self._transition_download(download_id, DownloadStatus.DOWNLOADING)

    def complete_download(
        self,
        download_id: str,
        *,
        sha256: str,
        relative_path: str,
        page_count: int | None = None,
    ) -> QtDownload:
        """downloading → downloaded（自动任务）或 candidate → downloaded（人工 register 直转）。

        两者均要求已提供 sha256 + relative_path。同 sha256 幂等：已存在同 sha256 行则复用。
        """
        with self._session_factory() as session:
            existing = session.scalar(select(QtDownload).where(QtDownload.sha256 == sha256))
            if existing is not None and existing.download_id != download_id:
                row = session.get(QtDownload, download_id)
                if row is not None:
                    session.delete(row)
                session.commit()
                return existing
            row = session.get(QtDownload, download_id)
            if row is None:
                raise KeyError(f"下载明细不存在：{download_id}")
            current = DownloadStatus(row.status)
            if current not in (DownloadStatus.DOWNLOADING, DownloadStatus.CANDIDATE):
                raise InvalidTransition(f"下载状态迁移非法：{current.value} → downloaded")
            row.sha256 = sha256
            row.relative_path = relative_path
            if page_count is not None:
                row.page_count = page_count
            row.status = DownloadStatus.DOWNLOADED.value
            row.downloaded_at = utc_now()
            session.commit()
            return row

    def approve_download(self, download_id: str) -> QtDownload:
        """downloaded → approved（册级验收通过）。"""
        return self._transition_download(download_id, DownloadStatus.APPROVED, approved_at=utc_now())

    def reject_download(self, download_id: str, *, reason: str, by: str, note: str = "") -> QtDownload:
        """candidate/downloading/downloaded → rejected（必填原因；文件硬删由调用方执行）。"""
        if not reason.strip():
            raise ValueError("拒绝必须提供原因（reject_reason 必填）")
        return self._transition_download(
            download_id,
            DownloadStatus.REJECTED,
            rejected_at=utc_now(),
            reject_reason=reason.strip(),
            rejected_by=by,
            review_note=note.strip(),
        )

    # ---------------- 表3 qt_sources ----------------

    def add_source(
        self,
        download_id: str,
        *,
        channel: str,
        provider_id: str = "",
        page_url: str = "",
        download_url: str = "",
        file_keywords: str = "",
        ok: bool = False,
        note: str = "",
        attempted_at=None,
    ) -> QtSource:
        """记录一次渠道尝试（人工 manual 或自动来源）；失败尝试留痕不展示。"""
        attempted_at = attempted_at or utc_now()
        source_id = _id("src", download_id, channel, provider_id, str(attempted_at))
        with self._session_factory() as session:
            row = session.get(QtSource, source_id)
            if row is None:
                row = QtSource(source_id=source_id, download_id=download_id, channel=channel, attempted_at=attempted_at)
                session.add(row)
            row.provider_id = provider_id
            row.page_url = page_url
            row.download_url = download_url
            row.file_keywords = file_keywords
            row.ok = ok
            row.note = note
            session.commit()
            return row

    def list_sources(self, download_id: str, *, ok_only: bool = False) -> list[QtSource]:
        with self._session_factory() as session:
            statement = select(QtSource).where(QtSource.download_id == download_id).order_by(QtSource.attempted_at)
            if ok_only:
                from sqlalchemy import true

                statement = statement.where(QtSource.ok == true())
            return list(session.scalars(statement))
