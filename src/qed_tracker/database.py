"""数据库连接与迁移入口（qed 库，qt_* 三表：selections/downloads/sources，QED-028）。

根 `.env` 的 `QED_DB_*` 由统一 CLI `qed` 注入环境；独立启动无凭据时能力降级，
engine 构造失败由调用方（ThreeTableRepository 工厂）捕获并回退为降级模式。
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from qed_tracker.config import Settings


def mysql_url(settings: Settings) -> str:
    return URL.create(
        "mysql+pymysql",
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        username=settings.db_user,
        password=settings.db_password,
        query={"charset": "utf8mb4"},
    ).render_as_string(hide_password=False)


def create_engine_for(settings: Settings) -> Engine:
    return create_engine(mysql_url(settings), pool_pre_ping=True, future=True)


def utc_now() -> datetime:
    """MySQL DATETIME 无时区：统一存 naive UTC，与 Axiom-Flow 模式一致。"""
    return datetime.now(UTC).replace(tzinfo=None)


def session_factory(engine: Engine) -> Callable[[], Session]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return lambda: factory()


def upgrade_database(settings: Settings) -> None:
    """编程式执行 Alembic 迁移到 head（供服务启动与冒烟复用）。"""
    from alembic import command
    from alembic.config import Config

    config = Config(os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini"))
    config.set_main_option("sqlalchemy.url", mysql_url(settings).replace("%", "%%"))
    command.upgrade(config, "head")
