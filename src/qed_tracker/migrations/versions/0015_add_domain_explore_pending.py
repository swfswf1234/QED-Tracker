"""Add explore_pending JSON column to qed_domain.

2026-08-30 REQ-067 B8: domain exploration state machine (explore/confirm-name)
writes pending name-confirmation or failure diagnostics here; read by GET
/domains and /courses for the frontend name-confirm / failure UX.

Chinese comments live in migrations/data/table_comments.json; this file stays
ASCII-only (Alembic reads migration modules with locale encoding on Windows/GBK).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_add_domain_explore_pending"
down_revision = "0014_rebuild_qt_sources"
branch_labels = None
depends_on = None

_TABLE = "qed_domain"
_COLUMN = "explore_pending"


def _columns(bind: sa.engine.Connection, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if _COLUMN not in _columns(bind, _TABLE):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column(_TABLE, _COLUMN)
