"""Create qt_explore_runs exploration runs table (QED-040/041, ARCH-019).

One row = one course-level or curriculum-level exploration run (single-table
JSON design accepted in docs/plans/2026-08-exploration-db-design.md):
scope=course keeps course_id, scope=curriculum keeps domain_name; proposals /
adopted_ids / conflicts / error / meta are JSON columns.

Chinese comments live in migrations/data/table_comments.json; this file stays
ASCII-only (Alembic reads migration modules with locale encoding on Windows/GBK).
"""

from __future__ import annotations

import json
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0008_exploration_runs"
down_revision = "0007_table_comments"
branch_labels = None
depends_on = None

_TABLE = "qt_explore_runs"


def _load_comments() -> dict:
    path = Path(__file__).resolve().parent.parent / "data" / "table_comments.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _apply_table_comment() -> None:
    comments = _load_comments().get(_TABLE)
    if not comments:
        return
    conn = op.get_bind()
    op.execute(f"ALTER TABLE `{_TABLE}` COMMENT = '{comments['table'].replace(chr(39), chr(39) * 2)}'")
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
    for col, comment in comments["columns"].items():
        if col not in columns:
            raise RuntimeError(f"column {_TABLE}.{col} not found")
        col_type, nullable = columns[col]
        null_sql = "NULL" if nullable == "YES" else "NOT NULL"
        default = ""
        if col == "adopted_ids":
            default = "DEFAULT ('[]')"
        elif col in ("created_by",):
            default = "DEFAULT ''"
        op.execute(
            f"ALTER TABLE `{_TABLE}` MODIFY COLUMN `{col}` {col_type} {null_sql} {default} "
            f"COMMENT '{comment.replace(chr(39), chr(39) * 2)}'"
        )


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("course_id", sa.String(length=64), nullable=True),
        sa.Column("domain_name", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="running"),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("proposals", sa.JSON(), nullable=True),
        sa.Column("adopted_ids", sa.JSON(), nullable=False),
        sa.Column("conflicts", sa.JSON(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("task_id", sa.String(length=32), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("run_id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_qt_explore_runs_course", _TABLE, ["course_id"])
    op.create_index("ix_qt_explore_runs_domain", _TABLE, ["domain_name"])
    op.create_index("ix_qt_explore_runs_status", _TABLE, ["status"])
    _apply_table_comment()


def downgrade() -> None:
    op.drop_index("ix_qt_explore_runs_status", table_name=_TABLE)
    op.drop_index("ix_qt_explore_runs_domain", table_name=_TABLE)
    op.drop_index("ix_qt_explore_runs_course", table_name=_TABLE)
    op.drop_table(_TABLE)
