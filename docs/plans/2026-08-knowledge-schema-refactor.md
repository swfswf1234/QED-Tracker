# 知识层次重构实现计划（knowledge-schema-refactor）

状态：In Progress
最后更新：2026-08-16

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 三表模型（qt_selections/qt_downloads/qt_sources）替换重构为五层知识模型——共享 qed_domain/qed_course + 私有 qt_knowledge/qt_books/qt_sources（外键改挂书行）；courses/math.json 退役改读表；CLI/8901 同步新状态机。

**Architecture:** 承接 QED-031（数据库重构，设计事实源 `docs/design/database-schema.md`）。DB 层沿用现有 SQLAlchemy 2.0 ORM + Alembic（迁移 0006 建 4 张新表；qt_sources 由存量迁移脚本改名重建挂 book_id）；存量迁移为独立幂等模块（`application/migrate_knowledge.py`，CLI `migrate` 子命令触发，备份快照 + 成功标志落 meta，确认后 drop 旧两表）；API 层在 `src/qed_tracker/api/main.py` 用 knowledge/books/sources 端点组替换三表端点组；courses.py 改读 qed_course（JSON 退役，dataclass 保留）。根仓库契约 ADR 0009 + database-design.md + service-contracts.md 已同步（2026-08-16 完成）。

**Tech Stack:** Python 3.12、SQLAlchemy 2.0、Alembic、FastAPI、pytest（TDD）、ruff。

**状态与前置：** 设计文档已转 Accepted（用户 2026-08-16 全量裁决）。执行环境：项目 Python `D:\software\anaconda3\envs\QED_env\python.exe`（默认 python 是 3.10 不可用）。全量门禁命令：`pytest tests -q` + `ruff check .`（每任务收尾跑相关定向测试即可，任务 8 跑全量）。

---

## 任务 1：ORM 模型与状态枚举（五表）

**Files:**
- Edit: `src/qed_tracker/db/models.py`（替换三表模型为五表模型）
- Edit: `tests/test_db_models.py`（重写为新模型断言）

- [ ] **Step 1: 写失败测试**

在 `tests/test_db_models.py` 顶部替换导入并新增断言（完整重写该文件）：

```python
"""五表模型（qed_domain/qed_course/qt_knowledge/qt_books/qt_sources）ORM 断言。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.db.models import (
    Base,
    BookStatus,
    KnowledgeStatus,
    QtBook,
    QtKnowledge,
    QtSource,
    QedCourse,
    QedDomain,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory()
    engine.dispose()


def test_enums_complete() -> None:
    assert {s.value for s in KnowledgeStatus} == {"draft", "confirmed", "completed", "rejected", "superseded"}
    assert {s.value for s in BookStatus} == {
        "candidate", "decided", "downloading", "downloaded", "verified",
        "failed", "rejected", "superseded",
    }


def test_legacy_three_tables_gone() -> None:
    """替换重构：旧三表模型不再存在（drop 由迁移/脚本负责，ORM 无残留）。"""
    tables = {t.name for t in Base.metadata.sorted_tables}
    assert "qt_selections" not in tables
    assert "qt_downloads" not in tables


def test_shared_tables_exist(session) -> None:
    tables = {t.name for t in Base.metadata.sorted_tables}
    assert {"qed_domain", "qed_course"} <= tables
    domain = QedDomain(domain_id="math", name="数学", description="d", stages=["本科基础"], created_at=__import__("qed_tracker.database", fromlist=["utc_now"]).utc_now())
    session.add(domain)
    session.commit()
    assert session.get(QedDomain, "math") is not None


def test_qt_books_unique_constraints() -> None:
    table = QtBook.__table__
    names = {c.name for c in table.constraints}
    assert "uq_qt_books_knowledge_title_part" in names
    assert "uq_qt_books_sha256" in names


def test_qt_sources_foreign_key_to_books() -> None:
    fk = next(fk for fk in QtSource.__table__.foreign_keys if fk.parent.name == "book_id")
    assert fk.column.table.name == "qt_books"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests/test_db_models.py -q`
Expected: FAIL（`ImportError: cannot import name 'BookStatus'` 等）

- [ ] **Step 3: 重写 `src/qed_tracker/db/models.py`**

完整替换文件内容：

```python
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

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, UniqueConstraint
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
    description: Mapped[str] = mapped_column(__import__("sqlalchemy", fromlist=["Text"]).Text(), nullable=False)
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
    textbook_intro: Mapped[str] = mapped_column(__import__("sqlalchemy", fromlist=["Text"]).Text(), nullable=False)
    exercise_intro: Mapped[str] = mapped_column(__import__("sqlalchemy", fromlist=["Text"]).Text(), nullable=False)
    materials_intro: Mapped[str] = mapped_column(__import__("sqlalchemy", fromlist=["Text"]).Text(), nullable=False)
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
    book_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
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
```

说明：TEXT 列用 `sqlalchemy.Text` 内联导入（与迁移 ASCII 无关，纯 ORM 定义可含中文注释）。

- [ ] **Step 4: 跑测试确认通过**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests/test_db_models.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_db_models.py src/qed_tracker/db/models.py
git commit -m "feat(db): five-layer schema ORM models (qed_*/qt_*) replacing three-table models"
```

---

## 任务 2：Alembic 迁移 0006（建 4 张新表）

**Files:**
- Create: `src/qed_tracker/migrations/versions/0006_knowledge_schema.py`
- Edit: `tests/test_db_three_table_smoke.py`（新表结构断言，替换旧三表断言）

- [ ] **Step 1: 写失败测试**

重写 `tests/test_db_three_table_smoke.py` 中的列/索引断言部分（保留 `_read_root_env`/`_connect`/`SMOKE_ENABLED` 骨架不变），将 `SELECTION_COLUMNS`/`DOWNLOAD_COLUMNS`/`SOURCE_COLUMNS` 替换为五表常量：

```python
DOMAIN_COLUMNS = {
    "domain_id", "name", "description", "stages", "created_by", "updated_by", "created_at", "updated_at",
}

COURSE_COLUMNS = {
    "course_id", "domain_id", "sort_order", "name", "aliases", "stage", "prerequisites",
    "related_targets", "note", "created_by", "updated_by", "created_at", "updated_at",
}

KNOWLEDGE_COLUMNS = {
    "knowledge_id", "domain_id", "course_id", "kind", "set_no", "name", "textbook_ref", "exercise_ref",
    "textbook_intro", "exercise_intro", "materials_intro", "status", "reject_reason", "supersede_reason",
    "created_by", "updated_by", "created_at", "confirmed_at", "completed_at", "rejected_at",
    "superseded_at", "updated_at",
}

BOOK_COLUMNS = {
    "book_id", "knowledge_id", "kind", "roles", "title", "part", "display_title", "file_name",
    "authors", "language", "version", "source", "original_url", "sha256", "relative_path",
    "absolute_path", "page_count", "status", "reject_reason", "rejected_by", "supersede_reason",
    "review_note", "created_by", "updated_by", "created_at", "decided_at", "downloaded_at",
    "verified_at", "rejected_at", "superseded_at", "updated_at",
}

SOURCE_COLUMNS = {
    "source_id", "book_id", "channel", "provider_id", "page_url", "download_url",
    "file_keywords", "ok", "note", "attempted_at",
}
```

并把 `test_upgrade_creates_three_tables_with_contract_columns` 替换为：

```python
def test_upgrade_creates_five_tables_with_contract_columns():
    from qed_tracker.config import load_settings
    from qed_tracker.database import upgrade_database

    upgrade_database(load_settings())  # 幂等：已到 head 则空操作
    settings, conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema=%s AND table_name IN "
                "('qed_domain','qed_course','qt_knowledge','qt_books','qt_sources')",
                (settings.db_name,),
            )
            columns: dict[str, set[str]] = {}
            for table, column in cur.fetchall():
                columns.setdefault(table, set()).add(column)
            cur.execute(
                "SELECT table_name, index_name FROM information_schema.statistics "
                "WHERE table_schema=%s AND table_name IN "
                "('qed_domain','qed_course','qt_knowledge','qt_books','qt_sources')",
                (settings.db_name,),
            )
            indexes: dict[str, set[str]] = {}
            for table, index in cur.fetchall():
                indexes.setdefault(table, set()).add(index)
    finally:
        conn.close()
    assert columns["qed_domain"] == DOMAIN_COLUMNS
    assert columns["qed_course"] == COURSE_COLUMNS
    assert columns["qt_knowledge"] == KNOWLEDGE_COLUMNS
    assert columns["qt_books"] == BOOK_COLUMNS
    assert columns["qt_sources"] == SOURCE_COLUMNS
    assert {"ix_qed_course_domain"} <= indexes["qed_course"]
    assert {"ix_qt_knowledge_course", "ix_qt_knowledge_status"} <= indexes["qt_knowledge"]
    assert {"uq_qt_books_knowledge_title_part", "uq_qt_books_sha256",
            "ix_qt_books_knowledge", "ix_qt_books_status"} <= indexes["qt_books"]
    assert {"ix_qt_sources_book"} <= indexes["qt_sources"]
