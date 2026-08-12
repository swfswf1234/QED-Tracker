"""MySQL qt_* 登记表（qed 库）的 ORM 模型与状态枚举。

资源事实源仍为 `meta/resources/<sha256>.json`（schema 不变）；MySQL 为查询/展示索引，
双写一致性由 ResourceRegistry/ResourceRepository 保证（docs/design/tracker-service.md QED-012）。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ResourceStatus(StrEnum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"
    PENDING_MANUAL = "pending_manual"
    NOT_FOUND = "not_found"
    BACKUP = "backup"


class Base(DeclarativeBase):
    pass


class QtResource(Base):
    """qt_resources 查询索引；resource_id 候选期为 cand_<md5>，下载后迁移为 sha256:<digest>。"""

    __tablename__ = "qt_resources"
    __table_args__ = (
        UniqueConstraint("sha256", name="uq_qt_resources_sha256"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    resource_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    authors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    year: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    edition: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    source: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    relative_path: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    page_count: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=ResourceStatus.CANDIDATE.value, index=True)
    llm_evaluation: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    catalog_ref: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    reject_reason: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    rejected_by: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    review_note: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}
