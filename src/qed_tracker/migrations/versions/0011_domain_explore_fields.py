"""Add exploration fields to qed_domain (level/scope/exploration_stage/classic_tracks/path_results).

2026-08-27 QED-043 表重构：领域探索管线产出（level/classic_tracks/path_results）落入 qed_domain
表，使领域数据以表为准。stages 去掉 Python default（无默认值，后续可变更）。

Chinese comments live in migrations/data/table_comments.json; this file stays
ASCII-only (Alembic reads migration modules with locale encoding on Windows/GBK).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_domain_explore_fields"
down_revision = "0010_prompt_runs"
branch_labels = None
depends_on = None

_TABLE = "qed_domain"


def upgrade() -> None:
    # 新增 5 列。TEXT/JSON 列在 MySQL 不允许字面 DEFAULT（error 1101）：
    # 先加可空列、回填、再收紧 NOT NULL；ORM 侧由 Python default 兜底。
    op.add_column(_TABLE, sa.Column("level", sa.String(50), nullable=False, server_default=""))
    op.add_column(_TABLE, sa.Column("scope", sa.Text(), nullable=True))
    op.execute(f"UPDATE `{_TABLE}` SET `scope` = '' WHERE `scope` IS NULL")
    op.alter_column(_TABLE, "scope", existing_type=sa.Text(), nullable=False)
    op.add_column(_TABLE, sa.Column("exploration_stage", sa.String(20), nullable=False, server_default="未开始"))
    op.add_column(_TABLE, sa.Column("classic_tracks", sa.JSON(), nullable=True))
    op.execute(f"UPDATE `{_TABLE}` SET `classic_tracks` = '[]' WHERE `classic_tracks` IS NULL")
    op.alter_column(_TABLE, "classic_tracks", existing_type=sa.JSON(), nullable=False)
    op.add_column(_TABLE, sa.Column("path_results", sa.JSON(), nullable=True))
    # description 扩容：VARCHAR(100) -> TEXT（管线输出允许 200 字符；TEXT 不带字面 DEFAULT）
    op.alter_column(_TABLE, "description", existing_type=sa.String(length=100), type_=sa.Text(), nullable=False)
    # stages 去掉 Python default（ORM 侧已去掉 default=list；MySQL 侧无需改动，存量行不受影响）


def downgrade() -> None:
    op.drop_column(_TABLE, "path_results")
    op.drop_column(_TABLE, "classic_tracks")
    op.drop_column(_TABLE, "exploration_stage")
    op.drop_column(_TABLE, "scope")
    op.drop_column(_TABLE, "level")
    # description 恢复 VARCHAR(100)——不自动恢复，避免数据截断
