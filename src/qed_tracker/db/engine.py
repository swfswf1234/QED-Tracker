"""Database engine / session lifecycle (qed db, qt_*/qed_* tables).

Single point of ownership for building the SQLAlchemy Engine (with a tuned
MySQL QueuePool), the session factory, the naive-UTC clock and disposal.

Moved from ``src/qed_tracker/database.py`` (retired in the v0.1 schema rework,
ADR 0006): the model is now the schema source of truth, so no Alembic and no
long-lived global engine elsewhere. Callers build the engine here and dispose it
when done (service shutdown / CLI run teardown).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from qed_tracker.config import Settings

# MySQL QueuePool tuning: pre-ping guards stale connections, recycle bounds the
# server-side wait timeout, and a small pool avoids exhausting MySQL connections.
_POOL_PRE_PING = True
_POOL_RECYCLE = 3600
_POOL_SIZE = 5
_POOL_MAX_OVERFLOW = 10


def mysql_url(settings: Settings) -> str:
    """Build the pymysql URL from QED_DB_* settings."""
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
    """Build the MySQL engine with a tuned QueuePool."""
    return create_engine(
        mysql_url(settings),
        pool_pre_ping=_POOL_PRE_PING,
        pool_recycle=_POOL_RECYCLE,
        pool_size=_POOL_SIZE,
        max_overflow=_POOL_MAX_OVERFLOW,
        future=True,
    )


def session_factory(engine: Engine) -> Callable[[], Session]:
    """Return a factory producing short-lived sessions (expire_on_commit=False)."""
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return lambda: factory()


def utc_now() -> datetime:
    """MySQL DATETIME has no timezone: store naive UTC (same as Axiom-Flow)."""
    return datetime.now(UTC).replace(tzinfo=None)


def dispose(engine: Engine | None) -> None:
    """Dispose the engine's connection pool (idempotent; None is a no-op)."""
    if engine is not None:
        engine.dispose()
