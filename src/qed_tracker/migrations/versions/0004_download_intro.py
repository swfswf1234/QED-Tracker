"""Add intro column to qt_downloads (three-table regroup, 2026-08-13).

Tutorial-level selections group multiple volumes; each volume (download) may
carry a short intro (LLM-generated or manual) shown in the volume card.

NOTE: keep this file ASCII-only (Alembic reads migration modules with locale encoding).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_download_intro"
down_revision = "0003_three_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("qt_downloads", sa.Column("intro", sa.String(1000), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("qt_downloads", "intro")
