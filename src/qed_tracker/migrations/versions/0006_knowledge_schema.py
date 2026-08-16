"""Create five-layer knowledge schema tables (QED-031).

Creates qed_domain / qed_course (shared, qed_* prefix) and qt_knowledge /
qt_books (private). qt_sources is NOT touched here -- it is rebuilt (FK
switched to qt_books.book_id) by the idempotent data migration script
(src/qed_tracker/application/migrate_knowledge.py) after this migration,
which first renames the old table and copies rows with the new mapping.

DDL fact source: docs/design/database-schema.md (single source of truth).

NOTE: keep this file ASCII-only (Alembic reads migration modules with locale encoding).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_knowledge_schema"
down_revision = "0005_drop_resources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qed_domain",
        sa.Column("domain_id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("stages", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(16), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(16), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    op.create_table(
        "qed_course",
        sa.Column("course_id", sa.String(64), primary_key=True),
        sa.Column("domain_id", sa.String(32), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("prerequisites", sa.JSON(), nullable=False),
        sa.Column("related_targets", sa.JSON(), nullable=False),
        sa.Column("note", sa.String(1000), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(16), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(16), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_qed_course_domain", "qed_course", ["domain_id"])

    op.create_table(
        "qt_knowledge",
        sa.Column("knowledge_id", sa.String(100), primary_key=True),
        sa.Column("domain_id", sa.String(32), nullable=False),
        sa.Column("course_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("set_no", sa.String(4), nullable=False, server_default=""),
        sa.Column("name", sa.String(200), nullable=False, server_default=""),
        sa.Column("textbook_ref", sa.JSON(), nullable=True),
        sa.Column("exercise_ref", sa.JSON(), nullable=True),
        sa.Column("textbook_intro", sa.Text(), nullable=False),
        sa.Column("exercise_intro", sa.Text(), nullable=False),
        sa.Column("materials_intro", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("reject_reason", sa.String(1000), nullable=False, server_default=""),
        sa.Column("supersede_reason", sa.String(1000), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(16), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(16), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.Column("superseded_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_qt_knowledge_course", "qt_knowledge", ["course_id"])
    op.create_index("ix_qt_knowledge_status", "qt_knowledge", ["status"])

    op.create_table(
        "qt_books",
        sa.Column("book_id", sa.String(100), primary_key=True),
        sa.Column("knowledge_id", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("part", sa.String(32), nullable=False, server_default=""),
        sa.Column("display_title", sa.String(500), nullable=False),
        sa.Column("file_name", sa.String(500), nullable=False, server_default=""),
        sa.Column("authors", sa.JSON(), nullable=False),
        sa.Column("language", sa.String(8), nullable=False, server_default=""),
        sa.Column("version", sa.JSON(), nullable=False),
        sa.Column("source", sa.JSON(), nullable=True),
        sa.Column("original_url", sa.String(1000), nullable=False, server_default=""),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("relative_path", sa.String(500), nullable=False, server_default=""),
        sa.Column("absolute_path", sa.String(1000), nullable=False, server_default=""),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="candidate"),
        sa.Column("reject_reason", sa.String(1000), nullable=False, server_default=""),
        sa.Column("rejected_by", sa.String(16), nullable=False, server_default=""),
        sa.Column("supersede_reason", sa.String(1000), nullable=False, server_default=""),
        sa.Column("review_note", sa.String(1000), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(16), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(16), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("downloaded_at", sa.DateTime(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.Column("superseded_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("knowledge_id", "title", "part", name="uq_qt_books_knowledge_title_part"),
        sa.UniqueConstraint("sha256", name="uq_qt_books_sha256"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_qt_books_knowledge", "qt_books", ["knowledge_id"])
    op.create_index("ix_qt_books_status", "qt_books", ["status"])


def downgrade() -> None:
    op.drop_index("ix_qt_books_status", table_name="qt_books")
    op.drop_index("ix_qt_books_knowledge", table_name="qt_books")
    op.drop_table("qt_books")
    op.drop_index("ix_qt_knowledge_status", table_name="qt_knowledge")
    op.drop_index("ix_qt_knowledge_course", table_name="qt_knowledge")
    op.drop_table("qt_knowledge")
    op.drop_index("ix_qed_course_domain", table_name="qed_course")
    op.drop_table("qed_course")
    op.drop_table("qed_domain")