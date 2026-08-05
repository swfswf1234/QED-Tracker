"""Alembic migration environment: database URL is built from QED_DB_* env vars (never hardcoded in ini).

NOTE: this file must stay ASCII-only -- Alembic reads migration modules with the locale
encoding on Windows (gbk), and non-ASCII characters would crash module loading.
"""

from __future__ import annotations

import os
import sys

from alembic import context
from sqlalchemy import create_engine, pool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from qed_tracker.config import load_settings  # noqa: E402
from qed_tracker.database import mysql_url  # noqa: E402
from qed_tracker.db.models import Base  # noqa: E402

config = context.config

target_metadata = Base.metadata


def _database_url() -> str:
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return configured
    return mysql_url(load_settings())


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_database_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
