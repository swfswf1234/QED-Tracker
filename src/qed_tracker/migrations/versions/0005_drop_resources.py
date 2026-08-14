"""Drop qt_resources legacy table (QED-030).

qt_resources (single-table query index + state machine) has been fully retired:
the three-table model (qt_selections / qt_downloads / qt_sources) is now the
only source of truth for acquisition state. All data was migrated in 0003 and
the 12-volume inventory lives in the three tables; the legacy table holds only
duplicated/derived rows and is dropped with evidence archived under
docs/history/qed-030-retire-qt_resources/.

NOTE: keep this file ASCII-only (Alembic reads migration modules with locale encoding).
"""

from __future__ import annotations

from alembic import op

revision = "0005_drop_resources"
down_revision = "0004_download_intro"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("qt_resources")


def downgrade() -> None:
    # QED-030：qt_resources 退役不可逆（数据已迁移三表，备份证据见 docs/history/ 归档）。
    raise NotImplementedError("qt_resources 已退役（QED-030），不支持回退")