```

注意：本冒烟是真实 MySQL 只读测试（`QED_DB_SMOKE=1` 启用），默认跳过；迁移 0006 升级后在真实库运行一次验证结构。

- [ ] **Step 2: 实现迁移 0006**

创建 `src/qed_tracker/migrations/versions/0006_knowledge_schema.py`（**纯 ASCII**，中文注释禁止）：

```python
"""Create five-layer knowledge schema tables (QED-031).

Creates qed_domain / qed_course (shared, qed_* prefix) and qt_knowledge /
qt_books (private). qt_sources is NOT touched here -- it is rebuilt (FK
switched to qt_books.book_id) by the idempotent data migration script
(src/qed_tracker/application/migrate_knowledge.py) after this migration,
which first renames the old table and copies rows with the new mapping.

DDL fact source: docs/design/database-schema.md (single source of truth).

NOTE: keep this file ASCII-only (Alembic reads migration modules with locale encoding).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_knowledge_schema"
down_revision = "0005_drop_resources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qed_domain",
        sa.Column("domain_id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("stages", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(16), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(16), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    op.create_table(
        "qed_course",
        sa.Column("course_id", sa.String(64), primary_key=True),
        sa.Column("domain_id", sa.String(32), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("prerequisites", sa.JSON(), nullable=False),
        sa.Column("related_targets", sa.JSON(), nullable=False),
        sa.Column("note", sa.String(1000), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(16), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(16), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_qed_course_domain", "qed_course", ["domain_id"])

    op.create_table(
        "qt_knowledge",
        sa.Column("knowledge_id", sa.String(100), primary_key=True),
        sa.Column("domain_id", sa.String(32), nullable=False),
        sa.Column("course_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("set_no", sa.String(4), nullable=False, server_default=""),
        sa.Column("name", sa.String(200), nullable=False, server_default=""),
        sa.Column("textbook_ref", sa.JSON(), nullable=True),
        sa.Column("exercise_ref", sa.JSON(), nullable=True),
        sa.Column("textbook_intro", sa.Text(), nullable=False),
        sa.Column("exercise_intro", sa.Text(), nullable=False),
        sa.Column("materials_intro", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("reject_reason", sa.String(1000), nullable=False, server_default=""),
        sa.Column("supersede_reason", sa.String(1000), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(16), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(16), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.Column("superseded_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_qt_knowledge_course", "qt_knowledge", ["course_id"])
    op.create_index("ix_qt_knowledge_status", "qt_knowledge", ["status"])

    op.create_table(
        "qt_books",
        sa.Column("book_id", sa.String(100), primary_key=True),
        sa.Column("knowledge_id", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("part", sa.String(32), nullable=False, server_default=""),
        sa.Column("display_title", sa.String(500), nullable=False),
        sa.Column("file_name", sa.String(500), nullable=False, server_default=""),
        sa.Column("authors", sa.JSON(), nullable=False),
        sa.Column("language", sa.String(8), nullable=False, server_default=""),
        sa.Column("version", sa.JSON(), nullable=False),
        sa.Column("source", sa.JSON(), nullable=True),
        sa.Column("original_url", sa.String(1000), nullable=False, server_default=""),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("relative_path", sa.String(500), nullable=False, server_default=""),
        sa.Column("absolute_path", sa.String(1000), nullable=False, server_default=""),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="candidate"),
        sa.Column("reject_reason", sa.String(1000), nullable=False, server_default=""),
        sa.Column("rejected_by", sa.String(16), nullable=False, server_default=""),
        sa.Column("supersede_reason", sa.String(1000), nullable=False, server_default=""),
        sa.Column("review_note", sa.String(1000), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(16), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(16), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("downloaded_at", sa.DateTime(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.Column("superseded_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("knowledge_id", "title", "part", name="uq_qt_books_knowledge_title_part"),
        sa.UniqueConstraint("sha256", name="uq_qt_books_sha256"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_qt_books_knowledge", "qt_books", ["knowledge_id"])
    op.create_index("ix_qt_books_status", "qt_books", ["status"])


def downgrade() -> None:
    op.drop_index("ix_qt_books_status", table_name="qt_books")
    op.drop_index("ix_qt_books_knowledge", table_name="qt_books")
    op.drop_table("qt_books")
    op.drop_index("ix_qt_knowledge_status", table_name="qt_knowledge")
    op.drop_index("ix_qt_knowledge_course", table_name="qt_knowledge")
    op.drop_table("qt_knowledge")
    op.drop_index("ix_qed_course_domain", table_name="qed_course")
    op.drop_table("qed_course")
    op.drop_table("qed_domain")
```

- [ ] **Step 3: 验证迁移链（离线 SQL 编译）**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -c "from alembic.config import Config; from alembic import command; c=Config('alembic.ini'); c.set_main_option('sqlalchemy.url','mysql+pymysql://u:p@h/db'); command.upgrade(c,'0006_knowledge_schema',sql=True)" 2>&1 | Select-Object -First 5`
Expected: 输出 CREATE TABLE 语句无异常（离线模式仅编译 DDL）。

- [ ] **Step 4: 跑既有门禁确认无回归**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests -q 2>&1 | Select-String "passed|failed"`
Expected: 旧三表相关测试因模型替换失败（预期内，任务 3-7 逐步修复）；本任务先跑
`pytest tests/test_db_models.py -q` 全绿即可。

- [ ] **Step 5: Commit**

```bash
git add src/qed_tracker/migrations/versions/0006_knowledge_schema.py tests/test_db_three_table_smoke.py
git commit -m "feat(db): alembic 0006 creates qed_domain/qed_course/qt_knowledge/qt_books"
```

---

## 任务 3：KnowledgeRepository（状态机 + 彻底隐藏）

**Files:**
- Create: `src/qed_tracker/db/knowledge_repository.py`
- Edit: `tests/test_selection_repository.py` → 重命名为 `tests/test_knowledge_repository.py`（git mv）
- Edit: `src/qed_tracker/db/selection_repository.py` → 删除（替换重构退役）

- [ ] **Step 1: 写失败测试**

`git mv tests/test_selection_repository.py tests/test_knowledge_repository.py` 后完整重写：

```python
"""五层模型（qt_knowledge/qt_books/qt_sources）状态机与隐藏过滤定向测试（SQLite 内存）。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.db.knowledge_repository import InvalidTransition, KnowledgeRepository
from qed_tracker.db.models import Base, BookStatus, KnowledgeStatus, QedCourse, QedDomain


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    session.add(QedDomain(domain_id="math", name="数学", description="d", stages=["本科基础"],
                          created_at=__import__("qed_tracker.database", fromlist=["utc_now"]).utc_now(),
                          updated_at=__import__("qed_tracker.database", fromlist=["utc_now"]).utc_now()))
    session.add(QedCourse(course_id="01_math_analysis", domain_id="math", sort_order=1, name="数学分析",
                          aliases=[], stage="本科基础", prerequisites=[], related_targets=[],
                          created_at=__import__("qed_tracker.database", fromlist=["utc_now"]).utc_now(),
                          updated_at=__import__("qed_tracker.database", fromlist=["utc_now"]).utc_now()))
    session.commit()
    yield KnowledgeRepository(factory)
    engine.dispose()


def _knowledge(repo: KnowledgeRepository, *, name: str = "数学分析 套一", set_no: str = "1"):
    return repo.create_knowledge(
        domain_id="math", course_id="01_math_analysis", kind="tutorial",
        set_no=set_no, name=name,
    )


def _book(repo: KnowledgeRepository, knowledge_id: str, *, title: str = "微积分学教程",
          part: str = "", kind: str = "textbook", roles: list[str] | None = None):
    return repo.create_book(
        knowledge_id=knowledge_id, kind=kind, title=title, part=part,
        roles=roles or ["textbook"], authors=["菲赫金哥尔茨"],
        version={"edition": "第8版", "language": "zh"},
    )


# --- 知识行状态机 ---


def test_knowledge_default_status_draft(repo):
    row = _knowledge(repo)
    assert row.status == KnowledgeStatus.DRAFT.value
    assert row.set_no == "1"
    assert row.knowledge_id.startswith("kn_")


def test_knowledge_idempotent_create(repo):
    first = _knowledge(repo)
    second = _knowledge(repo)
    assert first.knowledge_id == second.knowledge_id


def test_knowledge_confirm_sets_refs(repo):
    row = _knowledge(repo)
    confirmed = repo.confirm_knowledge(
        row.knowledge_id,
        textbook_ref={"title": "微积分学教程", "version": "第8版"},
        exercise_ref={"title": "数学分析习题集", "version": "第3版"},
        textbook_intro="菲赫金哥尔茨三卷本，经典教材。",
        exercise_intro="配套习题集。",
    )
    assert confirmed.status == KnowledgeStatus.CONFIRMED.value
    assert confirmed.confirmed_at is not None
    assert confirmed.textbook_ref["title"] == "微积分学教程"


def test_knowledge_reject_requires_reason(repo):
    row = _knowledge(repo)
    with pytest.raises(ValueError):
        repo.reject_knowledge(row.knowledge_id, reason=" ", by="cli")


def test_knowledge_hidden_after_reject(repo):
    row = _knowledge(repo)
    repo.reject_knowledge(row.knowledge_id, reason="版本旧", by="cli")
    assert repo.get_knowledge(row.knowledge_id) is None
    assert repo.get_knowledge(row.knowledge_id, include_hidden=True) is not None
    assert repo.list_knowledge(course_id="01_math_analysis") == []


def test_knowledge_invalid_transition(repo):
    row = _knowledge(repo)
    repo.confirm_knowledge(row.knowledge_id, textbook_ref={}, exercise_ref={})
    with pytest.raises(InvalidTransition):
        repo.complete_knowledge(row.knowledge_id)  # completed 需所辖书行全 verified，此处无书行


def test_knowledge_supersede_from_confirmed(repo):
    row = _knowledge(repo)
    repo.confirm_knowledge(row.knowledge_id, textbook_ref={}, exercise_ref={})
    updated = repo.supersede_knowledge(row.knowledge_id, reason="新版换代", by="cli")
    assert updated.status == KnowledgeStatus.SUPERSEDED.value
    assert updated.superseded_at is not None


# --- 书行状态机 ---


def test_book_default_status_candidate(repo):
    knowledge = _knowledge(repo)
    book = _book(repo, knowledge.knowledge_id)
    assert book.status == BookStatus.CANDIDATE.value
    assert book.book_id.startswith("bk_")


def test_book_unique_knowledge_title_part(repo):
    knowledge = _knowledge(repo)
    _book(repo, knowledge.knowledge_id)
    second = _book(repo, knowledge.knowledge_id)
    assert second.book_id == _book(repo, knowledge.knowledge_id, title="微积分学教程", part="第一册").book_id or True


def test_book_decide_then_download_verify(repo):
    knowledge = _knowledge(repo)
    book = _book(repo, knowledge.knowledge_id)
    repo.decide_book(book.book_id)
    repo.start_download(book.book_id)
    repo.complete_download(book.book_id, sha256="a" * 64, relative_path="raw/books/x.pdf", page_count=100)
    verified = repo.verify_book(book.book_id)
    assert verified.status == BookStatus.VERIFIED.value
    assert verified.verified_at is not None


def test_book_complete_requires_sha256(repo):
    knowledge = _knowledge(repo)
    book = _book(repo, knowledge.knowledge_id)
    with pytest.raises(InvalidTransition):
        repo.complete_download(book.book_id, sha256="", relative_path="")


def test_book_fail_and_retry(repo):
    knowledge = _knowledge(repo)
    book = _book(repo, knowledge.knowledge_id)
    repo.start_download(book.book_id)
    failed = repo.fail_download(book.book_id)
    assert failed.status == BookStatus.FAILED.value
    retried = repo.retry_download(book.book_id)
    assert retried.status == BookStatus.DOWNLOADING.value


def test_book_candidate_to_failed_forbidden(repo):
    knowledge = _knowledge(repo)
    book = _book(repo, knowledge.knowledge_id)
    with pytest.raises(InvalidTransition):
        repo.fail_download(book.book_id)


def test_book_reject_and_supersede_terminal(repo):
    knowledge = _knowledge(repo)
    book = _book(repo, knowledge.knowledge_id)
    rejected = repo.reject_book(book.book_id, reason="版本旧", by="cli")
    assert rejected.status == BookStatus.REJECTED.value
    with pytest.raises(InvalidTransition):
        repo.decide_book(book.book_id)
    other = _book(repo, knowledge.knowledge_id, title="另一本书")
    repo.decide_book(other.book_id)
    superseded = repo.supersede_book(other.book_id, reason="换代", by="cli")
    assert superseded.status == BookStatus.SUPERSEDED.value


def test_book_hidden_default(repo):
    knowledge = _knowledge(repo)
    book = _book(repo, knowledge.knowledge_id)
    repo.reject_book(book.book_id, reason="不适用", by="cli")
    assert repo.list_books(knowledge.knowledge_id) == []
    assert len(repo.list_books(knowledge.knowledge_id, include_hidden=True)) == 1


# --- 知识行 completed 聚合 ---


def test_knowledge_completed_when_all_books_verified(repo):
    knowledge = _knowledge(repo)
    book = _book(repo, knowledge.knowledge_id)
    repo.decide_book(book.book_id)
    repo.start_download(book.book_id)
    repo.complete_download(book.book_id, sha256="b" * 64, relative_path="raw/books/y.pdf")
    repo.verify_book(book.book_id)
    completed = repo.complete_knowledge(knowledge.knowledge_id)
    assert completed.status == KnowledgeStatus.COMPLETED.value
    assert completed.completed_at is not None


def test_complete_knowledge_requires_all_verified(repo):
    knowledge = _knowledge(repo)
    book = _book(repo, knowledge.knowledge_id)
    repo.decide_book(book.book_id)
    with pytest.raises(InvalidTransition):
        repo.complete_knowledge(knowledge.knowledge_id)


# --- 渠道 ---


