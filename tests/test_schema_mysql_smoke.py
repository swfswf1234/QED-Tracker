"""ensure_schema 真实 MySQL 冒烟（v0.1 模型即 schema，ADR 0006）。

默认跳过（CI 不依赖数据库）；仅当同时满足以下条件才执行：
  - `QED_DB_SMOKE=1` 已设置，且
  - 目标库名为 `qed_test`（QED_DB_NAME=qed_test）——用于验证重建式自愈，
    绝不静默触达共享 `qed` 生产库。真实 `qed` 的更新是人工确认后执行的独立步骤。

本测试执行**幂等**的全库 self-heal（缺表补建 + 列不一致重建 + qed_llm_calls 增量自愈），
随后断言 7 张业务表结构与 qed_llm_calls 的 REQ-060 扩展列。
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


def _smoke_enabled() -> bool:
    if os.environ.get("QED_DB_SMOKE") != "1":
        return False
    if not (os.environ.get("QED_DB_PASSWORD") or _ROOT_VARS.get("QED_DB_PASSWORD")):
        return False
    # 只允许在 qed_test 上跑破坏性自愈，防止误伤共享 qed 生产库。
    return (os.environ.get("QED_DB_NAME") or _ROOT_VARS.get("QED_DB_NAME") or "qed") == "qed_test"


pytestmark = pytest.mark.skipif(
    not _smoke_enabled(),
    reason="仅本机 MySQL 冒烟：需 QED_DB_SMOKE=1 且 QED_DB_NAME=qed_test",
)

DOMAIN_COLUMNS = {
    "domain_id", "name", "description", "level", "scope", "exploration_stage",
    "classic_tracks", "stages", "path_results", "explore_pending",
    "created_by", "updated_by", "created_at", "updated_at",
}
COURSE_COLUMNS = {
    "course_id", "domain_id", "sort_order", "name", "aliases", "track", "stage",
    "prerequisites", "related_targets", "description", "exploration_stage", "explore_pending",
    "created_by", "updated_by", "created_at", "updated_at",
}
KNOWLEDGE_COLUMNS = {
    "knowledge_id", "course_id", "kind", "set_no", "name", "position", "intro",
    "textbook_ref", "exercise_ref", "parallel_ref", "status", "confirmed_at",
    "notes", "created_at", "updated_at",
}
BOOK_COLUMNS = {
    "book_id", "title", "original_title", "part", "authors", "publisher", "edition",
    "year", "language", "roles", "status", "retire_reason", "holding", "file_path",
    "priority", "notes", "domain_id", "created_at", "updated_at",
}
SOURCE_COLUMNS = {
    "source_id", "book_id", "channel", "provider_id", "page_url", "download_url",
    "file_keywords", "ok", "note", "attempted_at",
}
TASK_COLUMNS = {
    "task_id", "type", "status", "params", "progress", "message", "result", "error",
    "created_at", "updated_at",
}
SELECTION_COLUMNS = {
    "selection_id", "schema_version", "status", "created_at", "profile", "temporary_goal",
    "allowed_categories", "search_plan", "search_failures", "excluded_existing",
    "candidates", "assessments", "recommendations", "model", "downloads", "error",
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


def test_ensure_schema_heals_to_contract_columns():
    from qed_tracker.config import load_settings
    from qed_tracker.db.engine import create_engine_for, dispose
    from qed_tracker.db.schema import ensure_schema

    settings = load_settings()
    engine = create_engine_for(settings)
    try:
        ensure_schema(engine)
        ensure_schema(engine)  # 幂等：第二次不报错、不改结构
    finally:
        dispose(engine)

    settings, conn = _connect()
    tables = {
        "qed_domain": DOMAIN_COLUMNS,
        "qed_course": COURSE_COLUMNS,
        "qt_knowledge": KNOWLEDGE_COLUMNS,
        "qt_books": BOOK_COLUMNS,
        "qt_sources": SOURCE_COLUMNS,
        "qt_tasks": TASK_COLUMNS,
        "qt_selections": SELECTION_COLUMNS,
    }
    try:
        with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(tables))
            cur.execute(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema=%s AND table_name IN (" + placeholders + ")",
                (settings.db_name,) + tuple(tables),
            )
            found: dict[str, set[str]] = {}
            for table, column in cur.fetchall():
                found.setdefault(table, set()).add(column)
            for table, expected in tables.items():
                assert table in found, f"缺表：{table}"
                assert found[table] == expected, f"{table} 列不一致"
            # qed_llm_calls 增量自愈：REQ-060 扩展列必在
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema=%s AND table_name='qed_llm_calls'",
                (settings.db_name,),
            )
            llm_cols = {row[0] for row in cur.fetchall()}
            assert {"task", "step", "review_status", "review_note"} <= llm_cols
    finally:
        conn.close()
