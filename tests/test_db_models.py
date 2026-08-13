"""qt_resources ORM 模型与状态枚举的定向测试（SQLite 内存，不访问公网）。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from qed_tracker.db.models import (
    Base,
    DownloadStatus,
    QtDownload,
    QtResource,
    QtSelection,
    QtSource,
    ResourceStatus,
    SelectionStatus,
)

CONTRACT_FIELDS = [
    "resource_id",
    "sha256",
    "kind",
    "title",
    "authors",
    "language",
    "year",
    "edition",
    "source",
    "retrieved_at",
    "relative_path",
    "page_count",
    "status",
    "llm_evaluation",
    "catalog_ref",
    "confirmed_at",
    "downloaded_at",
    "approved_at",
    "rejected_at",
    "reject_reason",
    "rejected_by",
    "review_note",
    "created_at",
]

ALL_STATUSES = {
    "candidate",
    "confirmed",
    "downloading",
    "downloaded",
    "approved",
    "rejected",
    "failed",
    "pending_manual",
    "not_found",
    "backup",
}

SELECTION_CONTRACT_FIELDS = {
    "selection_id",
    "course_id",
    "title",
    "authors",
    "roles",
    "version",
    "vols",
    "set_no",
    "evaluation",
    "note",
    "status",
    "reject_reason",
    "rejected_by",
    "supersede_reason",
    "created_at",
    "confirmed_at",
    "superseded_at",
    "rejected_at",
}

DOWNLOAD_CONTRACT_FIELDS = {
    "download_id",
    "selection_id",
    "vol",
    "roles",
    "file_hint",
    "sha256",
    "relative_path",
    "page_count",
    "status",
    "reject_reason",
    "rejected_by",
    "review_note",
    "created_at",
    "downloaded_at",
    "approved_at",
    "rejected_at",
}

SOURCE_CONTRACT_FIELDS = {
    "source_id",
    "download_id",
    "channel",
    "provider_id",
    "page_url",
    "download_url",
    "file_keywords",
    "ok",
    "note",
    "attempted_at",
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


def test_status_enum_has_all_ten_states():
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
    row.llm_evaluation = {
        "score": 85,
        "verdict": "recommend",
        "summary": "ok",
        "model": "qwen-plus",
        "evaluated_at": "2026-08-05T00:00:00Z",
    }
    session.commit()
    loaded = session.get(QtResource, row.resource_id)
    assert loaded.authors == ["James Munkres"]
    assert loaded.source["provider"] == "fake"
    assert loaded.catalog_ref["course_id"] == "03"
    assert loaded.llm_evaluation["score"] == 85


def test_status_default_is_candidate(session):
    row = _row(session)
    assert row.status == ResourceStatus.CANDIDATE.value


# --- 三表模型（QED-028，迁移 0003） ---


def test_selection_status_enum_members():
    assert {s.value for s in SelectionStatus} == {"candidate", "confirmed", "backup", "rejected", "superseded"}


def test_download_status_enum_members():
    assert {s.value for s in DownloadStatus} == {
        "candidate",
        "downloading",
        "downloaded",
        "approved",
        "rejected",
        "failed",
    }


def test_selection_table_contract(session):
    columns = {column.name for column in QtSelection.__table__.columns}
    assert columns == SELECTION_CONTRACT_FIELDS
    assert QtSelection.__tablename__ == "qt_selections"


def test_download_table_contract(session):
    columns = {column.name for column in QtDownload.__table__.columns}
    assert columns == DOWNLOAD_CONTRACT_FIELDS
    assert QtDownload.__tablename__ == "qt_downloads"
    assert "uq_qt_downloads_sha256" in {c.name for c in QtDownload.__table__.constraints}


def test_source_table_contract(session):
    columns = {column.name for column in QtSource.__table__.columns}
    assert columns == SOURCE_CONTRACT_FIELDS
    assert QtSource.__tablename__ == "qt_sources"


def test_three_table_round_trip(session):
    selection = QtSelection(
        selection_id="cand_abc",
        course_id="01_math_analysis",
        title="微积分学教程",
        authors=["菲赫金哥尔茨"],
        roles=["textbook"],
        version={"edition": "第8版", "language": "zh"},
        vols=["v1", "v2", "v3"],
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(selection)
    session.commit()

    download = QtDownload(
        download_id="download_v1",
        selection_id=selection.selection_id,
        vol="v1",
        roles=["textbook"],
        sha256="e" * 64,
        relative_path="raw/books/math-qe/01_math_analysis/v1.pdf",
        status="approved",
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(download)
    session.commit()

    source = QtSource(
        source_id="src_1",
        download_id=download.download_id,
        channel="manual",
        ok=1,
        attempted_at=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(source)
    session.commit()

    loaded = session.get(QtSelection, "cand_abc")
    assert loaded.vols == ["v1", "v2", "v3"]
    assert loaded.roles == ["textbook"]
    assert loaded.to_dict()["status"] == "candidate"
    assert session.get(QtDownload, "download_v1").sha256 == "e" * 64
    assert session.get(QtSource, "src_1").ok == 1


def test_download_roles_override_inherit(session):
    """册级 roles 独立列：answers 册可显式覆盖为 solutions。"""
    selection = QtSelection(
        selection_id="cand_sel",
        course_id="01_math_analysis",
        title="数学分析",
        authors=["陈纪修"],
        roles=["textbook"],
        version={},
        vols=["v1", "v2", "answers"],
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(selection)
    answers = QtDownload(
        download_id="download_answers",
        selection_id=selection.selection_id,
        vol="answers",
        roles=["solutions"],
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(answers)
    session.commit()
    assert session.get(QtDownload, "download_answers").roles == ["solutions"]
