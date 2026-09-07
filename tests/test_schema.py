"""ensure_schema 快照自愈测试（隔离 SQLite，零公网）。

v0.1 数据库策略（ADR 0006）：模型即 schema + 启动自愈——缺表补建、结构不一致重建、
幂等、qed_llm_calls 增量化自愈（缺失则建、缺列则补），未声明表一律不碰。

守卫契约：
- 7 张声明表（Base.metadata）：缺表补建、列集不一致重建、幂等。
- qed_llm_calls：缺失建表、缺列增量化补列（不 DROP），未声明表不被删除。
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from qed_tracker.db.models import Base
from qed_tracker.db.schema import ensure_schema

_QED_LLM_CALLS = "qed_llm_calls"


def _engine() -> sa.Engine:
    return sa.create_engine("sqlite:///:memory:", future=True)


def _table_names(engine: sa.Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def test_ensure_schema_creates_missing_tables() -> None:
    engine = _engine()
    ensure_schema(engine)
    names = _table_names(engine)
    assert {
        "qed_domain", "qed_course", "qt_knowledge",
        "qt_books", "qt_sources", "qt_tasks", "qt_selections",
    } <= names
    # 共享表不因 ensure 重建 qed_llm_calls 而残缺：required 列齐备
    cols = {c["name"] for c in inspect(engine).get_columns(_QED_LLM_CALLS)}
    assert {"task", "step", "review_status", "review_note"} <= cols


def test_ensure_schema_is_idempotent() -> None:
    engine = _engine()
    ensure_schema(engine)
    before = _table_names(engine)
    ensure_schema(engine)
    assert _table_names(engine) == before


def test_ensure_schema_rebuilds_on_column_mismatch() -> None:
    engine = _engine()
    Base.metadata.create_all(engine)
    # 模拟旧结构：qt_books 缺 original_title 列
    with engine.begin() as conn:
        conn.execute(sa.text("ALTER TABLE qt_books DROP COLUMN original_title"))
    cols_before = {c["name"] for c in inspect(engine).get_columns("qt_books")}
    assert "original_title" not in cols_before
    ensure_schema(engine)
    cols_after = {c["name"] for c in inspect(engine).get_columns("qt_books")}
    assert "original_title" in cols_after


def test_ensure_schema_adds_late_columns_to_qed_llm_calls() -> None:
    engine = _engine()
    # 手工建一个缺 REQ-060 列的 qed_llm_calls（基础 12 列 + id）
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE qed_llm_calls ("
                " id INTEGER PRIMARY KEY, service VARCHAR(32) NOT NULL, mode VARCHAR(16) NOT NULL,"
                " provider VARCHAR(32) NOT NULL, model VARCHAR(64) NOT NULL, endpoint VARCHAR(16) NOT NULL,"
                " prompt_template VARCHAR(255), prompt TEXT, response TEXT, duration_ms INTEGER,"
                " status VARCHAR(16) NOT NULL, error VARCHAR(500), created_at DATETIME NOT NULL)"
            )
        )
    ensure_schema(engine)
    cols = {c["name"] for c in inspect(engine).get_columns(_QED_LLM_CALLS)}
    assert {"task", "step", "review_status", "review_note"} <= cols
    # 不做 DROP：id 仍保留（增量化而非重建）
    assert "id" in cols


def test_ensure_schema_leaves_unknown_tables_alone() -> None:
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE some_foreign_table (x INTEGER)"))
    ensure_schema(engine)
    names = _table_names(engine)
    assert "some_foreign_table" in names