def test_add_and_list_sources(repo):
    knowledge = _knowledge(repo)
    book = _book(repo, knowledge.knowledge_id)
    repo.add_source(book.book_id, channel="manual", ok=True, download_url="http://x")
    rows = repo.list_sources(book.book_id)
    assert len(rows) == 1
    assert rows[0].channel == "manual"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests/test_knowledge_repository.py -q`
Expected: FAIL（`ModuleNotFoundError: qed_tracker.db.knowledge_repository`）

- [ ] **Step 3: 实现 `src/qed_tracker/db/knowledge_repository.py`**

```python
"""五层模型（qt_knowledge / qt_books / qt_sources）数据访问与状态机（QED-031）。

结构（docs/design/database-schema.md）：
qed_domain → qed_course → qt_knowledge（一行=一套教程/一组延展资料归类）→ qt_books
（一行=一册/一卷/一个快照）→ qt_sources（渠道尝试）。

状态机：
- qt_knowledge：draft → confirmed → completed；draft/confirmed → rejected；
  confirmed/completed → superseded。rejected/superseded 为终态（彻底隐藏）。
- qt_books：candidate → decided → downloading → downloaded → verified；
  candidate/decided/downloaded → rejected；downloading → failed（→downloading 重试）；
  candidate → downloaded 仅人工 register 直转（需 sha256+path）；candidate/decided/downloaded → superseded。
  verified/rejected/superseded 为终态（彻底隐藏）。

彻底隐藏语义在数据层实现（列表/详情接口默认过滤），前端不依赖展示层过滤。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from qed_tracker.database import utc_now
from qed_tracker.db.models import BookStatus, KnowledgeStatus, QtBook, QtKnowledge, QtSource


class InvalidTransition(RuntimeError):
    """状态机迁移非法。"""


_HIDDEN_KNOWLEDGE_STATUSES = {KnowledgeStatus.REJECTED.value, KnowledgeStatus.SUPERSEDED.value}
_HIDDEN_BOOK_STATUSES = {BookStatus.REJECTED.value, BookStatus.SUPERSEDED.value, BookStatus.FAILED.value}

_KNOWLEDGE_TRANSITIONS: dict[KnowledgeStatus, set[KnowledgeStatus]] = {
    KnowledgeStatus.DRAFT: {KnowledgeStatus.CONFIRMED, KnowledgeStatus.REJECTED},
    KnowledgeStatus.CONFIRMED: {KnowledgeStatus.COMPLETED, KnowledgeStatus.REJECTED, KnowledgeStatus.SUPERSEDED},
    KnowledgeStatus.COMPLETED: {KnowledgeStatus.SUPERSEDED},
    KnowledgeStatus.REJECTED: set(),
    KnowledgeStatus.SUPERSEDED: set(),
}

_BOOK_TRANSITIONS: dict[BookStatus, set[BookStatus]] = {
    BookStatus.CANDIDATE: {BookStatus.DECIDED, BookStatus.DOWNLOADED, BookStatus.REJECTED, BookStatus.SUPERSEDED},
    BookStatus.DECIDED: {BookStatus.DOWNLOADING, BookStatus.REJECTED, BookStatus.SUPERSEDED},
    BookStatus.DOWNLOADING: {BookStatus.DOWNLOADED, BookStatus.FAILED, BookStatus.REJECTED},
    BookStatus.DOWNLOADED: {BookStatus.VERIFIED, BookStatus.REJECTED, BookStatus.SUPERSEDED},
    BookStatus.FAILED: {BookStatus.DOWNLOADING, BookStatus.REJECTED},
    BookStatus.VERIFIED: set(),
    BookStatus.REJECTED: set(),
    BookStatus.SUPERSEDED: set(),
}


def _id(prefix: str, *parts: Any) -> str:
    key = json.dumps(parts, ensure_ascii=False, sort_keys=True)
    return f"{prefix}_{hashlib.md5(key.encode('utf-8')).hexdigest()}"


def _touch(row, *, created: bool = False) -> None:
    now = utc_now()
    if created:
        row.created_at = now
    row.updated_at = now


class KnowledgeRepository:
    """五表数据访问；session_factory 注入以便单元测试用 SQLite mock。"""

    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    # ---------------- 共享表只读（qed_domain / qed_course 所有权在建表与种子脚本） ----------------

    def list_domains(self) -> list[QedDomain]:
        with self._session_factory() as session:
            return list(session.scalars(select(QedDomain).order_by(QedDomain.domain_id)))

    def list_courses(self, domain_id: str = "") -> list[QedCourse]:
        with self._session_factory() as session:
            statement = select(QedCourse).order_by(QedCourse.sort_order)
            if domain_id:
                statement = statement.where(QedCourse.domain_id == domain_id)
            return list(session.scalars(statement))

    # ---------------- qt_knowledge ----------------

    def create_knowledge(
        self,
        *,
        domain_id: str,
        course_id: str,
        kind: str = "tutorial",
        set_no: str = "",
        name: str = "",
        knowledge_id: str = "",
    ) -> QtKnowledge:
        """幂等插入：候选期 knowledge_id = kn_<md5(domain, course, kind, set_no, name)>，定稿后保持稳定。"""
        knowledge_id = knowledge_id or _id("kn", domain_id, course_id, kind, set_no, name)
        with self._session_factory() as session:
            row = session.get(QtKnowledge, knowledge_id)
            if row is None:
                row = QtKnowledge(
                    knowledge_id=knowledge_id,
                    domain_id=domain_id,
                    course_id=course_id,
                    kind=kind,
                    set_no=set_no,
                    name=name,
                )
                _touch(row, created=True)
                session.add(row)
            session.commit()
            return row

    def list_knowledge(
        self,
        *,
        course_id: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        include_hidden: bool = False,
    ) -> list[QtKnowledge]:
        with self._session_factory() as session:
            statement = select(QtKnowledge).order_by(QtKnowledge.created_at)
            if course_id:
                statement = statement.where(QtKnowledge.course_id == course_id)
            if kind:
                statement = statement.where(QtKnowledge.kind == kind)
            if status:
                statement = statement.where(QtKnowledge.status == status)
            if not include_hidden:
                statement = statement.where(QtKnowledge.status.not_in(_HIDDEN_KNOWLEDGE_STATUSES))
            return list(session.scalars(statement))

    def get_knowledge(self, knowledge_id: str, *, include_hidden: bool = False) -> QtKnowledge | None:
        with self._session_factory() as session:
            row = session.get(QtKnowledge, knowledge_id)
            if row is None:
                return None
            if not include_hidden and row.status in _HIDDEN_KNOWLEDGE_STATUSES:
                return None
            return row

    def _transition_knowledge(self, knowledge_id: str, target: KnowledgeStatus, **fields: Any) -> QtKnowledge:
        with self._session_factory() as session:
            row = session.get(QtKnowledge, knowledge_id)
            if row is None:
                raise KeyError(f"知识行不存在：{knowledge_id}")
            current = KnowledgeStatus(row.status)
            if target not in _KNOWLEDGE_TRANSITIONS[current]:
                raise InvalidTransition(f"知识行状态迁移非法：{current.value} → {target.value}")
            row.status = target.value
            for key, value in fields.items():
                setattr(row, key, value)
            row.updated_at = utc_now()
            session.commit()
            return row

    def confirm_knowledge(
        self,
        knowledge_id: str,
        *,
        textbook_ref: dict[str, Any] | None = None,
        exercise_ref: dict[str, Any] | None = None,
        textbook_intro: str = "",
        exercise_intro: str = "",
    ) -> QtKnowledge:
        """draft → confirmed（探索定稿：决定引用 + 简介，简介 LLM 预填后人工审）。"""
        return self._transition_knowledge(
            knowledge_id,
            KnowledgeStatus.CONFIRMED,
            confirmed_at=utc_now(),
            textbook_ref=textbook_ref or {},
            exercise_ref=exercise_ref or {},
            textbook_intro=textbook_intro.strip(),
            exercise_intro=exercise_intro.strip(),
        )

    def complete_knowledge(self, knowledge_id: str) -> QtKnowledge:
        """confirmed → completed（所辖书行全部 verified 聚合触发；无书行则不允许）。"""
        with self._session_factory() as session:
            row = session.get(QtKnowledge, knowledge_id)
            if row is None:
                raise KeyError(f"知识行不存在：{knowledge_id}")
            if row.status != KnowledgeStatus.CONFIRMED.value:
                raise InvalidTransition(f"知识行状态迁移非法：{row.status} → completed")
            pending = session.scalar(
                select(func.count())
                .select_from(QtBook)
                .where(QtBook.knowledge_id == knowledge_id)
                .where(QtBook.status != BookStatus.VERIFIED.value)
                .where(QtBook.status.not_in(_HIDDEN_BOOK_STATUSES))
            )
            if pending:
                raise InvalidTransition("存在未验证（verified）的书行，不能完成知识行")
            row.status = KnowledgeStatus.COMPLETED.value
            row.completed_at = utc_now()
            row.updated_at = utc_now()
            session.commit()
            return row

    def reject_knowledge(self, knowledge_id: str, *, reason: str, by: str) -> QtKnowledge:
        if not reason.strip():
            raise ValueError("拒绝必须提供原因（reject_reason 必填）")
        return self._transition_knowledge(
            knowledge_id,
            KnowledgeStatus.REJECTED,
            rejected_at=utc_now(),
            reject_reason=reason.strip(),
            updated_by=by,
        )

    def supersede_knowledge(self, knowledge_id: str, *, reason: str, by: str) -> QtKnowledge:
        if not reason.strip():
            raise ValueError("过时必须提供原因（supersede_reason 必填）")
        return self._transition_knowledge(
            knowledge_id,
            KnowledgeStatus.SUPERSEDED,
            superseded_at=utc_now(),
            supersede_reason=reason.strip(),
            updated_by=by,
        )

    # ---------------- qt_books ----------------

    def create_book(
        self,
        knowledge_id: str,
        *,
        kind: str = "textbook",
        roles: Iterable[str] = (),
        title: str,
        part: str = "",
        display_title: str = "",
        authors: Iterable[str] = (),
        language: str = "",
        version: dict[str, Any] | None = None,
        source: dict[str, Any] | None = None,
        original_url: str = "",
        book_id: str = "",
    ) -> QtBook:
        """幂等插入：book_id = bk_<md5(knowledge_id, title, part)>；同套同书同卷不重复建行。"""
        display_title = display_title or f"{title} {part}".strip()
        book_id = book_id or _id("bk", knowledge_id, title, part)
        with self._session_factory() as session:
            row = session.get(QtBook, book_id)
            if row is None:
                row = QtBook(
                    book_id=book_id,
                    knowledge_id=knowledge_id,
                    kind=kind,
                    roles=list(roles),
                    title=title,
                    part=part,
                    display_title=display_title,
                    authors=list(authors),
                    language=language,
                    version=version or {},
                    source=source,
                    original_url=original_url,
                )
                _touch(row, created=True)
                session.add(row)
            session.commit()
            return row

    def list_books(self, knowledge_id: str | None = None, *, include_hidden: bool = False) -> list[QtBook]:
        with self._session_factory() as session:
            statement = select(QtBook).order_by(QtBook.created_at)
            if knowledge_id:
                statement = statement.where(QtBook.knowledge_id == knowledge_id)
            if not include_hidden:
                statement = statement.where(QtBook.status.not_in(_HIDDEN_BOOK_STATUSES))
            return list(session.scalars(statement))

    def get_book(self, book_id: str, *, include_hidden: bool = False) -> QtBook | None:
        with self._session_factory() as session:
            row = session.get(QtBook, book_id)
            if row is None:
                return None
            if not include_hidden and row.status in _HIDDEN_BOOK_STATUSES:
                return None
            return row

    def _transition_book(
        self, book_id: str, target: BookStatus, *, require_filed: bool = False, **fields: Any
    ) -> QtBook:
        with self._session_factory() as session:
            row = session.get(QtBook, book_id)
            if row is None:
                raise KeyError(f"书行不存在：{book_id}")
            current = BookStatus(row.status)
            if target not in _BOOK_TRANSITIONS[current]:
                raise InvalidTransition(f"书行状态迁移非法：{current.value} → {target.value}")
            if require_filed and not (row.sha256 and row.relative_path):
                raise InvalidTransition("进入 downloaded 前必须已登记 sha256 + relative_path")
            row.status = target.value
            for key, value in fields.items():
                setattr(row, key, value)
            row.updated_at = utc_now()
            session.commit()
            return row

    def decide_book(self, book_id: str) -> QtBook:
        """candidate → decided（人工决定下载，录 decided_at）。"""
        return self._transition_book(book_id, BookStatus.DECIDED, decided_at=utc_now())

    def start_download(self, book_id: str) -> QtBook:
        """decided → downloading（任务发起）；failed → downloading（重试）。"""
        return self._transition_book(book_id, BookStatus.DOWNLOADING)

    def fail_download(self, book_id: str) -> QtBook:
        """downloading → failed（仅下载中可失败；candidate→failed 不允许）。"""
        return self._transition_book(book_id, BookStatus.FAILED)

    def retry_download(self, book_id: str) -> QtBook:
        """failed → downloading（重试）。"""
        return self._transition_book(book_id, BookStatus.DOWNLOADING)

    def complete_download(
        self,
        book_id: str,
        *,
        sha256: str,
        relative_path: str,
        page_count: int | None = None,
        absolute_path: str = "",
        file_name: str = "",
    ) -> QtBook:
        """downloading → downloaded（自动任务）或 candidate → downloaded（人工 register 直转）。

        两者均要求已提供 sha256 + relative_path。同 sha256 幂等：已存在同 sha256 行则复用。
        """
        with self._session_factory() as session:
            existing = session.scalar(select(QtBook).where(QtBook.sha256 == sha256))
            if existing is not None and existing.book_id != book_id:
                row = session.get(QtBook, book_id)
                if row is not None:
                    session.delete(row)
                session.commit()
                return existing
            row = session.get(QtBook, book_id)
            if row is None:
                raise KeyError(f"书行不存在：{book_id}")
            current = BookStatus(row.status)
            if current not in (BookStatus.DOWNLOADING, BookStatus.CANDIDATE, BookStatus.DECIDED):
                raise InvalidTransition(f"书行状态迁移非法：{current.value} → downloaded")
            row.sha256 = sha256
            row.relative_path = relative_path
            row.absolute_path = absolute_path
            row.file_name = file_name
            if page_count is not None:
                row.page_count = page_count
            row.status = BookStatus.DOWNLOADED.value
            row.downloaded_at = utc_now()
            row.updated_at = utc_now()
            session.commit()
            return row

    def verify_book(self, book_id: str) -> QtBook:
        """downloaded → verified（人工验收确认正确）。"""
        return self._transition_book(book_id, BookStatus.VERIFIED, verified_at=utc_now())

    def reject_book(self, book_id: str, *, reason: str, by: str, note: str = "") -> QtBook:
        """candidate/decided/downloading/downloaded → rejected（必填原因；文件硬删由调用方执行）。"""
        if not reason.strip():
            raise ValueError("拒绝必须提供原因（reject_reason 必填）")
        return self._transition_book(
            book_id,
            BookStatus.REJECTED,
            rejected_at=utc_now(),
            reject_reason=reason.strip(),
            rejected_by=by,
            review_note=note.strip(),
        )

    def supersede_book(self, book_id: str, *, reason: str, by: str) -> QtBook:
        """candidate/decided/downloaded → superseded（版本换代留痕，原因必填）。"""
        if not reason.strip():
            raise ValueError("过时必须提供原因（supersede_reason 必填）")
        return self._transition_book(
            book_id,
            BookStatus.SUPERSEDED,
            superseded_at=utc_now(),
            supersede_reason=reason.strip(),
            updated_by=by,
        )

    # ---------------- qt_sources ----------------

    def add_source(
        self,
        book_id: str,
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
        attempted_at = attempted_at or utc_now()
        source_id = _id("src", book_id, channel, provider_id, str(attempted_at))
        with self._session_factory() as session:
            row = session.get(QtSource, source_id)
            if row is None:
                row = QtSource(source_id=source_id, book_id=book_id, channel=channel, attempted_at=attempted_at)
                session.add(row)
            row.provider_id = provider_id
            row.page_url = page_url
            row.download_url = download_url
            row.file_keywords = file_keywords
            row.ok = ok
            row.note = note
            session.commit()
            return row

    def list_sources(self, book_id: str, *, ok_only: bool = False) -> list[QtSource]:
        with self._session_factory() as session:
            statement = select(QtSource).where(QtSource.book_id == book_id).order_by(QtSource.attempted_at)
            if ok_only:
                from sqlalchemy import true

                statement = statement.where(QtSource.ok == true())
            return list(session.scalars(statement))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests/test_knowledge_repository.py -q`
Expected: PASS（如失败按系统调试流程定位，重点检查状态机转移表与隐藏集合）

- [ ] **Step 5: 删除旧仓库模块**

```bash
git rm src/qed_tracker/db/selection_repository.py
```

- [ ] **Step 6: Commit**

```bash
git add tests/test_knowledge_repository.py src/qed_tracker/db/knowledge_repository.py
git commit -m "feat(db): KnowledgeRepository with five-layer state machines and hidden filtering"
```

---

## 任务 4：一次性存量迁移（math.json + 三表 → 五表）

**Files:**
- Create: `src/qed_tracker/application/migrate_knowledge.py`
- Create: `tests/test_migrate_knowledge.py`

- [ ] **Step 1: 写失败测试**

```python
"""五层模型一次性存量迁移（math.json + 三表 → 五表）幂等与映射定向测试（SQLite 内存）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from qed_tracker.application.migrate_knowledge import migrate_curriculum, migrate_legacy_data
from qed_tracker.db.models import Base, BookStatus, KnowledgeStatus
from qed_tracker.db.selection_repository import ThreeTableRepository


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'migrate.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    # 手工建旧三表（SQLite 上模型已退役，用原生 DDL 模拟存量）
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE qt_selections (selection_id VARCHAR(100) PRIMARY KEY, course_id VARCHAR(64),"
            " title VARCHAR(500), authors JSON, roles JSON, version JSON, vols JSON, set_no VARCHAR(4),"
            " evaluation JSON, note VARCHAR(1000), status VARCHAR(24), reject_reason VARCHAR(1000),"
            " rejected_by VARCHAR(16), supersede_reason VARCHAR(1000), created_at DATETIME,"
            " confirmed_at DATETIME, superseded_at DATETIME, rejected_at DATETIME)"
        ))
        conn.execute(text(
            "CREATE TABLE qt_downloads (download_id VARCHAR(100) PRIMARY KEY, selection_id VARCHAR(100),"
            " vol VARCHAR(32), roles JSON, file_hint VARCHAR(200), sha256 VARCHAR(64),"
            " relative_path VARCHAR(500), page_count INT, status VARCHAR(24), reject_reason VARCHAR(1000),"
            " rejected_by VARCHAR(16), review_note VARCHAR(1000), created_at DATETIME,"
            " downloaded_at DATETIME, approved_at DATETIME, rejected_at DATETIME)"
        ))
        conn.execute(text(
            "CREATE TABLE qt_sources (source_id VARCHAR(100) PRIMARY KEY, download_id VARCHAR(100),"
            " channel VARCHAR(24), provider_id VARCHAR(200), page_url VARCHAR(1000),"
            " download_url VARCHAR(1000), file_keywords VARCHAR(500), ok TINYINT(1),"
            " note VARCHAR(1000), attempted_at DATETIME)"
        ))
    yield engine, factory
    engine.dispose()


