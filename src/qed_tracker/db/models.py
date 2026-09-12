"""MySQL qed_*/qt_* 登记表（qed 库）的 ORM 模型与状态枚举。

共享表（qed_*）：qed_domain / qed_course，所有权 QED-Tracker，其他项目只读；
私有表（qt_*）：qt_knowledge（一套教程/一组延展资料归类）→ qt_books（书库：域级书库）
→ qt_sources（渠道尝试）。旧三表模型（qt_selections/qt_downloads）已随 QED-031 退役。
qt_explore_runs / qt_prompt_runs 已随共享表重构（2026-08-27）退役。

DDL 文档事实源：docs/architecture/database-shared-tables.md（共享表）与
docs/architecture/database-private-tables.md（专用表，ADR 0007 按表族拆分）。
表/列中文注释事实源：本模型 `comment=`（建表即带，ensure_schema 自愈后注释随模型；
v0.1 起弃用 migrations/data/table_comments.json，ADR 0006）。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class KnowledgeStatus(StrEnum):
    """qt_knowledge 教程状态（两态）：draft（探索中）→ confirmed（定稿）。"""

    DRAFT = "draft"
    CONFIRMED = "confirmed"


class BookStatus(StrEnum):
    """qt_books 选用状态 + 下载生命周期。"""

    # 选用四态（原有）
    CANDIDATE = "candidate"
    DECIDED = "decided"
    PARALLEL = "parallel"
    RETIRED = "retired"
    # 下载生命周期（新增）
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    VERIFIED = "verified"
    FAILED = "failed"


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
        String(32), nullable=False, comment="所属阶段（基础/主干/分支/前沿，qed_domain.stages 四档）"
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
    __table_args__ = (
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4",
         "comment": "教程表：登记一套教程或一组课程延展资料，承载套级简介与教材/习题集/平行读物引用数组，指引资源检索与补书决策"},
    )

    knowledge_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="教程标识（主键）：kt-{课程缩写}-{set_no}，服务端生成")
    course_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="所属课程标识")
    kind: Mapped[str] = mapped_column(
        String(24), nullable=False, comment="教程类型：tutorial=一套教程；other_material=课程延展资料归类"
    )
    set_no: Mapped[str] = mapped_column(String(4), nullable=False, default="", comment="套标记：1~4=中文套号；en=英文对照；空串=资料行")
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="教程名：格式「教程N：作者《书名》」")
    position: Mapped[str] = mapped_column(
        String(24), nullable=False,
        comment="学习阶段（套级）：beginner/intermediate/advanced/comprehensive/elective",
    )
    intro: Mapped[str] = mapped_column(Text(), nullable=False, comment="套级简介（散文，120~350字）")
    textbook_ref: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list, comment="教材引用数组"
    )
    exercise_ref: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True, comment="习题集引用数组；NULL=教材含习题"
    )
    parallel_ref: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True, comment="平行读物引用数组"
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=KnowledgeStatus.DRAFT.value,
        index=True, comment="审阅状态：draft=探索中；confirmed=定稿",
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, comment="人工定稿时间")
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True, comment="审阅备注或退役说明")
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


class QtBook(Base):
    """qt_books 书库（私有）：域级书库，一行 = 一册/一本书的选用状态与持有状态。"""

    __tablename__ = "qt_books"
    __table_args__ = (
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4",
         "comment": "书库表：域级书库，登记一册/一本书的选用状态与持有状态，承载补书优先级；下载执行由 qt_sources 承载"},
    )

    book_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="书籍标识（主键）：{课程缩写}-b{NN}，服务端生成")
    title: Mapped[str] = mapped_column(String(256), nullable=False, comment="书名（真实名称，支持 zh/en）")
    original_title: Mapped[str | None] = mapped_column(
        String(256), nullable=True,
        comment="原题（外文原版书名，支撑原版检索；无则 NULL）",
    )
    part: Mapped[str] = mapped_column(String(8), nullable=False, default="", comment="卷标识：空串=单卷本；上册/下册/Vol.1~3")
    authors: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list,
        comment='作者列表：[{name, role:"author|translator"}]',
    )
    publisher: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="出版社名称")
    edition: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="版本/版次")
    year: Mapped[int | None] = mapped_column(Integer(), nullable=True, comment="出版年份（未知填 NULL）")
    language: Mapped[str] = mapped_column(String(8), nullable=False, comment="主要语言：zh/en")
    roles: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list,
        comment='书籍角色：textbook/exercises/solutions',
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=BookStatus.CANDIDATE.value,
        index=True, comment="选用状态：decided/parallel/candidate/retired",
    )
    retire_reason: Mapped[str] = mapped_column(String(500), nullable=False, default="", comment="退役原因（retired 时必填）")
    holding: Mapped[str] = mapped_column(
        String(8), nullable=False, default="missing",
        index=True, comment="持有状态：owned=已到手；missing=未持有",
    )
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="PDF 文件路径（数据根相对）")
    priority: Mapped[int | None] = mapped_column(Integer(), nullable=True, index=True, comment="补书优先级：0=P0/1=P1/2=P2/NULL")
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True, comment="备注")
    domain_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", index=True, comment="所属领域标识")
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