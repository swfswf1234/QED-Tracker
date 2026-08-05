"""qt_resources 登记服务与状态机的定向测试（SQLite 内存，不访问公网）。

契约（docs/design/tracker-service.md QED-012）：
- 状态机 candidate→confirmed→downloading→downloaded→approved/rejected（+failed 可重试；
  pending_manual/not_found 辅助状态）；非法迁移抛 InvalidTransition；
- 同 sha256 幂等；reject 必填原因并留痕（rejected_by/rejected_at/reject_reason）；
- JSON 落盘先于 DB 双写，DB 失败保留可重放现场；无密码时降级 no-op。
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.db.models import Base
from qed_tracker.db.registry import ResourceRegistry
from qed_tracker.db.repository import InvalidTransition, ResourceRepository


@pytest.fixture
def repository():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    repo = ResourceRepository(lambda: factory())
    yield repo
    engine.dispose()


CANDIDATE = {
    "title": "Topology 2nd Edition",
    "authors": ["James Munkres"],
    "language": "en",
    "year": "2000",
    "edition": "2nd",
    "kind": "book",
    "source": {"provider": "fake", "provider_id": "x1", "download_url": "https://example.test/t.pdf"},
    "catalog_ref": {"catalog_id": "math-qe", "target_id": "03-munkres", "course_id": "03"},
}


def test_upsert_candidate_is_idempotent(repository):
    first = repository.upsert_candidate(**CANDIDATE, llm_evaluation={"score": 80, "verdict": "recommend", "summary": "", "model": "qwen-plus", "evaluated_at": "2026-08-05T00:00:00Z"})
    second = repository.upsert_candidate(**CANDIDATE, llm_evaluation={"score": 90, "verdict": "recommend", "summary": "", "model": "qwen-plus", "evaluated_at": "2026-08-05T00:00:01Z"})
    assert first.resource_id == second.resource_id
    assert len(repository.list()) == 1
    assert second.llm_evaluation["score"] == 90


def test_legal_transitions_pass(repository):
    row = repository.upsert_candidate(**CANDIDATE)
    repository.confirm(row.resource_id)
    assert repository.get(row.resource_id).status == "confirmed"
    repository.start_download(row.resource_id)
    assert repository.get(row.resource_id).status == "downloading"
    repository.complete_download(row.resource_id, sha256="d" * 64, relative_path="raw/books/math-qe/03_topology/Topology_2nd_Edition_dddddddd.pdf", page_count=372)
    assert repository.get("sha256:" + "d" * 64).status == "downloaded"
    repository.approve("sha256:" + "d" * 64)
    assert repository.get("sha256:" + "d" * 64).status == "approved"


def test_illegal_transitions_raise_409(repository):
    row = repository.upsert_candidate(**CANDIDATE)
    with pytest.raises(InvalidTransition):
        repository.start_download(row.resource_id)  # 未 confirm 即下载
    repository.confirm(row.resource_id)
    with pytest.raises(InvalidTransition):
        repository.approve(row.resource_id)  # 未下载即验收
    repository.start_download(row.resource_id)
    repository.complete_download(row.resource_id, sha256="e" * 64, relative_path="raw/books/inbox/t.pdf", page_count=1)
    repository.reject("sha256:" + "e" * 64, reason="书影不清", by="cli")
    with pytest.raises(InvalidTransition):
        repository.approve("sha256:" + "e" * 64)  # 已拒再验收


def test_failed_can_retry_downloading(repository):
    row = repository.upsert_candidate(**CANDIDATE)
    repository.confirm(row.resource_id)
    repository.start_download(row.resource_id)
    repository.fail(row.resource_id)
    assert repository.get(row.resource_id).status == "failed"
    repository.start_download(row.resource_id)  # failed → downloading 可重试
    assert repository.get(row.resource_id).status == "downloading"


def test_reject_requires_reason_and_leaves_audit_trail(repository):
    row = repository.upsert_candidate(**CANDIDATE)
    with pytest.raises(ValueError):
        repository.reject(row.resource_id, reason="", by="api")
    repository.reject(row.resource_id, reason="重复书", by="api")
    rejected = repository.get(row.resource_id)
    assert rejected.status == "rejected"
    assert rejected.reject_reason == "重复书"
    assert rejected.rejected_by == "api"
    assert rejected.rejected_at is not None
    # 候选级拒绝无文件，DB 记录保留（永不删除）
    assert repository.get(row.resource_id) is not None


def test_complete_download_migrates_candidate_row_to_sha256(repository):
    row = repository.upsert_candidate(**CANDIDATE)
    repository.confirm(row.resource_id)
    repository.start_download(row.resource_id)
    digest = "f" * 64
    repository.complete_download(row.resource_id, sha256=digest, relative_path="raw/books/math-qe/03_topology/Topology_2nd_Edition_ffffffff.pdf", page_count=372)
    migrated = repository.get("sha256:" + digest)
    assert migrated is not None
    assert migrated.title == "Topology 2nd Edition"
    assert migrated.catalog_ref["target_id"] == "03-munkres"
    assert repository.get(row.resource_id) is None  # 候选行主键已迁移


def test_duplicate_sha256_download_reuses_existing_row(repository):
    row = repository.upsert_candidate(**CANDIDATE)
    repository.confirm(row.resource_id)
    repository.start_download(row.resource_id)
    digest = "a" * 64
    repository.complete_download(row.resource_id, sha256=digest, relative_path="raw/books/math-qe/03_topology/t.pdf", page_count=1)
    second = repository.upsert_candidate(title="Topology 2nd Edition", authors=["James Munkres"], language="en", year="2000", edition="2nd", kind="book", source={"provider": "fake", "provider_id": "x1", "download_url": "https://example.test/t.pdf"})
    second_id = second.resource_id
    assert second_id != "sha256:" + digest  # 不同候选行
    repository.confirm(second_id)
    repository.start_download(second_id)
    repository.complete_download(second_id, sha256=digest, relative_path="raw/books/math-qe/03_topology/t.pdf", page_count=1)
    # 同内容已登记：候选行被移除，既有 sha256 行保留
    rows = [item for item in repository.list()]
    assert len(rows) == 1
    assert rows[0].resource_id == "sha256:" + digest


def test_list_filters_by_status_and_course(repository):
    repository.upsert_candidate(**CANDIDATE)
    repository.upsert_candidate(title="习题集", authors=["吉米多维奇"], language="zh", year="", edition="", kind="exercise", source={"provider": "fake", "provider_id": "x2", "download_url": "https://example.test/e.pdf"}, catalog_ref={"catalog_id": "math-qe", "target_id": "01-demidovich", "course_id": "01"})
    assert len(repository.list(status="candidate")) == 2
    assert len(repository.list(status="downloaded")) == 0
    assert len(repository.list(course_id="03")) == 1
    assert len(repository.list(kind="exercise")) == 1
    assert len(repository.list(language="zh")) == 1


def test_find_rejected_same_source(repository):
    row = repository.upsert_candidate(**CANDIDATE)
    repository.reject(row.resource_id, reason="不匹配", by="cli")
    assert repository.find_rejected_same_source(catalog_ref={"catalog_id": "math-qe", "target_id": "03-munkres", "course_id": "03"}, title="Topology 2nd Edition") is True
    assert repository.find_rejected_same_source(catalog_ref={"catalog_id": "math-qe", "target_id": "01-other", "course_id": "01"}, title="Topology 2nd Edition") is False


def test_registry_degrades_without_database(repository):
    registry = ResourceRegistry(None)
    record = {
        "resource_id": "sha256:" + "c" * 64,
        "kind": "book",
        "title": "Algebra",
        "authors": ["Lang"],
        "language": "en",
        "year": "2002",
        "source": {"provider": "fake", "provider_id": "x9", "download_url": "https://example.test/a.pdf"},
        "file": {"relative_path": "raw/books/inbox/Algebra_cccccccc.pdf", "sha256": "c" * 64, "page_count": 1},
        "catalog_ref": None,
    }
    registry.register_downloaded(record)  # 降级：不应抛错
    registry.reject("sha256:" + "c" * 64, reason="x", by="api")  # 降级 no-op


def test_registry_register_downloaded_writes_db_row(repository):
    registry = ResourceRegistry(repository)
    record = {
        "resource_id": "sha256:" + "b" * 64,
        "kind": "book",
        "title": "Algebra",
        "authors": ["Lang"],
        "language": "en",
        "year": "2002",
        "source": {"provider": "fake", "provider_id": "x9", "download_url": "https://example.test/a.pdf"},
        "file": {"relative_path": "raw/books/inbox/Algebra_bbbbbbbb.pdf", "sha256": "b" * 64, "page_count": 1},
        "catalog_ref": {"catalog_id": "math-qe", "target_id": "03-munkres", "course_id": "03"},
    }
    registry.register_downloaded(record)
    row = repository.get("sha256:" + "b" * 64)
    assert row is not None
    assert row.status == "downloaded"
    assert row.relative_path == "raw/books/inbox/Algebra_bbbbbbbb.pdf"
    assert row.catalog_ref["course_id"] == "03"
    assert row.downloaded_at is not None
    registry.register_downloaded(record)  # 幂等
    assert len(repository.list()) == 1
