"""三表 ORM 模型与状态枚举的定向测试（SQLite 内存，不访问公网）。

QED-030：qt_resources 旧表已退役（不再有 ORM 模型），本文件只覆盖
qt_selections / qt_downloads / qt_sources 三表契约。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.db.models import (
    Base,
    DownloadStatus,
    QtDownload,
    QtSelection,
    QtSource,
    SelectionStatus,
)

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
    "intro",
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
