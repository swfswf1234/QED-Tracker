"""Create qt_tasks table for background task persistence (REQ-032).

Replaces meta/tasks/ JSON files with a proper database table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_qt_tasks"
down_revision = "0015_add_explore_pending"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qt_tasks",
        sa.Column("task_id", sa.String(100), primary_key=True, comment="任务标识（主键）"),
        sa.Column("type", sa.String(50), nullable=False, comment="任务类型"),
        sa.Column("status", sa.String(24), nullable=False, comment="状态（queued/running/succeeded/failed）"),
        sa.Column("params", sa.JSON, nullable=False, comment="任务参数"),
        sa.Column("progress", sa.Integer, nullable=False, server_default="0", comment="进度（0-100）"),
        sa.Column("message", sa.Text, nullable=False, server_default="", comment="当前状态消息"),
        sa.Column("result", sa.JSON, nullable=True, comment="成功结果"),
        sa.Column("error", sa.Text, nullable=False, server_default="", comment="失败错误信息"),
        sa.Column("created_at", sa.DateTime, nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime, nullable=False, comment="最后更新时间"),
        sa.Index("ix_qt_tasks_status", "status"),
        sa.Index("ix_qt_tasks_type", "type"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )


def downgrade() -> None:
    op.drop_table("qt_tasks")
