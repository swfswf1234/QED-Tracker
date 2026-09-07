"""数据访问与登记服务（qed 库，qt_*/qed_* 表）——所有数据库操作集中于此。

- engine：连接管理（Engine + session_factory + dispose + utc_now）
- schema：ensure_schema 快照自愈（模型即 schema，无 Alembic，ADR 0006）
- models：ORM 模型（单一事实源）
- knowledge_repository：qt_knowledge/qt_books/qt_sources + qed_* 读写
- selection_repository：qt_selections 论文选择报告
- tasks_repository：qt_tasks 读写层
"""

from __future__ import annotations

from qed_tracker.db.engine import dispose, session_factory, utc_now
from qed_tracker.db.schema import ensure_schema

__all__ = ["dispose", "ensure_schema", "session_factory", "utc_now"]
