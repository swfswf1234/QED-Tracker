"""Drop qt_explore_runs and qt_prompt_runs (shared table consolidation).

2026-08-27 共享表重构：探索状态追踪已移至 qed_domain/qed_course.exploration_stage；
LLM 调用审计保留共享表 qed_llm_calls。两个 runs 表的 ORM 模型与仓储已删除。

Chinese comments live in migrations/data/table_comments.json; this file stays
ASCII-only (Alembic reads migration modules with locale encoding on Windows/GBK).
"""

from __future__ import annotations

from alembic import op

revision = "0013_drop_runs_tables"
down_revision = "0012_course_explore_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("qt_explore_runs")
    op.drop_table("qt_prompt_runs")


def downgrade() -> None:
    raise RuntimeError("Downgrade not supported: qt_explore_runs / qt_prompt_runs permanently removed")
