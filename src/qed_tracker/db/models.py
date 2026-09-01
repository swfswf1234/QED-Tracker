"""MySQL qed_*/qt_* 登记表（qed 库）的 ORM 模型与状态枚举（五层模型，QED-031）。

共享表（qed_*）：qed_domain / qed_course，所有权 QED-Tracker，其他项目只读；
私有表（qt_*）：qt_knowledge（一套教程/一组延展资料归类）→ qt_books（一册/一卷/一个快照）
→ qt_sources（渠道尝试）。旧三表模型（qt_selections/qt_downloads）已随 QED-031 退役。
qt_explore_runs / qt_prompt_runs 已随共享表重构（2026-08-27）退役。

DDL 事实源：docs/architecture/database-schema.md（唯一当前事实源）。
表/列中文注释事实源：migrations/data/table_comments.json（0007 迁移应用）。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class KnowledgeStatus(StrEnum):
    """qt_knowledge 教程生命周期：draft（探索中）→ confirmed（定稿）→ completed；终态 rejected/superseded。"""

    DRAFT = "draft"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class BookStatus(StrEnum):
    """qt_books 书籍四段状态机：candidate → decided → downloading → downloaded → verified；failed 可重试。"""

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

    domain_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="领域标识（主键）")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="领域名称")
    description: Mapped[str] = mapped_column(Text(), nullable=False, comment="学科介绍")
    level: Mapped[str] = mapped_column(String(50), nullable=False, default="", comment="探索范围")
    scope: Mapped[str] = mapped_column(Text(), nullable=False, default="", comment="学科知识")
    exploration_stage: Mapped[str] = mapped_column(String(20), nullable=False, default="未开始", comment="流程状态")
    classic_tracks: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, comment="课程方向")
    stages: Mapped[list[str]] = mapped_column(JSON, nullable=False, comment="学习阶段顺序")
    path_results: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="学习流程")
    explore_pending: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="探索待确认载荷（REQ-067-B12）")
    created_by: Mapped[str] = mapped_column(String(16), nullable=False, default="", comment="创建人")
    updated_by: Mapped[str] = mapped_column(String(16), nullable=False, default="", comment="最后更新人")
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, comment="更新时间")

    def to_dict(self) -> dict[str, Any]:
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            result[column.name] = value
        return result


class QedCourse(Base):
    """qed_course 课程（共享）：一门课程（含阶段/先修/别名/顺序）。"""

    __tablename__ = "qed_course"
    __table_args__ = ({"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},)

    course_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="课程标识（主键）")
    domain_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="所属领域")
    sort_order: Mapped[int] = mapped_column(Integer(), nullable=False, default=0, comment="学习顺序")
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="课程名称")
    aliases: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, comment="别名列表")
    track: Mapped[str] = mapped_column(String(50), nullable=False, default="", comment="课程所属学术方向")
    stage: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="所属阶段（本科基础/本科进阶/研究生基础/QE冲刺）"
    )
    prerequisites: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, comment="先修课程")
    related_targets: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, comment="已验收关联目标")
    description: Mapped[str] = mapped_column(String(1000), nullable=False, default="", comment="课程介绍")
    exploration_stage: Mapped[str] = mapped_column(String(20), nullable=False, default="未开始", comment="流程状态")
    explore_pending: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="探索待确认载荷（REQ-067-B12）")
    created_by: Mapped[str] = mapped_column(String(16), nullable=False, default="", comment="创建人")
    updated_by: Mapped[str] = mapped_column(String(16), nullable=False, default="", comment="最后更新人")
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, comment="更新时间")

    def to_dict(self) -> dict[str, Any]:
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            result[column.name] = value
        return result


class QtKnowledge(Base):
    """qt_knowledge 教程（私有）：一行 = 一套教程（tutorial）或一组课程延展资料归类（other_material）。"""

    __tablename__ = "qt_knowledge"
    __table_args__ = ({"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},)

    knowledge_id: Mapped[str] = mapped_column(String(100), primary_key=True, comment="教程标识（主键）")
    domain_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="所属领域")
    course_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="所属课程")
    kind: Mapped[str] = mapped_column(
        String(24), nullable=False, comment="类型（tutorial=教程套系；other_material=延展资料归类）"
    )
    set_no: Mapped[str] = mapped_column(
        String(4), nullable=False, default="", comment="套标记（1~4=中文套；en=英文套；空=无配套）"
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="", comment="名称")
    textbook_ref: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="教材决定引用")
    exercise_ref: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="习题集决定引用")
    textbook_intro: Mapped[str] = mapped_column(Text(), nullable=False, comment="教材简介")
    exercise_intro: Mapped[str] = mapped_column(Text(), nullable=False, comment="习题集简介")
    materials_intro: Mapped[str] = mapped_column(Text(), nullable=False, comment="延展资料简介")
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=KnowledgeStatus.DRAFT.value,
        index=True,
        comment="状态（draft=探索中；confirmed=已定稿；completed=已完成；rejected=已否决；superseded=已替代）",
    )
    reject_reason: Mapped[str] = mapped_column(String(1000), nullable=False, default="", comment="否决原因")
    supersede_reason: Mapped[str] = mapped_column(String(1000), nullable=False, default="", comment="替代原因")
    created_by: Mapped[str] = mapped_column(String(16), nullable=False, default="", comment="创建人")
    updated_by: Mapped[str] = mapped_column(String(16), nullable=False, default="", comment="最后更新人")
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, comment="创建时间")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, comment="定稿时间")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, comment="完成时间")
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, comment="否决时间")
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, comment="替代时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, comment="更新时间")

    def to_dict(self) -> dict[str, Any]:
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            result[column.name] = value
        return result


class QtBook(Base):
    """qt_books 书籍（私有）：一行 = 一册/一卷/一个快照（论文/博客）；候选→决定→下载→验证全生命周期。"""

    __tablename__ = "qt_books"
    __table_args__ = (
        UniqueConstraint("knowledge_id", "title", "part", name="uq_qt_books_knowledge_title_part"),
        UniqueConstraint("sha256", name="uq_qt_books_sha256"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    book_id: Mapped[str] = mapped_column(String(100), primary_key=True, comment="书籍标识（主键）")
    knowledge_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True, comment="所属教程")
    kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="类型（textbook=教材；exercise=习题集；supplement=补充；paper=论文；blog=博客；other=其他）",
    )
    roles: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, comment="角色（textbook=教材；exercise=习题集；solutions=解答）"
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False, comment="书名（不含卷）")
    part: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", comment="卷标识（空=整本；第一册/上册/博文序号）"
    )
    display_title: Mapped[str] = mapped_column(String(500), nullable=False, comment="展示名")
    file_name: Mapped[str] = mapped_column(String(500), nullable=False, default="", comment="落盘文件名")
    authors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, comment="作者")
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="", comment="语言")
    version: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, comment="版本信息")
    source: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="候选来源方案")
    original_url: Mapped[str] = mapped_column(String(1000), nullable=False, default="", comment="原始来源链接")
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="文件哈希")
    relative_path: Mapped[str] = mapped_column(String(500), nullable=False, default="", comment="相对数据根路径")
    absolute_path: Mapped[str] = mapped_column(String(1000), nullable=False, default="", comment="dataset 绝对路径")
    page_count: Mapped[int | None] = mapped_column(Integer(), nullable=True, comment="页数")
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=BookStatus.CANDIDATE.value,
        index=True,
        comment=(
            "状态（candidate=候选；decided=已决定；downloading=下载中；downloaded=已下载；"
            "verified=已验证；failed=失败；rejected=已否决；superseded=已替代）"
        ),
    )
    reject_reason: Mapped[str] = mapped_column(String(1000), nullable=False, default="", comment="否决原因")
    rejected_by: Mapped[str] = mapped_column(String(16), nullable=False, default="", comment="否决人")
    supersede_reason: Mapped[str] = mapped_column(String(1000), nullable=False, default="", comment="替代原因")
    review_note: Mapped[str] = mapped_column(String(1000), nullable=False, default="", comment="审理备注")
    created_by: Mapped[str] = mapped_column(String(16), nullable=False, default="", comment="创建人")
    updated_by: Mapped[str] = mapped_column(String(16), nullable=False, default="", comment="最后更新人")
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, comment="创建时间")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, comment="决定下载时间")
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, comment="下载完成时间")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, comment="验证通过时间")
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, comment="否决时间")
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, comment="替代时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, comment="更新时间")

    def to_dict(self) -> dict[str, Any]:
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            result[column.name] = value
        return result


class QtSource(Base):
    """qt_sources 渠道尝试（私有）：一次渠道尝试一条记录；失败尝试留痕不展示。"""

    __tablename__ = "qt_sources"
    __table_args__ = (
        # 显式索引名与设计文档 DDL 一致（ORM create 默认名 ix_qt_sources_book_id 不同）
        Index("ix_qt_sources_book", "book_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
    source_id: Mapped[str] = mapped_column(String(100), primary_key=True, comment="渠道标识（主键）")
    book_id: Mapped[str] = mapped_column(String(100), ForeignKey("qt_books.book_id"), nullable=False, comment="所属书籍")
    channel: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        comment=(
            "渠道（manual=人工；internet_archive=互联网档案馆；open_library=开放图书馆；"
            "google_books=谷歌图书；libgen_li=图书馆链接）"
        ),
    )
    provider_id: Mapped[str] = mapped_column(String(200), nullable=False, default="", comment="提供方标识")
    page_url: Mapped[str] = mapped_column(String(1000), nullable=False, default="", comment="页面地址")
    download_url: Mapped[str] = mapped_column(String(1000), nullable=False, default="", comment="下载地址")
    file_keywords: Mapped[str] = mapped_column(String(500), nullable=False, default="", comment="检索关键词")
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否成功（1=成功；0=失败）")
    note: Mapped[str] = mapped_column(String(1000), nullable=False, default="", comment="备注")
    attempted_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, comment="尝试时间")

    def to_dict(self) -> dict[str, Any]:
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            result[column.name] = value
        return result


class QtTask(Base):
    """qt_tasks 后台任务（私有，REQ-032）：一行一个后台任务记录，替代 meta/tasks/ JSON 文件。"""

    __tablename__ = "qt_tasks"
    __table_args__ = (
        Index("ix_qt_tasks_status", "status"),
        Index("ix_qt_tasks_type", "type"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    task_id: Mapped[str] = mapped_column(String(100), primary_key=True, comment="任务标识（主键）")
    type: Mapped[str] = mapped_column(String(50), nullable=False, comment="任务类型")
    status: Mapped[str] = mapped_column(String(24), nullable=False, comment="状态（queued/running/succeeded/failed）")
    params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, comment="任务参数")
    progress: Mapped[int] = mapped_column(Integer(), nullable=False, default=0, comment="进度（0-100）")
    message: Mapped[str] = mapped_column(Text(), nullable=False, default="", comment="当前状态消息")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="成功结果")
    error: Mapped[str] = mapped_column(Text(), nullable=False, default="", comment="失败错误信息")
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, comment="最后更新时间")

    def to_dict(self) -> dict[str, Any]:
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            result[column.name] = value
        return result


class QtSelection(Base):
    """qt_selections 论文选择报告（私有，REQ-032）：一行一个选择报告，替代 meta/selections/ JSON 文件。"""

    __tablename__ = "qt_selections"
    __table_args__ = (
        Index("ix_qt_selections_status", "status"),
        Index("ix_qt_selections_created_at", "created_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    selection_id: Mapped[str] = mapped_column(String(100), primary_key=True, comment="选择报告标识（主键）")
    schema_version: Mapped[int] = mapped_column(Integer(), nullable=False, comment="Schema 版本号")
    status: Mapped[str] = mapped_column(String(24), nullable=False, comment="状态（planning/no_candidates/completed/...）")
    created_at: Mapped[str] = mapped_column(String(50), nullable=False, comment="创建时间（ISO 格式）")
    profile: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="论文档案")
    temporary_goal: Mapped[str] = mapped_column(Text(), nullable=False, default="", comment="临时研究目标")
    allowed_categories: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="允许的 arXiv 分类")
    search_plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="搜索计划")
    search_failures: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="搜索失败记录")
    excluded_existing: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="已排除的已有 arXiv ID")
    candidates: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="候选论文列表")
    assessments: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="评估结果")
    recommendations: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="推荐列表")
    model: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="模型元数据")
    downloads: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="下载记录")
    error: Mapped[str] = mapped_column(Text(), nullable=False, default="", comment="失败错误信息（兼容 papers.py error 字段）")

    def to_dict(self) -> dict[str, Any]:
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            result[column.name] = value
        return result