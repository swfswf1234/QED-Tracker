"""qt_resources 真实 MySQL 冒烟（QED-012）。

默认跳过（CI 不依赖数据库）：设置环境变量 `QED_DB_SMOKE=1` 且在根 `.env` 有 `QED_DB_*`
时于本机执行。流程：upgrade head → 核对表结构 → registry 双写一条 → 读回一致 → 清理 →
downgrade base 恢复原状（qed 库为新建库，qt_* 表可重建，不触存量数据）。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa

ROOT_ENV = Path(r"D:\coding\QED-Engine\.env")


def _read_root_env() -> dict[str, str]:
    """只读根 .env（不注入进程环境，避免污染其他测试；fixture 内注入并恢复）。"""
    values: dict[str, str] = {}
    if not ROOT_ENV.exists():
        return values
    for line in ROOT_ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


_ROOT_VARS = _read_root_env()

SMOKE_ENABLED = os.environ.get("QED_DB_SMOKE") == "1" and bool(os.environ.get("QED_DB_PASSWORD") or _ROOT_VARS.get("QED_DB_PASSWORD"))

pytestmark = pytest.mark.skipif(not SMOKE_ENABLED, reason="仅本机 MySQL 冒烟（设置 QED_DB_SMOKE=1 启用）")


@pytest.fixture(scope="module")
def repository():
    saved = {key: os.environ.get(key) for key in _ROOT_VARS}
    for key, value in _ROOT_VARS.items():
        os.environ.setdefault(key, value)
    try:
        yield _build_repository()
    finally:
        _cleanup_repository()
        for key, old in saved.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def _build_repository():
    from qed_tracker.config import load_settings
    from qed_tracker.database import create_engine_for, session_factory, upgrade_database

    settings = load_settings()
    upgrade_database(settings)
    engine = create_engine_for(settings)
    factory = session_factory(engine)

    from qed_tracker.db.repository import ResourceRepository

    _engine_for_cleanup = engine
    return ResourceRepository(factory)


def _cleanup_repository():
    """清理测试数据并回滚建表（qt_* 为新建表，无存量数据）。"""
    from qed_tracker.config import load_settings
    from qed_tracker.database import create_engine_for, mysql_url, session_factory

    settings = load_settings()
    engine = create_engine_for(settings)
    factory = session_factory(engine)
    try:
        with factory() as session:
            session.execute(sa.text("DELETE FROM qt_resources WHERE resource_id LIKE 'smoke%' OR resource_id LIKE 'sha256:%'"))
            session.commit()
    except Exception:  # noqa: BLE001 - cleanup best effort
        pass
    engine.dispose()

    from alembic import command
    from alembic.config import Config

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", mysql_url(settings).replace("%", "%%"))
    command.downgrade(config, "base")


CONTRACT_COLUMNS = {
    "resource_id", "sha256", "kind", "title", "authors", "language", "year", "edition",
    "source", "retrieved_at", "relative_path", "page_count", "status", "llm_evaluation",
    "catalog_ref", "confirmed_at", "downloaded_at", "approved_at", "rejected_at",
    "reject_reason", "rejected_by", "created_at",
}


def test_upgrade_creates_qt_resources_with_contract_columns(repository):
    import pymysql

    from qed_tracker.config import load_settings

    settings = load_settings()
    conn = pymysql.connect(host=settings.db_host, port=settings.db_port, user=settings.db_user, password=settings.db_password, database=settings.db_name)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name='qt_resources'", (settings.db_name,))
            columns = {row[0] for row in cur.fetchall()}
            cur.execute("SELECT index_name FROM information_schema.statistics WHERE table_schema=%s AND table_name='qt_resources'", (settings.db_name,))
            indexes = {row[0] for row in cur.fetchall()}
    finally:
        conn.close()
    assert CONTRACT_COLUMNS == columns
    assert {"uq_qt_resources_sha256", "ix_qt_resources_status"} <= indexes


def test_registry_double_write_round_trip(repository):
    record = {
        "resource_id": "smoke:1",
        "kind": "book",
        "title": "冒烟测试书",
        "authors": ["测试作者"],
        "language": "zh",
        "year": "2020",
        "source": {"provider": "url", "provider_id": "smoke-1", "download_url": "https://example.test/smoke.pdf"},
        "file": {"relative_path": "raw/books/inbox/冒烟测试书_12345678.pdf", "sha256": "12" * 32, "page_count": 10},
        "catalog_ref": {"catalog_id": "math-qe", "target_id": "smoke", "course_id": "99"},
    }
    from qed_tracker.db.registry import ResourceRegistry

    registry = ResourceRegistry(repository)
    registry.register_downloaded(record)
    row = repository.get("sha256:" + "12" * 32)
    assert row is not None
    assert row.status == "downloaded"
    assert row.title == "冒烟测试书"
    assert row.relative_path == "raw/books/inbox/冒烟测试书_12345678.pdf"
    assert row.page_count == 10
    assert row.catalog_ref["course_id"] == "99"
    assert row.downloaded_at is not None
    # 幂等：重复登记仍一行
    registry.register_downloaded(record)
    assert len(repository.list()) == 1


def test_state_machine_on_mysql(repository):
    row = repository.upsert_candidate(title="冒烟候选", authors=[], language="en", kind="book", source={"provider": "fake", "provider_id": "smoke-2", "download_url": "https://example.test/s.pdf"})
    repository.confirm(row.resource_id)
    repository.start_download(row.resource_id)
    digest = "ab" * 32
    repository.complete_download(row.resource_id, sha256=digest, relative_path="raw/books/inbox/s.pdf", page_count=1)
    final = repository.get("sha256:" + digest)
    assert final.status == "downloaded"
    assert repository.get(row.resource_id) is None  # 主键已迁移
    repository.reject("sha256:" + digest, reason="冒烟拒绝", by="cli")
    rejected = repository.get("sha256:" + digest)
    assert rejected.status == "rejected"
    assert rejected.reject_reason == "冒烟拒绝"
