"""0015_add_domain_explore_pending 迁移定向测试（离线 SQLite）。

覆盖：全新库补列 / 幂等容忍标注 / ASCII-only 模块约定。
迁移模块以 importlib 按路径加载（文件名以数字开头无法常规 import）。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

MIGRATION_0013 = (
    Path(__file__).resolve().parents[1]
    / "src" / "qed_tracker" / "migrations" / "versions" / "0013_drop_runs_tables.py"
)
MIGRATION_0015 = (
    Path(__file__).resolve().parents[1]
    / "src" / "qed_tracker" / "migrations" / "versions" / "0015_add_domain_explore_pending.py"
)


def _load_upgrade(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.upgrade


def _run_upgrade(engine: Engine, path: Path) -> None:
    upgrade = _load_upgrade(path)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            upgrade()


def _columns(engine: Engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


def test_adds_explore_pending_column(tmp_path):
    """0015 upgrade 后 qed_domain 应含 explore_pending 列（nullable）。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'a.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE qed_domain (domain_id VARCHAR(32) PRIMARY KEY)"))
    _run_upgrade(engine, MIGRATION_0015)
    assert "explore_pending" in _columns(engine, "qed_domain")


def test_upgrade_is_noop_on_selected_domain(tmp_path):
    """幂等重放（含 0013 之后库状态）不抛异常。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'b.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE qed_domain (domain_id VARCHAR(32) PRIMARY KEY)"))
    _run_upgrade(engine, MIGRATION_0015)
    _run_upgrade(engine, MIGRATION_0015)
    assert "explore_pending" in _columns(engine, "qed_domain")


def test_migration_module_is_ascii_only():
    """Windows/GBK 本地编码读迁移模块：文件必须 ASCII-only（0006/0013/0014 同款约定）。"""
    content = MIGRATION_0015.read_text(encoding="utf-8")
    content.encode("ascii")
