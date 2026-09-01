"""Add explore_pending JSON column to qed_domain and qed_course (REQ-067-B12).

The 6-state exploration stage machine introduces a '待确认' state that needs
a payload field to carry review results or failure reasons. explore_pending
stores this payload as JSON (nullable).

State machine (6 states):
  未开始 -> 已生成 -> 探索中 -> 待确认 -> 已完成
                            \--> 失败

explore_pending payloads:
  待确认 = {kind: "review_results", courses/tutorials: [...], ...}
  失败   = {kind: "failed", error: "..."}
  其余   = NULL
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_add_explore_pending"
down_revision = "0014_rebuild_qt_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("qed_domain", sa.Column("explore_pending", sa.JSON, nullable=True))
    op.add_column("qed_course", sa.Column("explore_pending", sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("qed_course", "explore_pending")
    op.drop_column("qed_domain", "explore_pending")
