"""Rebuild qt_sources with book_id foreign key (schema drift fix).

Migration 0006 deliberately skipped qt_sources: the rebuild (FK switched from
qt_downloads.download_id to qt_books.book_id) was delegated to the one-off
legacy data migration script (application/migrate_knowledge.py). Databases
rebuilt via alembic alone (wipe + upgrade head) never ran that script, leaving
the old three-table shape (download_id) behind while the ORM expects book_id.
Every repo.add_source / list_sources call then fails with
"Unknown column 'qt_sources.book_id'" (observed 2026-08-28 on the live MySQL).

This migration makes the alembic path self-sufficient:

1. If qt_sources exists in the OLD shape (download_id column):
   - rename to qt_sources_legacy when that archive table is absent,
   - otherwise drop it (data already archived by the legacy script).
   No row copying happens here: download_id -> book_id mapping requires the
   qt_selections / qt_downloads context and stays the job of
   migrate_knowledge.py on real legacy databases (it is idempotent and skips
   this migration's rename because the table no longer has download_id).
2. Create the new qt_sources from the ORM model DDL (single source of truth
   with db/models.py, same approach as _ensure_qt_sources).

Keep this file ASCII-only (Alembic reads migration modules with locale
encoding on Windows/GBK); Chinese comments live in
migrations/data/table_comments.json.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from qed_tracker.db.models import QtSource

revision = "0014_rebuild_qt_sources"
down_revision = "0013_drop_runs_tables"
branch_labels = None
depends_on = None


def _columns(bind: sa.engine.Connection, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def _exists(bind: sa.engine.Connection, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()
    if _exists(bind, "qt_sources") and "download_id" in _columns(bind, "qt_sources"):
        if _exists(bind, "qt_sources_legacy"):
            # Archive already exists (legacy script ran before): old table is redundant.
            op.drop_table("qt_sources")
        else:
            op.rename_table("qt_sources", "qt_sources_legacy")
    if not _exists(bind, "qt_sources") or "book_id" not in _columns(bind, "qt_sources"):
        QtSource.__table__.create(bind, checkfirst=True)


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade not supported: qt_sources shape history is preserved in "
        "qt_sources_legacy; recreate the old shape via migrate_knowledge.py instead"
    )
