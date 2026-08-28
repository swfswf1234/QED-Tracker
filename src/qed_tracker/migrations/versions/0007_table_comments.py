"""Add Chinese table/column comments to the five-layer schema (QED-031).

Adds TABLE_COMMENT / COLUMN_COMMENT to qed_domain / qed_course /
qt_knowledge / qt_books / qt_sources and the qt_sources_legacy backup table.

Comments (Chinese) live in migrations/data/table_comments.json (UTF-8).
This file stays ASCII-only (Alembic reads migration modules with locale
encoding on Windows/GBK).

Column MODIFY statements are rebuilt from information_schema so existing
types / nullability / defaults are preserved exactly.
"""

from __future__ import annotations

import json
from pathlib import Path

from alembic import op
from sqlalchemy import text

revision = "0007_table_comments"
down_revision = "0006_knowledge_schema"
branch_labels = None
depends_on = None


def _load_comments() -> dict:
    path = Path(__file__).resolve().parent.parent / "data" / "table_comments.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _columns(conn, table: str) -> dict:
    rows = conn.execute(
        text(
            "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT "
            "FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
        ),
        {"t": table},
    )
    return {name: (col_type, nullable, default) for name, col_type, nullable, default in rows}


def _default_sql(value, col_type: str) -> str:
    if value is None:
        return ""
    low = col_type.lower()
    if str(value) == "0" and low.startswith(
        ("int", "tinyint", "bigint", "smallint", "float", "double", "decimal", "numeric")
    ):
        return f"DEFAULT {value}"
    if isinstance(value, str):
        return f"DEFAULT '{value.replace(chr(39), chr(39) * 2)}'"
    return f"DEFAULT {value}"


def _modify(table: str, name: str, col_type: str, nullable: str, default, comment: str) -> str:
    null_sql = "NULL" if nullable == "YES" else "NOT NULL"
    return (
        f"ALTER TABLE `{table}` MODIFY COLUMN `{name}` {col_type} {null_sql} "
        f"{_default_sql(default, col_type)} COMMENT '{comment.replace(chr(39), chr(39) * 2)}'"
    )


def _apply(apply_comments: bool) -> None:
    conn = op.get_bind()
    existing_tables = {
        row[0]
        for row in conn.execute(
            text("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()")
        )
    }
    for table, meta in _load_comments().items():
        if table not in existing_tables:
            # Optional tables (e.g. the qt_sources_legacy backup created only
            # when legacy data existed) may be absent on a fresh upgrade path.
            continue
        table_comment = meta["table"] if apply_comments else ""
        op.execute(
            f"ALTER TABLE `{table}` COMMENT = '{table_comment.replace(chr(39), chr(39) * 2)}'"
        )
        columns = _columns(conn, table)
        for col, comment in meta["columns"].items():
            if col not in columns:
                # Columns added by later migrations (e.g. 0011/0012 exploration
                # fields) do not exist yet on a fresh upgrade path: skip them
                # instead of failing the whole chain.
                continue
            col_type, nullable, default = columns[col]
            col_comment = comment if apply_comments else ""
            op.execute(_modify(table, col, col_type, nullable, default, col_comment))


def upgrade() -> None:
    _apply(apply_comments=True)


def downgrade() -> None:
    _apply(apply_comments=False)
