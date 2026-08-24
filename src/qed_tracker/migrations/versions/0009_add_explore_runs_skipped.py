"""Add skipped JSON column to qt_explore_runs (REQ-059 re-exploration).

skipped records domain-level changes that were skipped because the domain
already existed (parallel to conflicts which records actual conflicts).

Chinese comments live in migrations/data/table_comments.json; this file stays
ASCII-only (Alembic reads migration modules with locale encoding on Windows/GBK).
"""

from __future__ import annotations

import json
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0009_add_explore_runs_skipped"
down_revision = "0008_exploration_runs"
branch_labels = None
depends_on = None

_TABLE = "qt_explore_runs"


def _load_comments() -> dict:
    path = Path(__file__).resolve().parent.parent / "data" / "table_comments.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _apply_column_comment() -> None:
    comments = _load_comments().get(_TABLE, {}).get("columns", {})
    comment = comments.get("skipped")
    if not comment:
        return
    conn = op.get_bind()
    columns = {
        name: (col_type, nullable)
        for name, col_type, nullable in conn.execute(
            text(
                "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
            ),
            {"t": _TABLE},
        )
    }
    if "skipped" not in columns:
        raise RuntimeError(f"column {_TABLE}.skipped not found after add_column")
    col_type, nullable = columns["skipped"]
    null_sql = "NULL" if nullable == "YES" else "NOT NULL"
    op.execute(
        f"ALTER TABLE `{_TABLE}` MODIFY COLUMN `skipped` {col_type} {null_sql} "
        f"COMMENT '{comment.replace(chr(39), chr(39) * 2)}'"
    )


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("skipped", sa.JSON(), nullable=True))
    _apply_column_comment()


def downgrade() -> None:
    op.drop_column(_TABLE, "skipped")
