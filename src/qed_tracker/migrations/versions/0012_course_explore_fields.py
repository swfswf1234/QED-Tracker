"""Add exploration fields and rename note to description on qed_course.

2026-08-27 共享表重构：课程探索管线产出（track/exploration_stage）落入 qed_course 表；
note 重命名为 description 与 qed_domain 同步。

Chinese comments live in migrations/data/table_comments.json; this file stays
ASCII-only (Alembic reads migration modules with locale encoding on Windows/GBK).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_course_explore_fields"
down_revision = "0011_domain_explore_fields"
branch_labels = None
depends_on = None

_TABLE = "qed_course"


def upgrade() -> None:
    # RENAME note -> description（MySQL 不支持 RENAME COLUMN，用 ADD + COPY + DROP）
    op.add_column(_TABLE, sa.Column("description", sa.String(1000), nullable=False, server_default=""))
    op.execute(f"UPDATE `{_TABLE}` SET `description` = `note`")
    op.drop_column(_TABLE, "note")
    # 新增 2 列
    op.add_column(_TABLE, sa.Column("track", sa.String(50), nullable=False, server_default=""))
    op.add_column(_TABLE, sa.Column("exploration_stage", sa.String(20), nullable=False, server_default="未开始"))


def downgrade() -> None:
    op.drop_column(_TABLE, "exploration_stage")
    op.drop_column(_TABLE, "track")
    # 恢复 note 列（description 数据不自动恢复）
    op.add_column(_TABLE, sa.Column("note", sa.String(1000), nullable=False, server_default=""))
    op.drop_column(_TABLE, "description")
