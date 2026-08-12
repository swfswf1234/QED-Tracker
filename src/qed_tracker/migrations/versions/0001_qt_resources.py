"""Initial qt_resources table (QED-012).

Columns follow docs/design/tracker-service.md "MySQL 资源登记索引":
resource_id (sha256:<digest> filled after download; cand_<md5> while candidate) / sha256 /
kind / title / authors(JSON) / language / year / edition / source(JSON) / retrieved_at /
relative_path / page_count / status / llm_evaluation(JSON) / catalog_ref(JSON) /
confirmed_at / downloaded_at / approved_at / rejected_at / reject_reason / rejected_by /
created_at.

NOTE: keep this file ASCII-only (Alembic reads migration modules with locale encoding).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_qt_resources"
down_revision = None
branch_labels = None
depends_on = None


def _columns() -> list[sa.Column]:
    datetime_type = sa.DateTime()
    json_type = sa.JSON()
    return [
        sa.Column("resource_id", sa.String(100), primary_key=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("authors", json_type, nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("year", sa.String(16), nullable=False),
        sa.Column("edition", sa.String(64), nullable=False),
        sa.Column("source", json_type, nullable=False),
        sa.Column("retrieved_at", datetime_type, nullable=True),
        sa.Column("relative_path", sa.String(500), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("llm_evaluation", json_type, nullable=True),
        sa.Column("catalog_ref", json_type, nullable=True),
        sa.Column("confirmed_at", datetime_type, nullable=True),
        sa.Column("downloaded_at", datetime_type, nullable=True),
        sa.Column("approved_at", datetime_type, nullable=True),
        sa.Column("rejected_at", datetime_type, nullable=True),
        sa.Column("reject_reason", sa.String(1000), nullable=False),
        sa.Column("rejected_by", sa.String(16), nullable=False),
        sa.Column("created_at", datetime_type, nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "qt_resources",
        *_columns(),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("uq_qt_resources_sha256", "qt_resources", ["sha256"], unique=True)
    op.create_index("ix_qt_resources_status", "qt_resources", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_qt_resources_status", table_name="qt_resources")
    op.drop_index("uq_qt_resources_sha256", table_name="qt_resources")
    op.drop_table("qt_resources")
