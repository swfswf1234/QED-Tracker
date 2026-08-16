"""MySQL qed_*/qt_* 登记表（qed 库）的 ORM 模型与状态枚举（五层模型，QED-031）。

共享表（qed_*）：qed_domain / qed_course，所有权 QED-Tracker，其他项目只读；
私有表（qt_*）：qt_knowledge（一套教程/一组延展资料归类）→ qt_books（一册/一卷/一个快照）
→ qt_sources（渠道尝试）。旧三表模型（qt_selections/qt_downloads）已随 QED-031 退役。

DDL 事实源：docs/design/database-schema.md（唯一当前事实源）。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class KnowledgeStatus(StrEnum):
    """qt_knowledge 知识行生命周期：draft（探索中）→ confirmed（定稿）→ completed；终态 rejected/superseded。"""

    DRAFT = "draft"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class BookStatus(StrEnum):
    """qt_books 书行四段状态机：candidate → decided → downloading → downloaded → verified；failed 可重试。"""

    CANDIDATE = "candidate"
    DECIDED = "decided"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    VERIFIED = "verified"
    FAILED = "failed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class Base(DeclarativeBase):
    pass


class QedDomain(Base):
    """qed_domain 领域（共享）：一行一个学科（math；预留扩展）。"""

    __tablename__ = "qed_domain"
    __table_args__ = ({"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},)

    domain_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    stages: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}


class QedCourse(Base):
    """qed_course 课程（共享）：一门课程（含阶段/先修/别名/顺序）。"""

    __tablename__ = "qed_course"
    __table_args__ = ({"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},)

    course_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    domain_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    prerequisites: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    related_targets: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    note: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}


class QtKnowledge(Base):
    """qt_knowledge 知识行（私有）：一行 = 一套教程（tutorial）或一组课程延展资料归类（other_material）。"""

    __tablename__ = "qt_knowledge"
    __table_args__ = ({"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},)

    knowledge_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    domain_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    course_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    set_no: Mapped[str] = mapped_column(String(4), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    textbook_ref: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    exercise_ref: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    textbook_intro: Mapped[str] = mapped_column(Text(), nullable=False)
    exercise_intro: Mapped[str] = mapped_column(Text(), nullable=False)
    materials_intro: Mapped[str] = mapped_column(Text(), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=KnowledgeStatus.DRAFT.value, index=True)
    reject_reason: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    supersede_reason: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}


class QtBook(Base):
    """qt_books 书行（私有）：一行 = 一册/一卷/一个快照（论文/博客）；候选→决定→下载→验证全生命周期。"""

    __tablename__ = "qt_books"
    __table_args__ = (
        UniqueConstraint("knowledge_id", "title", "part", name="uq_qt_books_knowledge_title_part"),
        UniqueConstraint("sha256", name="uq_qt_books_sha256"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    book_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    knowledge_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    roles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    part: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    display_title: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    authors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    version: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    source: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    original_url: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    relative_path: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    absolute_path: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    page_count: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=BookStatus.CANDIDATE.value, index=True)
    reject_reason: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    rejected_by: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    supersede_reason: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    review_note: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}


class QtSource(Base):
    """qt_sources 渠道尝试（私有）：一次渠道尝试一条记录；失败尝试留痕不展示。"""

    __tablename__ = "qt_sources"
    __table_args__ = ({"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},)

    source_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    book_id: Mapped[str] = mapped_column(String(100), ForeignKey("qt_books.book_id"), nullable=False, index=True)
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