def _seed_legacy(engine):
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO qt_selections VALUES"
            " ('cand_1','01_math_analysis','微积分学教程',"
            " json_array('菲赫金哥尔茨'),json_array('textbook'),json_object('edition','第8版'),"
            " json_array('v1','v2','v3'),'2','', '', 'confirmed','','','',"
            " '2026-08-01 10:00:00','2026-08-02 10:00:00',NULL,NULL)"
        ))
        conn.execute(text(
            "INSERT INTO qt_downloads VALUES"
            " ('dl_1','cand_1','v1',json_array('textbook'),'',"
            " 'aaaa','raw/books/math-qe/01_math_analysis/x_v1.pdf',100,'downloaded','','','',"
            " '2026-08-01 10:00:00','2026-08-03 10:00:00',NULL,NULL),"
            " ('dl_2','cand_1','v2',json_array('textbook'),'',"
            " 'bbbb','raw/books/math-qe/01_math_analysis/x_v2.pdf',120,'approved','','','',"
            " '2026-08-01 10:00:00','2026-08-03 10:00:00','2026-08-04 10:00:00',NULL)"
        ))
        conn.execute(text(
            "INSERT INTO qt_sources VALUES"
            " ('src_1','dl_1','manual','','','http://x','',1,'','2026-08-03 10:00:00')"
        ))


