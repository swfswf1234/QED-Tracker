"""Create qt_prompt_runs prompt-lab exploration runs table (QED-043).

One row = one domain/course knowledge exploration run (prompt optimization
module). Call-level auditing (template id / question / answer) lives in the
shared qed_llm_calls table; this table holds params snapshot, state machine,
aggregated report and review status.

Chinese comments live in migrations/data/table_comments.json; this file stays
ASCII-only (Alembic reads migration modules with locale encoding on Windows/GBK).
"""

from __future__ import annotations

import json
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0010_prompt_runs"
down_revision = "0009_add_explore_runs_skipped"
branch_labels = None
depends_on = None

_TABLE = "qt_prompt_runs"


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
        if col == "calls_review":
            default = "DEFAULT ('[]')"
        elif col == "scope_hint":
            default = "DEFAULT ''"
        elif col == "review_status":
            default = "DEFAULT 'unreviewed'"
        op.execute(
            f"ALTER TABLE `{_TABLE}` MODIFY COLUMN `{col}` {col_type} {null_sql} {default} "
            f"COMMENT '{comment.replace(chr(39), chr(39) * 2)}'"
        )


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("task", sa.String(length=16), nullable=False),
        sa.Column("subject", sa.String(length=100), nullable=False),
        sa.Column("scope_hint", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="running"),
        sa.Column("report", sa.JSON(), nullable=True),
        sa.Column("review_status", sa.String(length=16), nullable=False),
        sa.Column("calls_review", sa.JSON(), nullable=False),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("task_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("run_id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_qt_prompt_runs_task", _TABLE, ["task"])
    op.create_index("ix_qt_prompt_runs_status", _TABLE, ["status"])
    op.create_index("ix_qt_prompt_runs_subject", _TABLE, ["subject"])
    _apply_table_comment()


def downgrade() -> None:
    op.drop_index("ix_qt_prompt_runs_subject", table_name=_TABLE)
    op.drop_index("ix_qt_prompt_runs_status", table_name=_TABLE)
    op.drop_index("ix_qt_prompt_runs_task", table_name=_TABLE)
    op.drop_table(_TABLE)
