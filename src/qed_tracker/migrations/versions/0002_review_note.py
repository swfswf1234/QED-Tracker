"""Add review_note to qt_resources (QED-020).

Human evaluation note: confirm/backup/reject may carry an optional note
stored in review_note for later reference (e.g. Axiom-Flow review context).

NOTE: keep this file ASCII-only (Alembic reads migration modules with locale encoding).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_review_note"
down_revision = "0001_qt_resources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("qt_resources", sa.Column("review_note", sa.String(1000), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("qt_resources", "review_note")