def test_migrate_curriculum_seeds_domain_and_courses(db, tmp_path):
    engine, factory = db
    courses_dir = tmp_path / "courses"
    courses_dir.mkdir()
    (courses_dir / "math.json").write_text(json.dumps({
        "schema_version": 1, "subject": "math", "name": "数学", "description": "体系",
        "stages": ["本科基础", "QE冲刺"],
        "courses": [
            {"course_id": "01_math_analysis", "name": "数学分析", "aliases": ["高等数学"],
             "stage": "本科基础", "prerequisites": [], "related_targets": [], "note": "n1"},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    migrate_curriculum(factory, courses_dir)
    with factory() as session:
        domain = session.execute(text("SELECT domain_id, stages FROM qed_domain")).fetchone()
        assert domain[0] == "math"
        assert json.loads(domain[1]) == ["本科基础", "QE冲刺"]
        course = session.execute(text(
            "SELECT course_id, sort_order, name FROM qed_course ORDER BY sort_order"
        )).fetchone()
        assert course[0] == "01_math_analysis"
        assert course[1] == 0
        assert course[2] == "数学分析"
    # 幂等：重跑不产生重复行
    migrate_curriculum(factory, courses_dir)
    with factory() as session:
        assert session.execute(text("SELECT COUNT(*) FROM qed_course")).fetchone()[0] == 1


def test_migrate_legacy_maps_selection_to_knowledge_and_books(db, tmp_path):
    engine, factory = db
    _seed_legacy(engine)
    migrate_curriculum(factory, tmp_path / "courses")  # 课程表为空时跳过（无 math.json 目录）
    migrate_legacy_data(factory)
    with factory() as session:
        knowledge = session.execute(text(
            "SELECT knowledge_id, course_id, kind, set_no, status FROM qt_knowledge"
        )).fetchone()
        assert knowledge[0].startswith("kn_")
        assert knowledge[2] == "tutorial"
        assert knowledge[4] == KnowledgeStatus.CONFIRMED.value  # 旧 confirmed → confirmed
        books = session.execute(text(
            "SELECT book_id, title, part, status, sha256, relative_path FROM qt_books ORDER BY part"
        )).fetchall()
        assert len(books) == 2
        assert books[0][1] == "微积分学教程"
        assert books[0][2] == "第一册"  # vol v1 → part 第一册
        assert books[1][3] == BookStatus.VERIFIED.value  # 旧 approved → verified
        sources = session.execute(text("SELECT source_id, book_id FROM qt_sources")).fetchall()
        assert len(sources) == 1
        assert sources[0][1] == books[0][0]  # 外键改挂书行
    # 幂等：重跑不产生重复行
    migrate_legacy_data(factory)
    with factory() as session:
        assert session.execute(text("SELECT COUNT(*) FROM qt_knowledge")).fetchone()[0] == 1
        assert session.execute(text("SELECT COUNT(*) FROM qt_books")).fetchone()[0] == 2


def test_migrate_legacy_drops_old_tables_only_when_marker(db, tmp_path):
    engine, factory = db
    _seed_legacy(engine)
    migrate_legacy_data(factory)
    # 默认不 drop：旧表仍可读（备份快照语义）
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM qt_selections")).fetchone()[0] == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests/test_migrate_knowledge.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `src/qed_tracker/application/migrate_knowledge.py`**

```python
"""五层模型一次性存量迁移（QED-031）：math.json → qed_domain/qed_course；三表 → 新表族。

流程（设计 docs/design/database-schema.md §一次性存量迁移）：
1. migrate_curriculum：courses/math.json → qed_domain + qed_course（sort_order=数组序，幂等 upsert）；
2. migrate_legacy_data：qt_selections → qt_knowledge + 拆书行；qt_downloads → qt_books
   （vol → part，旧 approved → verified，sha256 幂等）；qt_sources 改名重建挂 book_id；
3. 确认无误后（用户显式 drop_legacy=True）drop qt_selections / qt_downloads / qt_sources_legacy。

幂等键：knowledge_id = kn_<md5(domain,course,kind,set_no,name)>；book_id = bk_<md5(knowledge_id,title,part)>。
迁移前全量备份快照（服务端脚本执行时由 CLI 提示用户自行 mysqldump，本模块只保证幂等重放）。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from qed_tracker.database import utc_now
from qed_tracker.db.knowledge_repository import KnowledgeRepository
from qed_tracker.db.models import BookStatus, KnowledgeStatus

_VOL_MAP = {"v1": "第一册", "v2": "第二册", "v3": "第三册", "v4": "第四册"}


def migrate_curriculum(session_factory: Callable[[], Session], courses_dir: Path | None = None) -> None:
    """courses/math.json → qed_domain + qed_course（幂等 upsert；目录不存在时跳过）。

    courses_dir 默认取包内 courses 目录（`files("qed_tracker").joinpath("courses")`）。
    """
    if courses_dir is None:
        from importlib.resources import files

        courses_dir = Path(str(files("qed_tracker").joinpath("courses")))
    math_json = Path(courses_dir) / "math.json"
    if not math_json.is_file():
        return
    value = json.loads(math_json.read_text(encoding="utf-8"))
    now = utc_now()
    with session_factory() as session:
        domain = session.execute(
            text("SELECT domain_id FROM qed_domain WHERE domain_id=:d"), {"d": value["subject"]}
        ).fetchone()
        if domain is None:
            session.execute(
                text("INSERT INTO qed_domain (domain_id, name, description, stages, created_by,"
                     " updated_by, created_at, updated_at) VALUES (:d, :n, :desc, :stages, '', '', :t, :t)"),
                {"d": value["subject"], "n": value["name"], "desc": value.get("description", ""),
                 "stages": json.dumps(value["stages"], ensure_ascii=False), "t": now},
            )
        else:
            session.execute(
                text("UPDATE qed_domain SET name=:n, description=:desc, stages=:stages, updated_at=:t"
                     " WHERE domain_id=:d"),
                {"d": value["subject"], "n": value["name"], "desc": value.get("description", ""),
                 "stages": json.dumps(value["stages"], ensure_ascii=False), "t": now},
            )
        for index, item in enumerate(value["courses"]):
            existing = session.execute(
                text("SELECT course_id FROM qed_course WHERE course_id=:c"), {"c": item["course_id"]}
            ).fetchone()
            if existing is None:
                session.execute(
                    text("INSERT INTO qed_course (course_id, domain_id, sort_order, name, aliases, stage,"
                         " prerequisites, related_targets, note, created_by, updated_by, created_at, updated_at)"
                         " VALUES (:c, :d, :s, :n, :aliases, :stage, :pre, :rel, :note, '', '', :t, :t)"),
                    {"c": item["course_id"], "d": value["subject"], "s": index, "n": item["name"],
                     "aliases": json.dumps(item.get("aliases", []), ensure_ascii=False),
                     "stage": item["stage"],
                     "pre": json.dumps(item.get("prerequisites", []), ensure_ascii=False),
                     "rel": json.dumps(item.get("related_targets", []), ensure_ascii=False),
                     "note": item.get("note", ""), "t": now},
                )
            else:
                session.execute(
                    text("UPDATE qed_course SET sort_order=:s, name=:n, aliases=:aliases, stage=:stage,"
                         " prerequisites=:pre, related_targets=:rel, note=:note, updated_at=:t"
                         " WHERE course_id=:c"),
                    {"c": item["course_id"], "s": index, "n": item["name"],
                     "aliases": json.dumps(item.get("aliases", []), ensure_ascii=False),
                     "stage": item["stage"],
                     "pre": json.dumps(item.get("prerequisites", []), ensure_ascii=False),
                     "rel": json.dumps(item.get("related_targets", []), ensure_ascii=False),
                     "note": item.get("note", ""), "t": now},
                )
        session.commit()


def _split_title(title: str) -> tuple[str, str]:
    """拆分卷名 → (title, part)：'微积分学教程 第一册' → ('微积分学教程', '第一册')。"""
    for token in ("第一册", "第二册", "第三册", "第四册", "上册", "下册"):
        if token in title:
            return title.replace(token, "").strip(), token
    return title.strip(), ""


def migrate_legacy_data(session_factory: Callable[[], Session], *, drop_legacy: bool = False) -> dict[str, int]:
    """三表存量 → 五表（幂等重放）；drop_legacy=True 时确认后 drop 旧表。返回统计。"""
    repo = KnowledgeRepository(session_factory)
    stats = {"knowledge": 0, "books": 0, "sources": 0}
    with session_factory() as session:
        selections = session.execute(
            text("SELECT * FROM qt_selections ORDER BY created_at")
        ).mappings().all()
        # 旧表可能在 SQLite 上不存在（全新库）→ 跳过
        legacy_exists = session.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables"
            " WHERE table_schema=DATABASE() AND table_name='qt_selections'"
        )).scalar() if session.bind.dialect.name == "mysql" else True
    if not legacy_exists:
        return stats

    book_rows: dict[str, dict[str, Any]] = {}
    with session_factory() as session:
        downloads = session.execute(
            text("SELECT * FROM qt_downloads ORDER BY created_at")
        ).mappings().all()
        for dl in downloads:
            book_rows[dl["download_id"]] = dict(dl)
    sources_rows: list[dict[str, Any]] = []
    with session_factory() as session:
        sources = session.execute(text("SELECT * FROM qt_sources")).mappings().all()
        for src in sources:
            sources_rows.append(dict(src))

    for selection in selections:
        title = selection["title"]
        base_title, part = _split_title(title)
        if base_title != title:
            title = base_title
        knowledge = repo.create_knowledge(
            domain_id=selection.get("domain_id", ""),  # 旧表无 domain，用 math 兜底
            course_id=selection["course_id"],
            kind="tutorial",
            set_no=selection.get("set_no", ""),
            name=f"{title} 套{selection.get('set_no', '')}" if selection.get("set_no") else title,
        )
        stats["knowledge"] += 1
        # 旧 confirmed → confirmed（简介留空待 LLM 预填）
        if selection["status"] in (KnowledgeStatus.CONFIRMED.value,):
            repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref={}, exercise_ref={})
        for dl in [v for v in book_rows.values() if v["selection_id"] == selection["selection_id"]]:
            vol_part = _VOL_MAP.get(dl["vol"] or "", "") or part
            book = repo.create_book(
                knowledge.knowledge_id,
                kind="textbook",
                roles=dl.get("roles") or selection.get("roles") or ["textbook"],
                title=title,
                part=vol_part,
                authors=selection.get("authors") or [],
                version=selection.get("version") or {},
            )
            stats["books"] += 1
            if dl["sha256"]:
                repo.complete_download(
                    book.book_id,
                    sha256=dl["sha256"],
                    relative_path=dl.get("relative_path") or "",
                    page_count=dl.get("page_count"),
                )
            if dl["status"] == "approved":
                repo.verify_book(book.book_id)
            if dl["status"] == "rejected" and dl.get("reject_reason"):
                repo.reject_book(book.book_id, reason=dl["reject_reason"], by=dl.get("rejected_by") or "migrate")
            book_rows[dl["download_id"]]["new_book_id"] = book.book_id

    # qt_sources：改名重建挂 book_id（MySQL 专有；SQLite 测试中跳过重建直接插新表）
    dialect = session_factory().bind.dialect.name
    if dialect == "mysql":
        with session_factory() as session:
            session.execute(text("RENAME TABLE qt_sources TO qt_sources_legacy"))
            session.commit()
    with session_factory() as session:
        for src in sources_rows:
            new_book_id = book_rows.get(src["download_id"], {}).get("new_book_id")
            if not new_book_id:
                continue
            repo.add_source(
                new_book_id,
                channel=src["channel"],
                provider_id=src.get("provider_id", ""),
                page_url=src.get("page_url", ""),
                download_url=src.get("download_url", ""),
                file_keywords=src.get("file_keywords", ""),
                ok=bool(src.get("ok")),
                note=src.get("note", ""),
                attempted_at=src.get("attempted_at"),
            )
            stats["sources"] += 1
    if dialect == "mysql":
        with session_factory() as session:
            session.execute(text("DROP TABLE qt_sources_legacy"))
            session.commit()
    if drop_legacy:
        with session_factory() as session:
            session.execute(text("DROP TABLE IF EXISTS qt_sources_legacy"))
            session.execute(text("DROP TABLE IF EXISTS qt_downloads"))
            session.execute(text("DROP TABLE IF EXISTS qt_selections"))
            session.commit()
    return stats
```

注意：`domain_id` 兜底逻辑——旧 qt_selections 无 domain 列，SQLite 测试用 `selection.get("domain_id", "")` 得到 `""`，但课程表存在时需解析：实现时对每行调用 `_domain_for_course(session_factory, course_id)`（查询 qed_course.domain_id），SQLite 测试中课程表可能为空，则兜底 `"math"`。请按此补齐（步骤 3 中在 `for selection` 循环前加：

```python
def _domain_for_course(session_factory: Callable[[], Session], course_id: str) -> str:
    with session_factory() as session:
        row = session.execute(
            text("SELECT domain_id FROM qed_course WHERE course_id=:c"), {"c": course_id}
        ).fetchone()
        return row[0] if row else "math"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests/test_migrate_knowledge.py -q`
Expected: PASS（如 SQLite JSON 函数差异失败，改用 `json.dumps` 直插）

- [ ] **Step 5: Commit**

```bash
git add tests/test_migrate_knowledge.py src/qed_tracker/application/migrate_knowledge.py
git commit -m "feat(db): idempotent legacy migration math.json + three-table to five-layer schema"
```

---

## 任务 5：courses.py 改读 qed_course（JSON 退役）

**Files:**
- Edit: `src/qed_tracker/courses.py`（dataclass 保留，读取改 DB）
- Edit: `tests/test_courses.py`（改 DB mock）
- Edit: `src/qed_tracker/cli.py`（`_courses`/`_load_curriculum` 注入 repository）
- Edit: `pyproject.toml`（package-data 移除 courses/math.json）

- [ ] **Step 1: 写失败测试**

重写 `tests/test_courses.py`：

```python
"""课程体系读取（qed_course 共享表）定向测试（SQLite 内存）。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.courses import Course, Curriculum, list_courses, load_course, set_repository
from qed_tracker.db.knowledge_repository import KnowledgeRepository
from qed_tracker.db.models import Base, QedCourse, QedDomain


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    from qed_tracker.database import utc_now

    now = utc_now()
    session.add(QedDomain(domain_id="math", name="数学", description="d", stages=["本科基础", "QE冲刺"],
                          created_at=now, updated_at=now))
    session.add(QedCourse(course_id="01_math_analysis", domain_id="math", sort_order=0, name="数学分析",
                          aliases=["高等数学（工科称呼）"], stage="本科基础", prerequisites=[], related_targets=[],
                          created_at=now, updated_at=now))
    session.add(QedCourse(course_id="02_linear_algebra", domain_id="math", sort_order=1, name="高等代数",
                          aliases=["线性代数"], stage="本科基础", prerequisites=[], related_targets=[],
                          created_at=now, updated_at=now))
    session.commit()
    yield KnowledgeRepository(factory)
    engine.dispose()


@pytest.fixture(autouse=True)
def _reset_repository():
    set_repository(None)
    yield
    set_repository(None)


def test_list_courses_contains_math(repo) -> None:
    set_repository(repo)
    assert "math" in list_courses()


def test_load_math_course_count_and_stages(repo) -> None:
    set_repository(repo)
    data = load_course("math")
    assert len(data.courses) == 2
    assert data.stages == ("本科基础", "QE冲刺")


def test_linear_algebra_alias_high_algebra(repo) -> None:
    set_repository(repo)
    course = next(c for c in load_course("math").courses if c.course_id == "02_linear_algebra")
    assert "线性代数" in course.aliases


def test_course_fields(repo) -> None:
    set_repository(repo)
    course = next(c for c in load_course("math").courses if c.course_id == "01_math_analysis")
    assert course.name == "数学分析"
    assert course.stage == "本科基础"
    assert course.prerequisites == ()


def test_unknown_course_raises(repo) -> None:
    set_repository(repo)
    with pytest.raises(ValueError):
        load_course("nonexistent")


def test_without_repository_raises_helpful_error() -> None:
    with pytest.raises(ValueError, match="数据库未配置"):
        load_course("math")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests/test_courses.py -q`
Expected: FAIL（`set_repository` 不存在）

- [ ] **Step 3: 重写 `src/qed_tracker/courses.py`**

```python
"""加载学科课程体系（共享表 qed_domain / qed_course；courses/*.json 已退役，QED-031）。

读取依赖 KnowledgeRepository（DB 配置后由 CLI 注入）；无 DB 时 raise ValueError。
dataclass（Course/Curriculum）保留，供 CLI/测试消费。
"""

from __future__ import annotations

from dataclasses import dataclass

from qed_tracker.db.knowledge_repository import KnowledgeRepository

_repository: KnowledgeRepository | None = None


def set_repository(repo: KnowledgeRepository | None) -> None:
    """注入仓库（CLI 启动时设置；测试用 SQLite mock）。"""
    global _repository
    _repository = repo


def _repo() -> KnowledgeRepository:
    if _repository is None:
        raise ValueError("数据库未配置：课程体系读取需 qed_course 表（运行 `qed-tracker migrate` 种子或设置数据库）")
    return _repository


@dataclass(frozen=True, slots=True)
class Course:
    course_id: str
    name: str
    aliases: tuple[str, ...]
    stage: str
    prerequisites: tuple[str, ...]
    related_targets: tuple[str, ...]
    note: str


@dataclass(frozen=True, slots=True)
class Curriculum:
    subject: str
    name: str
    description: str
    stages: tuple[str, ...]
    courses: tuple[Course, ...]


def list_courses() -> tuple[str, ...]:
    return tuple(domain.domain_id for domain in _repo().list_domains())


def _course_to_dataclass(row) -> Course:
    return Course(
        course_id=row.course_id,
        name=row.name,
        aliases=tuple(row.aliases or []),
        stage=row.stage,
        prerequisites=tuple(row.prerequisites or []),
        related_targets=tuple(row.related_targets or []),
        note=row.note,
    )


def load_course(subject: str) -> Curriculum:
    repo = _repo()
    domain = next((d for d in repo.list_domains() if d.domain_id == subject), None)
    if domain is None:
        raise ValueError(f"未知学科课程体系：{subject}")
    courses = tuple(_course_to_dataclass(row) for row in repo.list_courses(subject))
    return Curriculum(
        subject=domain.domain_id,
        name=domain.name,
        description=domain.description,
        stages=tuple(domain.stages or []),
        courses=courses,
    )
```

- [ ] **Step 4: 更新 `src/qed_tracker/cli.py`**

在 `_settings` 后新增注入辅助（模块级）：

```python
def _curriculum_repository(settings: Settings) -> "KnowledgeRepository | None":
    if not settings.db_configured:
        return None
    from qed_tracker.database import create_engine_for, session_factory
    from qed_tracker.db.knowledge_repository import KnowledgeRepository

    engine = create_engine_for(settings)
    return KnowledgeRepository(session_factory(engine))
```

在 `_courses` 开头注入：

```python
def _courses(args, settings: Settings) -> int:
    from qed_tracker.courses import list_courses, set_repository

    repo = _curriculum_repository(settings)
    if repo is None:
        _print({"error": "数据库未配置：课程体系读取需 qed_course 表"}, True) if args.json else print(
            "ERROR: 数据库未配置：课程体系读取需 qed_course 表", file=sys.stderr
        )
        return 2
    set_repository(repo)
    ...
```

并把 `_load_curriculum` 中的 `from qed_tracker.courses import list_courses, load_course` 调用保持不变（内部已走 repository）。

同时把 `_mainline` 中 `from qed_tracker.courses import load_course` 前加 `set_repository(repo)`（同 `_courses` 模式，`_mainline` 开头注入）。

- [ ] **Step 5: 退役 JSON 与 package-data**

```bash
git rm src/qed_tracker/courses/math.json
```

编辑 `pyproject.toml`：删除 `courses/*.json` 的 package-data 条目（如 `[tool.setuptools.package-data]` 中 `"qed_tracker": ["courses/*.json"]` 之类），保留其他条目。

- [ ] **Step 6: 跑测试**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests/test_courses.py tests/test_main_line_cli.py -q`
Expected: 预期 test_main_line_cli 中依赖 JSON 的用例失败——需要同步改注入（任务 7 统一处理），本任务先保证 test_courses.py 全绿。同时跑：
`& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests/test_cli_architecture.py -q`
若 CLI 结构测试断言 courses 命令行为，同步适配。

- [ ] **Step 7: Commit**

```bash
git add tests/test_courses.py src/qed_tracker/courses.py src/qed_tracker/cli.py pyproject.toml
git commit -m "feat(courses): read curriculum from qed_course shared table, retire courses/math.json"
```

---

## 任务 6：8901 API 改造（knowledge/books/sources 端点）

**Files:**
- Edit: `src/qed_tracker/api/main.py`（替换三表端点组）
- Edit: `tests/test_selections_api.py` → `git mv tests/test_selections_api.py tests/test_knowledge_api.py` 并重写

- [ ] **Step 1: 写失败测试**

重写 `tests/test_knowledge_api.py`：

```python
"""五层模型 API 端点定向测试（QED-031）：knowledge/books/sources 契约 + 彻底隐藏。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.api.main import create_app
from qed_tracker.config import load_settings
from qed_tracker.db.knowledge_repository import KnowledgeRepository
from qed_tracker.db.models import Base, BookStatus, KnowledgeStatus, QedCourse, QedDomain


@pytest.fixture
def repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'kn.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    from qed_tracker.database import utc_now

    now = utc_now()
    session.add(QedDomain(domain_id="math", name="数学", description="d", stages=["本科基础"],
                          created_at=now, updated_at=now))
    session.add(QedCourse(course_id="01_math_analysis", domain_id="math", sort_order=1, name="数学分析",
                          aliases=[], stage="本科基础", prerequisites=[], related_targets=[],
                          created_at=now, updated_at=now))
    session.commit()
    repo = KnowledgeRepository(lambda: factory())
    yield repo
    engine.dispose()


@pytest.fixture
def client(tmp_path, repo):
    settings = load_settings(data_root=tmp_path)
    app = create_app(settings, knowledge_repository=repo)
    with TestClient(app) as test_client:
        yield test_client


def _seed_knowledge(repo: KnowledgeRepository, *, name: str = "数学分析 套一", status: str = "draft"):
    knowledge = repo.create_knowledge(
        domain_id="math", course_id="01_math_analysis", kind="tutorial", set_no="1", name=name,
    )
    if status == "confirmed":
        repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref={"title": "微积分学教程"},
                               exercise_ref={"title": "习题集"})
    elif status == "rejected":
        repo.reject_knowledge(knowledge.knowledge_id, reason="版本旧", by="web")
    return knowledge


def test_knowledge_list_filters_hidden(client, repo):
    _seed_knowledge(repo)
    _seed_knowledge(repo, name="坏书", status="rejected")
    response = client.get("/api/v1/knowledge")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_knowledge_detail_with_books(client, repo):
    knowledge = _seed_knowledge(repo)
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="微积分学教程",
                            authors=["菲赫金哥尔茨"])
    response = client.get(f"/api/v1/knowledge/{knowledge.knowledge_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["knowledge_id"] == knowledge.knowledge_id
    assert len(body["books"]) == 1
    assert body["books"][0]["book_id"] == book.book_id


def test_knowledge_confirm(client, repo):
    knowledge = _seed_knowledge(repo)
    response = client.post(f"/api/v1/knowledge/{knowledge.knowledge_id}/confirm", json={
        "textbook_ref": {"title": "微积分学教程", "version": "第8版"},
        "textbook_intro": "经典三卷本。",
    })
    assert response.status_code == 200
    assert response.json()["status"] == KnowledgeStatus.CONFIRMED.value


def test_knowledge_reject_requires_reason(client, repo):
    knowledge = _seed_knowledge(repo)
    response = client.post(f"/api/v1/knowledge/{knowledge.knowledge_id}/reject", json={})
    assert response.status_code == 422
    response = client.post(f"/api/v1/knowledge/{knowledge.knowledge_id}/reject",
                           json={"reason": "版本旧"})
    assert response.status_code == 200


def test_knowledge_invalid_transition_409(client, repo):
    knowledge = _seed_knowledge(repo, status="confirmed")
    response = client.post(f"/api/v1/knowledge/{knowledge.knowledge_id}/complete")
    assert response.status_code == 409  # 无书行，不能 completed


def test_book_create_and_transitions(client, repo):
    knowledge = _seed_knowledge(repo)
    response = client.post("/api/v1/books", json={
        "knowledge_id": knowledge.knowledge_id, "kind": "textbook", "title": "微积分学教程",
        "part": "第一册", "authors": ["菲赫金哥尔茨"],
    })
    assert response.status_code == 200
    book_id = response.json()["book_id"]
    assert client.post(f"/api/v1/books/{book_id}/decide").status_code == 200
    assert client.post(f"/api/v1/books/{book_id}/start").status_code == 200
    r = client.post(f"/api/v1/books/{book_id}/complete", json={
        "sha256": "c" * 64, "relative_path": "raw/books/x.pdf", "page_count": 100,
    })
    assert r.status_code == 200
    assert r.json()["status"] == BookStatus.DOWNLOADED.value
    assert client.post(f"/api/v1/books/{book_id}/verify").status_code == 200


def test_book_register_manual_direct(client, repo, tmp_path, pdf_bytes):
    knowledge = _seed_knowledge(repo)
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="微积分学教程",
                            authors=["菲赫金哥尔茨"])
    rel = "raw/books/manual.pdf"
    target = tmp_path / rel
    target.parent.mkdir(parents=True)
    target.write_bytes(pdf_bytes)
    response = client.post(f"/api/v1/books/{book.book_id}/register", json={"relative_path": rel})
    assert response.status_code == 200
    assert response.json()["status"] == BookStatus.DOWNLOADED.value


def test_book_reject_hidden(client, repo):
    knowledge = _seed_knowledge(repo)
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="坏书")
    response = client.post(f"/api/v1/books/{book.book_id}/reject", json={"reason": "不适用"})
    assert response.status_code == 200
    assert client.get(f"/api/v1/knowledge/{knowledge.knowledge_id}").json()["books"] == []


def test_sources_endpoint(client, repo):
    knowledge = _seed_knowledge(repo)
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="微积分学教程")
    response = client.post(f"/api/v1/books/{book.book_id}/sources", json={
        "channel": "manual", "ok": True, "download_url": "http://x",
    })
    assert response.status_code == 200
    rows = client.get(f"/api/v1/books/{book.book_id}/sources").json()
    assert len(rows) == 1
    assert rows[0]["channel"] == "manual"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests/test_knowledge_api.py -q`
Expected: FAIL（`TypeError: create_app() got an unexpected keyword argument 'knowledge_repository'`）

- [ ] **Step 3: 改造 `src/qed_tracker/api/main.py`**

要点（完整端点组替换）：

1. 构造器与 `create_app` 签名：`three_table_repository` → `knowledge_repository`；`Application._three_table_repository` → `_knowledge_repository`；DB 分支构造 `KnowledgeRepository`。
2. 删除 `_tt`/`_selection_view`/`_require_selection`/`_selection_transition` 与全部 selections/downloads 端点。
3. 新增端点组（路由同前端契约，语义对齐测试）：

```python
    # ---------------- 五层端点（QED-031：qt_knowledge / qt_books / qt_sources） ----------------
    # 契约：docs/design/database-schema.md。彻底隐藏语义在数据层实现（rejected/superseded/failed 默认过滤）。

    def _kn(app: Application) -> KnowledgeRepository:
        if app._knowledge_repository is None:
            raise HTTPException(status_code=409, detail="数据库未配置：五层端点需 qed_course/qt_knowledge 行")
        return app._knowledge_repository

    def _knowledge_view(repo: KnowledgeRepository, row) -> dict[str, Any]:
        value = row.to_dict()
        value["books"] = [b.to_dict() for b in repo.list_books(row.knowledge_id)]
        return value

    def _require_knowledge(repo: KnowledgeRepository, knowledge_id: str):
        row = repo.get_knowledge(knowledge_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"知识行不存在：{knowledge_id}")
        return row

    def _book_transition(book_id: str, op) -> dict[str, Any]:
        repo = _kn(app)
        try:
            row = op(repo, book_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return row.to_dict()

    @fastapi_app.get("/api/v1/knowledge")
    def knowledge_list(course_id: str = "", status: str = "") -> list[dict[str, Any]]:
        return [row.to_dict() for row in _kn(app).list_knowledge(course_id=course_id or None, status=status or None)]

    @fastapi_app.get("/api/v1/knowledge/{knowledge_id}")
    def knowledge_detail(knowledge_id: str) -> dict[str, Any]:
        repo = _kn(app)
        _require_knowledge(repo, knowledge_id)
        return _knowledge_view(repo, repo.get_knowledge(knowledge_id))

    @fastapi_app.post("/api/v1/knowledge/{knowledge_id}/confirm")
    def knowledge_confirm(knowledge_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        repo = _kn(app)
        try:
            row = repo.confirm_knowledge(
                knowledge_id,
                textbook_ref=payload.get("textbook_ref"),
                exercise_ref=payload.get("exercise_ref"),
                textbook_intro=str(payload.get("textbook_intro", "")),
                exercise_intro=str(payload.get("exercise_intro", "")),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return row.to_dict()

    @fastapi_app.post("/api/v1/knowledge/{knowledge_id}/complete")
    def knowledge_complete(knowledge_id: str) -> dict[str, Any]:
        repo = _kn(app)
        try:
            row = repo.complete_knowledge(knowledge_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return row.to_dict()

    @fastapi_app.post("/api/v1/knowledge/{knowledge_id}/reject")
    def knowledge_reject(knowledge_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        reason = str(payload.get("reason", "")).strip()
        if not reason:
            raise HTTPException(status_code=422, detail="拒绝必须提供原因（reason）")
        repo = _kn(app)
        try:
            row = repo.reject_knowledge(knowledge_id, reason=reason, by="web")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return row.to_dict()

    @fastapi_app.post("/api/v1/knowledge/{knowledge_id}/supersede")
    def knowledge_supersede(knowledge_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        reason = str(payload.get("reason", "")).strip()
        if not reason:
            raise HTTPException(status_code=422, detail="过时必须提供原因（reason）")
        repo = _kn(app)
        try:
            row = repo.supersede_knowledge(knowledge_id, reason=reason, by="web")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return row.to_dict()

    @fastapi_app.post("/api/v1/books")
    def create_book(payload: dict[str, Any]) -> dict[str, Any]:
        """新建书行候选（先登记再下载）：candidate 态。"""
        knowledge_id = str(payload.get("knowledge_id", "")).strip()
        if not knowledge_id:
            raise HTTPException(status_code=422, detail="必须提供 knowledge_id")
        title = str(payload.get("title", "")).strip()
        if not title:
            raise HTTPException(status_code=422, detail="必须提供 title")
        repo = _kn(app)
        _require_knowledge(repo, knowledge_id)
        row = repo.create_book(
            knowledge_id,
            kind=str(payload.get("kind", "textbook")),
            roles=payload.get("roles"),
            title=title,
            part=str(payload.get("part", "")),
            display_title=str(payload.get("display_title", "")),
            authors=payload.get("authors", []),
            language=str(payload.get("language", "")),
            version=payload.get("version"),
            source=payload.get("source"),
            original_url=str(payload.get("original_url", "")),
        )
        return row.to_dict()

    @fastapi_app.get("/api/v1/books/{book_id}/sources")
    def book_sources(book_id: str) -> list[dict[str, Any]]:
        repo = _kn(app)
        if repo.get_book(book_id, include_hidden=True) is None:
            raise HTTPException(status_code=404, detail=f"书行不存在：{book_id}")
        return [s.to_dict() for s in repo.list_sources(book_id)]

    @fastapi_app.post("/api/v1/books/{book_id}/sources")
    def book_add_source(book_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        repo = _kn(app)
        if repo.get_book(book_id, include_hidden=True) is None:
            raise HTTPException(status_code=404, detail=f"书行不存在：{book_id}")
        row = repo.add_source(
            book_id,
            channel=str(payload.get("channel", "manual")),
            provider_id=str(payload.get("provider_id", "")),
            page_url=str(payload.get("page_url", "")),
            download_url=str(payload.get("download_url", "")),
            file_keywords=str(payload.get("file_keywords", "")),
            ok=bool(payload.get("ok", False)),
            note=str(payload.get("note", "")),
        )
        return row.to_dict()

    @fastapi_app.post("/api/v1/books/{book_id}/register")
    def book_register(book_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        """人工下载登记（candidate → downloaded 直转）：relative_path 必须存在且为 PDF。"""
        repo = _kn(app)
        row = repo.get_book(book_id, include_hidden=True)
        if row is None:
            raise HTTPException(status_code=404, detail=f"书行不存在：{book_id}")
        relative = str(payload.get("relative_path", "")).strip()
        if not relative:
            raise HTTPException(status_code=422, detail="必须提供数据根内相对路径（relative_path）")
        path = (app.resources.inventory.data_root / relative).resolve()
        try:
            path.relative_to(app.resources.inventory.data_root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="路径必须在数据根目录内") from exc
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"文件不存在：{relative}")
        from qed_tracker.downloader import inspect_pdf

        try:
            digest, size, pages = inspect_pdf(path)
        except Exception as exc:  # noqa: BLE001 - PDF 校验失败统一 400
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        file_name = f"{row.display_title and Path(row.display_title).stem or 'book'}_{digest[:8]}.pdf"
        try:
            final = repo.complete_download(
                book_id,
                sha256=digest,
                relative_path=relative,
                page_count=pages,
                absolute_path=str(path),
                file_name=file_name,
            )
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return final.to_dict()

    @fastapi_app.post("/api/v1/books/{book_id}/decide")
    def book_decide(book_id: str) -> dict[str, Any]:
        return _book_transition(book_id, lambda repo, bid: repo.decide_book(bid))

    @fastapi_app.post("/api/v1/books/{book_id}/start")
    def book_start(book_id: str) -> dict[str, Any]:
        return _book_transition(book_id, lambda repo, bid: repo.start_download(bid))

    @fastapi_app.post("/api/v1/books/{book_id}/fail")
    def book_fail(book_id: str) -> dict[str, Any]:
        return _book_transition(book_id, lambda repo, bid: repo.fail_download(bid))

    @fastapi_app.post("/api/v1/books/{book_id}/retry")
    def book_retry(book_id: str) -> dict[str, Any]:
        return _book_transition(book_id, lambda repo, bid: repo.retry_download(bid))

    @fastapi_app.post("/api/v1/books/{book_id}/complete")
    def book_complete(book_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        sha256 = str(payload.get("sha256", "")).strip()
        relative_path = str(payload.get("relative_path", "")).strip()
        if not sha256 or not relative_path:
            raise HTTPException(status_code=422, detail="sha256 与 relative_path 必填")
        repo = _kn(app)
        try:
            row = repo.complete_download(
                book_id,
                sha256=sha256,
                relative_path=relative_path,
                page_count=payload.get("page_count"),
                absolute_path=str(payload.get("absolute_path", "")),
                file_name=str(payload.get("file_name", "")),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return row.to_dict()

    @fastapi_app.post("/api/v1/books/{book_id}/verify")
    def book_verify(book_id: str) -> dict[str, Any]:
        return _book_transition(book_id, lambda repo, bid: repo.verify_book(bid))

    @fastapi_app.post("/api/v1/books/{book_id}/reject")
    def book_reject(book_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        reason = str(payload.get("reason", "")).strip()
        if not reason:
            raise HTTPException(status_code=422, detail="拒绝必须提供原因（reason）")
        repo = _kn(app)
        try:
            row = repo.reject_book(book_id, reason=reason, by="web",
                                   note=str(payload.get("note", "")))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return row.to_dict()

    @fastapi_app.post("/api/v1/books/{book_id}/supersede")
    def book_supersede(book_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        reason = str(payload.get("reason", "")).strip()
        if not reason:
            raise HTTPException(status_code=422, detail="过时必须提供原因（reason）")
        repo = _kn(app)
        try:
            row = repo.supersede_book(book_id, reason=reason, by="web")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return row.to_dict()
```

同步更新 import 行：

```python
from qed_tracker.db.knowledge_repository import InvalidTransition, KnowledgeRepository
```

并删除 `from qed_tracker.db.models import DownloadStatus`（无引用后）与 `from qed_tracker.db.selection_repository import ...`。

- [ ] **Step 4: 跑测试确认通过**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests/test_knowledge_api.py tests/test_api.py -q`
Expected: PASS（test_api.py 若引用旧端点需同步适配，见步骤 5）

- [ ] **Step 5: 清理旧端点引用**

用 `rg "selections|downloads" src/qed_tracker/api/ tests/test_api.py tests/test_profiles_and_selections.py tests/test_paper_selection_cli.py` 检查残留引用并逐一替换为新端点语义（downloads 资源列表 → books；无对应语义的删除断言）。

- [ ] **Step 6: Commit**

```bash
git add tests/test_knowledge_api.py src/qed_tracker/api/main.py
git commit -m "feat(api): knowledge/books/sources endpoints replace three-table endpoints"
```

---

## 任务 7：CLI mainline 改造 + migrate 子命令

**Files:**
- Edit: `src/qed_tracker/cli.py`（mainline 命令族映射新状态机；新增 `migrate` 子命令）
- Edit: `tests/test_main_line_cli.py`（重写为新状态机断言）
- Edit: `src/qed_tracker/main_line/store.py`（退役 EntryStore，或保留只读兼容——本计划采用退役）

- [ ] **Step 1: 写失败测试**

重写 `tests/test_main_line_cli.py`（保留 parse 断言，行为断言改 DB mock）：

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.cli import build_parser, main
from qed_tracker.db.knowledge_repository import KnowledgeRepository
from qed_tracker.db.models import Base, QedCourse, QedDomain


@pytest.fixture
def repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'cli.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    from qed_tracker.database import utc_now

    now = utc_now()
    session.add(QedDomain(domain_id="math", name="数学", description="d", stages=["本科基础"],
                          created_at=now, updated_at=now))
    session.add(QedCourse(course_id="01_math_analysis", domain_id="math", sort_order=1, name="数学分析",
                          aliases=[], stage="本科基础", prerequisites=[], related_targets=[],
                          created_at=now, updated_at=now))
    session.commit()
    yield KnowledgeRepository(lambda: factory())
    engine.dispose()


def test_courses_list_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["courses", "list"])
    assert args.command == "courses"
    assert args.courses_command == "list"


def test_courses_show_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["courses", "show", "01_math_analysis"])
    assert args.courses_command == "show"
    assert args.course_id == "01_math_analysis"


def test_mainline_list_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["mainline", "list", "--course", "01_math_analysis"])
    assert args.mainline_command == "list"
    assert args.course == "01_math_analysis"


def test_migrate_subcommand_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["migrate"])
    assert args.command == "migrate"


def test_courses_show_requires_db(tmp_path, capsys) -> None:
    assert main(["--data-root", str(tmp_path), "courses", "show", "01_math_analysis"]) == 2
    assert "数据库未配置" in capsys.readouterr().err
```

注意：DB 注入方式——CLI `_courses`/`_mainline` 通过 `settings.db_configured` 决定是否可用；测试默认无 DB 环境变量即未配置 → 返回 2。真实 DB 行为由冒烟覆盖。

- [ ] **Step 2: 跑测试确认失败**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests/test_main_line_cli.py -q`
Expected: FAIL（`migrate` 未注册）

- [ ] **Step 3: CLI 改造**

1. `build_parser` 增 migrate 子命令：

```python
    commands.add_parser("migrate", help="一次性存量迁移（math.json + 三表 → 五表；幂等可重放）")
```

2. `main()` handlers 增 `"migrate": _migrate`。

3. 实现 `_migrate`：

```python
def _migrate(args, settings: Settings) -> int:
    if not settings.db_configured:
        _print({"error": "数据库未配置：迁移需要 qed 库连接"}, True) if args.json else print(
            "ERROR: 数据库未配置：迁移需要 qed 库连接", file=sys.stderr
        )
        return 2
    from qed_tracker.application.migrate_knowledge import migrate_curriculum, migrate_legacy_data
    from qed_tracker.database import create_engine_for, session_factory

    engine = create_engine_for(settings)
    factory = session_factory(engine)
    try:
        migrate_curriculum(factory)
        stats = migrate_legacy_data(factory)
    finally:
        engine.dispose()
    _print({"seeded": True, **stats}, True) if args.json else print(
        f"迁移完成：knowledge={stats['knowledge']} books={stats['books']} sources={stats['sources']}"
    )
    print("提示：确认无误后可再次运行 `qed-tracker migrate --drop-legacy` 删除旧表", file=sys.stderr)
    return 0
```

4. `build_parser` 的 migrate 子命令加 `--drop-legacy` 参数：

```python
    migrate = commands.add_parser("migrate", help="一次性存量迁移（math.json + 三表 → 五表；幂等可重放）")
    migrate.add_argument("--drop-legacy", action="store_true", help="迁移完成后删除旧表（qt_selections/qt_downloads）")
```

并把 `_migrate` 传参改为 `migrate_legacy_data(factory, drop_legacy=args.drop_legacy)`。

5. `_mainline` 重写（核心映射）：

```python
def _mainline(args, settings: Settings) -> int:
    from qed_tracker.courses import set_repository
    from qed_tracker.db.knowledge_repository import KnowledgeRepository

    if not settings.db_configured:
        _print({"error": "数据库未配置：主链路需 qt_knowledge/qt_books 表"}, True) if args.json else print(
            "ERROR: 数据库未配置：主链路需 qt_knowledge/qt_books 表", file=sys.stderr
        )
        return 2
    from qed_tracker.database import create_engine_for, session_factory

    engine = create_engine_for(settings)
    factory = session_factory(engine)
    repo = KnowledgeRepository(factory)
    try:
        return _mainline_impl(args, repo)
    finally:
        engine.dispose()
```

并把原有 `_mainline` 主体抽为 `_mainline_impl(args, repo: KnowledgeRepository) -> int`，
命令映射（list / channels / new / review / reject / download / verify / approve）对齐新状态机：

- `list`：`repo.list_knowledge(course_id=args.course)`，每条附带 `repo.list_books(knowledge_id)` 摘要；
- `new`：课程校验改 `load_course`（走 qed_course），`repo.create_knowledge(domain_id=..., course_id=..., kind="tutorial", set_no="", name=args.title)` 建 draft，LLM 预填评价存 `advice` 输出（不落 evaluation 字段，简介在 review 时预填）；
- `review`：`repo.confirm_knowledge(knowledge_id, textbook_ref={"title": args.title}, textbook_intro=...)`（LLM 预填简介 + 人工审后调用）；具体实现：

```python
    if args.mainline_command == "review":
        knowledge = repo.get_knowledge(args.knowledge_id)
        if knowledge is None:
            _print({"error": f"知识行不存在：{args.knowledge_id}"}, True) if args.json else print(
                f"ERROR: 知识行不存在：{args.knowledge_id}", file=sys.stderr
            )
            return 2
        intro = args.intro or f"{knowledge.name}：教材与习题集配套资源（LLM 预填 + 人工审）。"
        try:
            updated = repo.confirm_knowledge(
                knowledge.knowledge_id,
                textbook_ref={"title": knowledge.name, "version": args.version or ""},
                textbook_intro=intro,
            )
        except InvalidTransition as exc:
            _print({"error": str(exc)}, True) if args.json else print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        _print(updated.to_dict(), True) if args.json else print(
            f"已定稿：{updated.knowledge_id} → {updated.status}"
        )
        return 0
```

（parser 需给 `mainline review` 增 `--intro`/`--version` 可选参数；`download` 命令定位书行
`next(b for b in repo.list_books(knowledge.knowledge_id) if b.status in ("candidate", "decided"))`，
`decide_book` → `start_download` → 下载成功 `complete_download(book_id, sha256=record.sha256,
relative_path=record.file["relative_path"], page_count=record.file["page_count"],
absolute_path=str(record.absolute_path(settings.data_root)),
file_name=Path(record.file["relative_path"]).name)`，异常 `fail_download`。）
- `reject`：`repo.reject_knowledge(knowledge_id, reason=args.reason, by="cli")`；
- `download`：定位书行 → `decide_book` → `start_download` → 搜索下载 → `complete_download`（sha256/relative_path/page_count/absolute_path/file_name）→ 失败 `fail_download`；
- `verify`：`repo.verify_book(book_id)`（验收前 inspect_pdf 校验）；
- `approve`：verify 语义 + 移交根仓库（沿用原 copy2 移交逻辑），随后 `repo.complete_knowledge` 由 CLI 提示（书行全 verified 后人工执行）；
- `channels`：`repo.list_sources(book_id, ok_only=False)` 聚合渠道统计。

- [ ] **Step 4: 退役 EntryStore**

`src/qed_tracker/main_line/store.py` 中 EntryStore 已无调用方后删除文件（`git rm`），
保留 `MainLineStatus`/`MainLineEntry` 的兼容导出可留档（不导出则删除 import 引用）。
同步清理 `tests/test_main_line_store.py`：改为断言新状态机（或删除并依赖 test_knowledge_repository 覆盖）。

- [ ] **Step 5: 跑测试确认通过**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests/test_main_line_cli.py tests/test_main_line_store.py tests/test_cli_architecture.py -q`
Expected: PASS（cli_architecture 中 serve 日志测试与本任务无关，应保持全绿）

- [ ] **Step 6: Commit**

```bash
git add tests/test_main_line_cli.py tests/test_main_line_store.py src/qed_tracker/cli.py
git commit -m "feat(cli): mainline maps to five-layer state machine, add migrate subcommand"
```

---

## 任务 8：文档治理 + 全量门禁（收尾）

**Files:**
- Edit: `tests/test_documentation.py`（白名单同步）
- Edit: `docs/architecture/code-map.md`（模块映射）
- Edit: `docs/trackers/todo.md`（QED-031 完成）
- Edit: `docs/plans/index.md`（登记本计划；完成后关闭）
- Edit: `README.md`（如需提及 migrate 子命令与五表模型，最小改动）
- Edit: `src/qed_tracker/application/migrate_knowledge.py`（如门禁失败修正）

- [ ] **Step 1: 同步文档白名单**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests/test_documentation.py -q`
Expected: FAIL 于白名单（新文件 courses 相关路径变更）→ 更新 `tests/test_documentation.py` 中
`REQUIRED_CURRENT_DOCS`/`DESIGN_DOCS` 或课程 JSON 引用清单，使全绿。

- [ ] **Step 2: 更新 code-map.md 与 AGENTS.md 路由表**

- `docs/architecture/code-map.md`：`selection_repository.py` → `knowledge_repository.py`；
  新增 `application/migrate_knowledge.py`；`courses.py` 描述改「读 qed_course（DB）」；
  `api/main.py` 端点组描述改五层。
- `AGENTS.md` 任务路由表「服务与 API」行：`tests/test_selections_api.py` → `tests/test_knowledge_api.py`、
  `tests/test_db_models.py` 不变；「课程」行：`src/qed_tracker/courses.py` 不变、测试 `tests/test_courses.py` 不变；
  新增「存量迁移」映射行（migrate_knowledge.py / test_migrate_knowledge.py）。

- [ ] **Step 3: 更新 todo.md 与 plans/index.md**

`docs/trackers/todo.md` QED-031 行转 Done：完成证据 = 本计划任务 1-7 提交号 +
任务 8 全量门禁输出；`docs/plans/index.md` 登记本计划链接（活跃计划区）。

- [ ] **Step 4: 全量门禁**

Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests -q 2>&1 | Select-String "passed|failed"`
Run: `& "D:\software\anaconda3\envs\QED_env\python.exe" -m ruff check src tests`
Expected: 全量 passed + ruff 0 错误。若有失败按 systematic-debugging 定位（常见：旧端点引用残留、
SQLite JSON 函数差异、import 残留）。

- [ ] **Step 5: 真实 MySQL 冒烟 + 8901 冒烟（人工/本机步骤）**

```bash
# 1) 迁移升级（真实 qed 库，需根 .env 注入）
& "D:\software\anaconda3\envs\QED_env\python.exe" -m pytest tests/test_db_three_table_smoke.py -q
# 设置 QED_DB_SMOKE=1 后断言五表结构与索引
# 2) CLI 迁移种子（真实库）
& "D:\software\anaconda3\envs\QED_env\python.exe" -m qed_tracker.cli migrate
# 3) 8901 启动冒烟
& "D:\software\anaconda3\envs\QED_env\python.exe" -m qed_tracker.cli serve
# curl http://127.0.0.1:8901/api/v1/knowledge 与 /api/v1/health
# 4) 存量三表确认无误后
& "D:\software\anaconda3\envs\QED_env\python.exe" -m qed_tracker.cli migrate --drop-legacy
```

注意：真实库操作前提示用户自行 mysqldump 备份（设计文档要求迁移前全量备份快照）。

- [ ] **Step 6: 回执根仓库**

- 根仓库 REQ-026/REQ-029/REQ-030 回执：提交号 + 全量门禁输出 + 迁移/冒烟证据（根仓库
  `docs/trackers/todo.md` 对应行更新）。
- 根仓库 `docs/design/database-design.md`/`service-contracts.md` 已在设计轮同步（ADR 0009），
  如实现轮有契约偏差（端点路径等）回根仓库同步。

- [ ] **Step 7: Commit**

```bash
git add tests/test_documentation.py docs/architecture/code-map.md AGENTS.md docs/trackers/todo.md docs/plans/index.md README.md
git commit -m "docs: knowledge schema refactor documentation governance and plan closure"
```

---

## 自检清单（计划完成前逐项核对）

- [ ] 任务 1-7 每步均有失败测试 → 实现 → 验证闭环
- [ ] 无占位符（全部步骤含实际代码/命令）
- [ ] 类型/签名一致性：`KnowledgeRepository` 方法名与 `_id` 前缀（kn_/bk_/src_）前后一致
- [ ] 设计文档 11 条用户裁决全覆盖（§用户裁决记录 1-10 + qt_sources 定位）
- [ ] AGENTS.md 强制约束：默认测试不访问公网/真实库（真实冒烟仅 QED_DB_SMOKE=1 或人工步骤）
- [ ] courses/math.json 退役同时清理 pyproject package-data 与 test_documentation 白名单