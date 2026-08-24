"""五表模型（qed_domain/qed_course/qt_knowledge/qt_books/qt_sources）ORM 断言。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.db.models import (
    Base,
    BookStatus,
    ExploreRunStatus,
    KnowledgeStatus,
    QedCourse,
    QedDomain,
    QtBook,
    QtExploreRun,
    QtSource,
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


def test_explore_run_status_enum_complete() -> None:
    """探索运行七态（数据库线详规）：课程层五态 + 领域层 applied 两终态。"""
    assert {s.value for s in ExploreRunStatus} == {
        "running", "ready", "adopted", "discarded", "failed", "applied", "partially_applied",
    }


def test_legacy_three_tables_gone() -> None:
    """替换重构：旧三表模型不再存在（drop 由迁移/脚本负责，ORM 无残留）。"""
    tables = {t.name for t in Base.metadata.sorted_tables}
    assert "qt_selections" not in tables
    assert "qt_downloads" not in tables


def test_shared_tables_exist(session) -> None:
    tables = {t.name for t in Base.metadata.sorted_tables}
    assert {QedDomain.__tablename__, QedCourse.__tablename__} <= tables
    now = __import__("qed_tracker.database", fromlist=["utc_now"]).utc_now()
    domain = QedDomain(domain_id="math", name="数学", description="d", stages=["本科基础"], created_at=now, updated_at=now)
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


def test_qt_explore_runs_table_shape() -> None:
    """探索运行表（数据库线详规）：单表 JSON 方案，scope 区分课程层/领域层。"""
    table = QtExploreRun.__table__
    tables = {t.name for t in Base.metadata.sorted_tables}
    assert "qt_explore_runs" in tables
    columns = {c.name for c in table.columns}
    assert columns == {
        "run_id", "scope", "course_id", "domain_name", "status", "params",
        "proposals", "adopted_ids", "conflicts", "skipped", "error", "task_id", "meta",
        "created_by", "created_at", "updated_at",
    }
    indexes = {ix.name for ix in table.indexes}
    assert {"ix_qt_explore_runs_course", "ix_qt_explore_runs_domain", "ix_qt_explore_runs_status"} <= indexes