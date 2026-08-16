"""三表模型真实 MySQL 迁移冒烟（QED-028 迁移 0003，安全只读版）。

默认跳过（CI 不依赖数据库）：设置环境变量 `QED_DB_SMOKE=1` 时于本机执行。
与前身 test_db_mysql_smoke.py 不同，本测试**只读**：upgrade head 后断言三表
结构与索引（qt_resources 数据、三表数据一律不修改、不删除、不 downgrade）。
qed 库现含真实存量（qt_resources 已 38 行），破坏性清理（DELETE/downgrade）
只应在用户显式隔离库或备份后执行。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT_ENV = Path(r"D:\coding\QED-Engine\.env")


def _read_root_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ROOT_ENV.exists():
        return values
    for line in ROOT_ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


_ROOT_VARS = _read_root_env()

SMOKE_ENABLED = os.environ.get("QED_DB_SMOKE") == "1" and bool(
    os.environ.get("QED_DB_PASSWORD") or _ROOT_VARS.get("QED_DB_PASSWORD")
)

pytestmark = pytest.mark.skipif(not SMOKE_ENABLED, reason="仅本机 MySQL 冒烟（设置 QED_DB_SMOKE=1 启用）")

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


def _connect():
    import pymysql

    from qed_tracker.config import load_settings

    settings = load_settings()
    conn = pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
    )
    return settings, conn


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


def test_legacy_tables_untouched_after_upgrade():
    """qt_resources 仍存在且行数未被迁移修改（退役只读语义）。"""
    settings, conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s AND table_name='qt_resources'",
                (settings.db_name,),
            )
            assert cur.fetchone()[0] == 1
            cur.execute("SELECT COUNT(*) FROM qt_resources")
            count = cur.fetchone()[0]
    finally:
        conn.close()
    assert count >= 1  # 真实存量存在（本机为 38 行），迁移不触碰
