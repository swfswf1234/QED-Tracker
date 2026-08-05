"""qt_resources ORM 模型与状态枚举的定向测试（SQLite 内存，不访问公网）。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from qed_tracker.db.models import Base, QtResource, ResourceStatus

CONTRACT_FIELDS = [
    "resource_id", "sha256", "kind", "title", "authors", "language", "year", "edition",
    "source", "retrieved_at", "relative_path", "page_count", "status", "llm_evaluation",
    "catalog_ref", "confirmed_at", "downloaded_at", "approved_at", "rejected_at",
    "reject_reason", "rejected_by", "created_at",
]

ALL_STATUSES = {
    "candidate", "confirmed", "downloading", "downloaded", "approved", "rejected",
    "failed", "pending_manual", "not_found",
}


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory()
    engine.dispose()


def _row(session, resource_id: str = "sha256:" + "a" * 64) -> QtResource:
    row = QtResource(
        resource_id=resource_id,
        kind="book",
        title="Topology",
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(row)
    session.commit()
    return row


def test_status_enum_has_all_nine_states():
    assert {status.value for status in ResourceStatus} == ALL_STATUSES


def test_table_has_all_contract_fields(session):
    columns = {column.name for column in QtResource.__table__.columns}
    assert set(CONTRACT_FIELDS) == columns
    assert QtResource.__tablename__ == "qt_resources"


def test_sha256_column_is_unique(session):
    first = _row(session, "sha256:" + "a" * 64)
    first.sha256 = "d" * 64
    session.commit()
    second = QtResource(
        resource_id="sha256:" + "b" * 64,
        sha256="d" * 64,
        kind="book",
        title="Duplicate",
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(second)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_json_columns_round_trip(session):
    row = _row(session)
    row.authors = ["James Munkres"]
    row.source = {"provider": "fake", "download_url": "https://example.test/t.pdf"}
    row.catalog_ref = {"catalog_id": "math-qe", "target_id": "03-munkres", "course_id": "03"}
    row.llm_evaluation = {"score": 85, "verdict": "recommend", "summary": "ok", "model": "qwen-plus", "evaluated_at": "2026-08-05T00:00:00Z"}
    session.commit()
    loaded = session.get(QtResource, row.resource_id)
    assert loaded.authors == ["James Munkres"]
    assert loaded.source["provider"] == "fake"
    assert loaded.catalog_ref["course_id"] == "03"
    assert loaded.llm_evaluation["score"] == 85


def test_status_default_is_candidate(session):
    row = _row(session)
    assert row.status == ResourceStatus.CANDIDATE.value
