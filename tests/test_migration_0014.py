"""0014_rebuild_qt_sources 迁移定向测试（离线 SQLite，不依赖 MySQL）。

覆盖四种库状态：旧结构改名留档 / 旧结构+已有备份 / 全新库补建 / 已是新结构（no-op）。
迁移模块以 importlib 按路径加载（文件名以数字开头无法常规 import）。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "src" / "qed_tracker" / "migrations" / "versions" / "0014_rebuild_qt_sources.py"
)


def _load_upgrade():
    spec = importlib.util.spec_from_file_location("migration_0014", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.upgrade


def _run_upgrade(engine: Engine) -> None:
    upgrade = _load_upgrade()
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            upgrade()


_OLD_QT_SOURCES_DDL = """
CREATE TABLE qt_sources (
    source_id VARCHAR(100) PRIMARY KEY,
    download_id VARCHAR(100) NOT NULL,
    channel VARCHAR(24) NOT NULL,
    provider_id VARCHAR(200) NOT NULL DEFAULT '',
    page_url VARCHAR(1000) NOT NULL DEFAULT '',
    download_url VARCHAR(1000) NOT NULL DEFAULT '',
    file_keywords VARCHAR(500) NOT NULL DEFAULT '',
    ok SMALLINT NOT NULL DEFAULT 0,
    note VARCHAR(1000) NOT NULL DEFAULT '',
    attempted_at DATETIME NOT NULL
)
"""


def _create_old_shape(engine: Engine, *, rows: int = 2) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE qt_books (book_id VARCHAR(100) PRIMARY KEY)"))
        conn.execute(text(_OLD_QT_SOURCES_DDL))
        for i in range(rows):
            conn.execute(text(
                "INSERT INTO qt_sources (source_id, download_id, channel, attempted_at) "
                f"VALUES ('s{i}', 'd{i}', 'manual', '2026-01-0{i + 1} 00:00:00')"
            ))


def _columns(engine: Engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


def test_old_shape_renamed_and_rebuilt(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'a.db'}")
    _create_old_shape(engine)
    _run_upgrade(engine)
    assert "book_id" in _columns(engine, "qt_sources")
    assert "download_id" not in _columns(engine, "qt_sources")
    # 旧行留档
    legacy = _columns(engine, "qt_sources_legacy")
    assert "download_id" in legacy
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM qt_sources_legacy")).scalar() == 2


def test_old_shape_dropped_when_archive_exists(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'b.db'}")
    _create_old_shape(engine)
    with engine.begin() as conn:
        conn.execute(text(_OLD_QT_SOURCES_DDL.replace("qt_sources", "qt_sources_legacy")))
    _run_upgrade(engine)
    assert "book_id" in _columns(engine, "qt_sources")
    with engine.connect() as conn:
        # 备份表保持原样（本用例建空表），旧 qt_sources 已被清理
        assert conn.execute(text("SELECT COUNT(*) FROM qt_sources_legacy")).scalar() == 0


def test_fresh_database_creates_new_shape(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'c.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE qt_books (book_id VARCHAR(100) PRIMARY KEY)"))
    _run_upgrade(engine)
    assert {"source_id", "book_id", "channel", "ok", "attempted_at"} <= _columns(engine, "qt_sources")


def test_new_shape_is_noop(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'd.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE qt_books (book_id VARCHAR(100) PRIMARY KEY)"))
    _run_upgrade(engine)
    _run_upgrade(engine)  # 幂等重放
    assert "book_id" in _columns(engine, "qt_sources")
    assert not inspect(engine).has_table("qt_sources_legacy")


@pytest.mark.parametrize("table", ["qt_sources"])
def test_migration_module_is_ascii_only(table):
    """Windows/GBK 本地编码读迁移模块：文件必须 ASCII-only（0006/0013 同款约定）。"""
    content = MIGRATION_PATH.read_text(encoding="utf-8")
    content.encode("ascii")
