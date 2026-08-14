"""MySQL qt_* 登记表（qed 库）的 ORM 模型与状态枚举（三表模型，QED-028）。

表1 qt_selections 选课表/书单；表2 qt_downloads 册级明细；表3 qt_sources 渠道尝试。
旧 qt_resources 查询索引已于 QED-030 退役（0005 迁移 drop）。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class SelectionStatus(StrEnum):
    """表1 qt_selections 生命周期（三表模型，QED-028）：候选=表1 生命周期。"""

    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    BACKUP = "backup"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class DownloadStatus(StrEnum):
    """表2 qt_downloads 册级状态机：验收（approve/reject）在表2。"""

    CANDIDATE = "candidate"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


class Base(DeclarativeBase):
    pass


class QtSelection(Base):
    """qt_selections 选课表/书单（表1）：一条=一套书，候选/确认/备选/否定/过时生命周期。"""

    __tablename__ = "qt_selections"
    __table_args__ = ({"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},)

    selection_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    course_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    authors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    roles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    version: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    vols: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    set_no: Mapped[str] = mapped_column(String(4), nullable=False, default="")
    evaluation: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    note: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=SelectionStatus.CANDIDATE.value, index=True)
    reject_reason: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    rejected_by: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    supersede_reason: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    def to_dict(self) -> dict[str, Any]:
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}


class QtDownload(Base):
    """qt_downloads 册级下载明细（表2）：一册一个文件，验收（approve/reject）发生在本层。"""

    __tablename__ = "qt_downloads"
    __table_args__ = (
        UniqueConstraint("sha256", name="uq_qt_downloads_sha256"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    download_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    selection_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    vol: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    roles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    file_hint: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    relative_path: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    page_count: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=DownloadStatus.CANDIDATE.value, index=True)
    reject_reason: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    rejected_by: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    review_note: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    intro: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    def to_dict(self) -> dict[str, Any]:
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}


class QtSource(Base):
    """qt_sources 渠道尝试（表3）：一次渠道尝试一条记录；失败留痕不展示。"""

    __tablename__ = "qt_sources"
    __table_args__ = ({"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},)

    source_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    download_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    page_url: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    download_url: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    file_keywords: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    attempted_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}
