"""Create qt_selections table for paper selection reports (REQ-032).

Replaces meta/selections/ JSON files with a proper database table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_qt_selections"
down_revision = "0016_qt_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qt_selections",
        sa.Column("selection_id", sa.String(100), primary_key=True, comment="选择报告标识（主键）"),
        sa.Column("schema_version", sa.Integer, nullable=False, comment="Schema 版本号"),
        sa.Column("status", sa.String(24), nullable=False, comment="状态（planning/no_candidates/completed/...）"),
        sa.Column("created_at", sa.String(50), nullable=False, comment="创建时间（ISO 格式）"),
        sa.Column("profile", sa.JSON, nullable=True, comment="论文档案"),
        sa.Column("temporary_goal", sa.Text, nullable=False, server_default="", comment="临时研究目标"),
        sa.Column("allowed_categories", sa.JSON, nullable=True, comment="允许的 arXiv 分类"),
        sa.Column("search_plan", sa.JSON, nullable=True, comment="搜索计划"),
        sa.Column("search_failures", sa.JSON, nullable=True, comment="搜索失败记录"),
        sa.Column("excluded_existing", sa.JSON, nullable=True, comment="已排除的已有 arXiv ID"),
        sa.Column("candidates", sa.JSON, nullable=True, comment="候选论文列表"),
        sa.Column("assessments", sa.JSON, nullable=True, comment="评估结果"),
        sa.Column("recommendations", sa.JSON, nullable=True, comment="推荐列表"),
        sa.Column("model", sa.JSON, nullable=True, comment="模型元数据"),
        sa.Column("downloads", sa.JSON, nullable=True, comment="下载记录"),
        sa.Index("ix_qt_selections_status", "status"),
        sa.Index("ix_qt_selections_created_at", "created_at"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )


def downgrade() -> None:
    op.drop_table("qt_selections")
