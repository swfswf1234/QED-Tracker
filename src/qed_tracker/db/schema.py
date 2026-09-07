"""Ensure the database schema matches the ORM models (snapshot self-healing).

v0.1 strategy (ADR 0006): the ORM models are the single source of truth. On
startup we reconcile the schema instead of replaying an Alembic migration chain:

- Every table declared in :data:`qed_tracker.db.models.Base.metadata` that is
  missing is created; one whose column set / primary key drifted is DROP+CREATE'd.
- We only touch tables declared in ``Base.metadata`` plus ``qed_llm_calls``.
- ``qed_llm_calls`` is the shared audit table owned by the root repo: we create
  it if missing and ADD missing late columns (never DROP) so audit history is
  preserved. This mirrors the root repo's own additive self-heal.

This file is ASCII-only by convention (kept simple and portable).
"""

from __future__ import annotations

import logging
from typing import Protocol

import sqlalchemy as sa
from sqlalchemy import Column, MetaData, Table, Text
from sqlalchemy.engine import Connection, Engine, Inspector
from sqlalchemy.sql import text

from qed_tracker.db.models import Base

logger = logging.getLogger("qed_tracker.schema")

# ---------------------------------------------------------------------------
# qed_llm_calls (shared audit, owned by the root repo)
# ---------------------------------------------------------------------------
# Mirrors backend/qed_engine/services/llm/call_log.py CREATE_TABLE_SQL. We only
# add missing LATE columns (REQ-060) to an existing table, never drop/dodge it.
_QED_LLM_CALLS = "qed_llm_calls"

# Late columns added by REQ-060 to an existing table (root repo's
# _REQUIRED_COLUMNS); these are the columns we reconcile additively.
_QED_LLM_LATE_COLUMNS: dict[str, str] = {
    "task": "VARCHAR(64)",
    "step": "VARCHAR(32)",
    "review_status": "VARCHAR(16) DEFAULT 'unreviewed'",
    "review_note": "VARCHAR(1000) DEFAULT ''",
}


def _qed_llm_calls_table() -> Table:
    """Build a portable Table for creating qed_llm_calls when missing."""
    meta = MetaData()
    return Table(
        _QED_LLM_CALLS,
        meta,
        Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        Column("service", sa.String(32), nullable=False),
        Column("mode", sa.String(16), nullable=False),
        Column("provider", sa.String(32), nullable=False),
        Column("model", sa.String(64), nullable=False),
        Column("endpoint", sa.String(16), nullable=False),
        Column("prompt_template", sa.String(255)),
        Column("prompt", Text()),
        Column("response", Text()),
        Column("duration_ms", sa.Integer()),
        Column("status", sa.String(16), nullable=False),
        Column("error", sa.String(500)),
        Column("created_at", sa.DateTime(), nullable=False),
        Column("task", sa.String(64)),
        Column("step", sa.String(32)),
        Column("review_status", sa.String(16), server_default="unreviewed"),
        Column("review_note", sa.String(1000), server_default=""),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        comment=(
            "LLM call audit: one row per LLM call (success or failure), "
            "full prompt, model response, duration and review state "
            "(shared across projects, distinguished by service)"
        ),
    )


# ---------------------------------------------------------------------------
# Structure comparison
# ---------------------------------------------------------------------------
def _table_drifted(inspector: Inspector, table: Table) -> bool:
    """Return True when the on-disk table no longer matches the model.

    We compare the column-name set and the primary key. Type/nullable/index
    drift is intentionally ignored for now (conservative, avoids destroying
    data on benign dialect differences); the primary driver is added/removed
    columns, which is what the v0.1 rebuild needs to catch.
    """
    on_disk = {c["name"] for c in inspector.get_columns(table.name)}
    modeled = {c.name for c in table.columns}
    if on_disk != modeled:
        return True
    model_pk = {c.name for c in table.primary_key.columns} if table.primary_key else set()
    disk_pk = set(inspector.get_pk_constraint(table.name).get("constrained_columns") or [])
    # SQLite reflects an implicit rowid pk as empty for single-col integer pk;
    # treat "same single col" as matching to avoid false rebuilds.
    if modeled and disk_pk == set() and model_pk and len(model_pk) == 1:
        return False
    return model_pk != disk_pk


def _drop_tables(connection: Connection, tables: list[Table]) -> None:
    """DROP the given tables, suspending FK checks on MySQL."""
    is_mysql = connection.dialect.name == "mysql"
    if is_mysql:
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
    try:
        for table in tables:
            table.drop(connection)
    finally:
        if is_mysql:
            connection.execute(text("SET FOREIGN_KEY_CHECKS = 1"))


def _ensure_qed_llm_calls(connection: Connection) -> None:
    inspector = sa.inspect(connection)
    existing = set(inspector.get_table_names())
    if _QED_LLM_CALLS not in existing:
        _qed_llm_calls_table().create(connection, checkfirst=True)
        return
    on_disk = {c["name"] for c in inspector.get_columns(_QED_LLM_CALLS)}
    for name, ddl in _QED_LLM_LATE_COLUMNS.items():
        if name not in on_disk:
            connection.execute(text(f"ALTER TABLE {_QED_LLM_CALLS} ADD COLUMN {name} {ddl}"))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
class _Log(Protocol):
    def info(self, msg: str, *args: object) -> None: ...

    def warning(self, msg: str, *args: object) -> None: ...


def ensure_schema(engine: Engine | Connection, *, log: _Log | None = None) -> tuple[int, int]:
    """Reconcile the schema to the ORM models; return (created, rebuilt) counts.

    Idempotent: safe to call on every startup. Never touches tables outside
    ``Base.metadata`` except ``qed_llm_calls`` (additive self-heal).
    """
    log = log or logger
    inspector = sa.inspect(engine)
    existing = set(inspector.get_table_names())

    to_create: list[Table] = []
    to_rebuild: list[Table] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            to_create.append(table)
        elif _table_drifted(inspector, table):
            to_rebuild.append(table)

    if to_rebuild:
        log.info("db schema rebuild: %s", ", ".join(t.name for t in to_rebuild))
    if to_create:
        log.info("db schema create: %s", ", ".join(t.name for t in to_create))

    # DROP drifted tables first (FK-safe on MySQL), then create the deltas.
    with engine.begin() as connection:
        if to_rebuild:
            _drop_tables(connection, to_rebuild)
    if to_rebuild or to_create:
        Base.metadata.create_all(engine)
    with engine.begin() as connection:
        _ensure_qed_llm_calls(connection)

    return len(to_create), len(to_rebuild)
