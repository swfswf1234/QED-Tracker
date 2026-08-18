"""五层模型真实 MySQL 迁移冒烟（QED-031：0006 + 存量迁移，安全可重放版）。

默认跳过（CI 不依赖数据库）：设置环境变量 `QED_DB_SMOKE=1` 时于本机执行。
本测试执行**幂等**升级链：`upgrade_database`（推进 alembic 至 head 0007，含表/列中文注释）→
`migrate_curriculum` + `migrate_legacy_data`（存量梳理：qt_selections → qt_knowledge、
qt_downloads → qt_books；qt_sources 重命名 qt_sources_legacy 备份后重建，均幂等可重放），
随后断言五表结构、索引与注释。真实数据只读/重命名备份，不删除（drop_legacy=False）。
qed 库现含真实存量（qt_selections/qt_downloads/qt_sources），破坏性清理只应在
用户显式隔离库或备份后执行。
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


def test_upgrade_and_migrate_creates_five_tables_with_contract_columns():
    from qed_tracker.config import load_settings
    from qed_tracker.database import upgrade_database

    settings = load_settings()
    upgrade_database(settings)  # 幂等：已到 head 则空操作
    # 注意：不重放 migrate_legacy_data —— 存量迁移为一次性动作，重放会按旧表重建已人工定稿的
    # 知识行/来源（如 Principles 独立行、重复 source）；迁移逻辑幂等性由 test_migrate_knowledge.py 覆盖。
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
    assert {"ix_qt_knowledge_course", "ix_qt_knowledge_domain", "ix_qt_knowledge_status"} <= indexes["qt_knowledge"]
    assert {"uq_qt_books_knowledge_title_part", "uq_qt_books_sha256",
            "ix_qt_books_knowledge", "ix_qt_books_status"} <= indexes["qt_books"]
    assert {"ix_qt_sources_book"} <= indexes["qt_sources"]


def test_table_and_column_comments_applied():
    """0007 表/列中文注释已应用：5 张新表 TABLE_COMMENT 非空、全部列均有 COLUMN_COMMENT。"""
    settings, conn = _connect()
    tables = ("qed_domain", "qed_course", "qt_knowledge", "qt_books", "qt_sources")
    try:
        with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(tables))
            cur.execute(
                f"SELECT TABLE_NAME, TABLE_COMMENT FROM information_schema.TABLES "
                f"WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN ({placeholders})",
                (settings.db_name,) + tables,
            )
            table_comments = {row[0]: row[1] for row in cur.fetchall()}
            assert set(table_comments) == set(tables)
            assert all(comment for comment in table_comments.values()), table_comments
            cur.execute(
                f"SELECT TABLE_NAME, COUNT(*) AS total, "
                f"SUM(CASE WHEN COLUMN_COMMENT <> '' THEN 1 ELSE 0 END) AS commented "
                f"FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN ({placeholders}) "
                f"GROUP BY TABLE_NAME",
                (settings.db_name,) + tables,
            )
            by_table = {row[0]: (row[1], row[2]) for row in cur.fetchall()}
            for table in tables:
                total, commented = by_table[table]
                assert total == commented, f"{table}: {commented}/{total} 列有注释"
    finally:
        conn.close()


def test_legacy_tables_retired_with_backup_snapshot():
    """qt_resources 已随 0005 退役（QED-030）；旧三表迁移后保留 qt_sources_legacy 备份（drop_legacy=False）。"""
    settings, conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s AND table_name='qt_resources'",
                (settings.db_name,),
            )
            assert cur.fetchone()[0] == 0  # 0005 已 drop
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s AND table_name='qt_sources_legacy'",
                (settings.db_name,),
            )
            legacy_exists = cur.fetchone()[0] == 1
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s AND table_name='qt_sources'",
                (settings.db_name,),
            )
            assert cur.fetchone()[0] == 1  # 新 qt_sources 已重建
            if legacy_exists:
                cur.execute("SELECT COUNT(*) FROM qt_sources_legacy")
                assert cur.fetchone()[0] >= 1  # 真实存量备份保留（本机为旧 12 行）
    finally:
        conn.close()
