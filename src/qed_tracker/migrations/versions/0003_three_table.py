"""Create three-table model: qt_selections / qt_downloads / qt_sources (QED-028).

Unify the dual-track storage (qt_resources state machine + main-line JSON) into
three normalized tables: selection (one row = one book set) -> downloads
(volume-level rows) -> sources (channel attempts). qt_resources stays as a
read-only legacy table; this migration only creates the three new tables.

DDL fact source: docs/design/three-table-schema.md (this repo) and
docs/design/downloads-three-table-model.md (root repo, model view).

NOTE: keep this file ASCII-only (Alembic reads migration modules with locale encoding).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_three_table"
down_revision = "0002_review_note"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qt_selections",
        sa.Column("selection_id", sa.String(100), primary_key=True),
        sa.Column("course_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("authors", sa.JSON(), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("version", sa.JSON(), nullable=False),
        sa.Column("vols", sa.JSON(), nullable=False),
        sa.Column("set_no", sa.String(4), nullable=False, server_default=""),
        sa.Column("evaluation", sa.JSON(), nullable=True),
        sa.Column("note", sa.String(1000), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="candidate"),
        sa.Column("reject_reason", sa.String(1000), nullable=False, server_default=""),
        sa.Column("rejected_by", sa.String(16), nullable=False, server_default=""),
        sa.Column("supersede_reason", sa.String(1000), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("superseded_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_qt_selections_course", "qt_selections", ["course_id"])
    op.create_index("ix_qt_selections_status", "qt_selections", ["status"])

    op.create_table(
        "qt_downloads",
        sa.Column("download_id", sa.String(100), primary_key=True),
        sa.Column("selection_id", sa.String(100), nullable=False),
        sa.Column("vol", sa.String(32), nullable=False, server_default=""),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("file_hint", sa.String(200), nullable=False, server_default=""),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("relative_path", sa.String(500), nullable=False, server_default=""),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="candidate"),
        sa.Column("reject_reason", sa.String(1000), nullable=False, server_default=""),
        sa.Column("rejected_by", sa.String(16), nullable=False, server_default=""),
        sa.Column("review_note", sa.String(1000), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("sha256", name="uq_qt_downloads_sha256"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_qt_downloads_selection", "qt_downloads", ["selection_id"])
    op.create_index("ix_qt_downloads_status", "qt_downloads", ["status"])

    op.create_table(
        "qt_sources",
        sa.Column("source_id", sa.String(100), primary_key=True),
        sa.Column("download_id", sa.String(100), nullable=False),
        sa.Column("channel", sa.String(24), nullable=False),
        sa.Column("provider_id", sa.String(200), nullable=False, server_default=""),
        sa.Column("page_url", sa.String(1000), nullable=False, server_default=""),
        sa.Column("download_url", sa.String(1000), nullable=False, server_default=""),
        sa.Column("file_keywords", sa.String(500), nullable=False, server_default=""),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("note", sa.String(1000), nullable=False, server_default=""),
        sa.Column("attempted_at", sa.DateTime(), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_qt_sources_download", "qt_sources", ["download_id"])


def downgrade() -> None:
    op.drop_index("ix_qt_sources_download", table_name="qt_sources")
    op.drop_table("qt_sources")
    op.drop_index("ix_qt_downloads_status", table_name="qt_downloads")
    op.drop_index("ix_qt_downloads_selection", table_name="qt_downloads")
    op.drop_table("qt_downloads")
    op.drop_index("ix_qt_selections_status", table_name="qt_selections")
    op.drop_index("ix_qt_selections_course", table_name="qt_selections")
    op.drop_table("qt_selections")
