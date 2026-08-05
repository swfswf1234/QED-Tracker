"""工作台闭环（QED-014/015/016）：资源状态迁移、下载任务与 PDF 预览端点的定向测试。

契约（docs/design/tracker-service.md）：
- `POST /tasks/books/download`：body `{resource_id}`，仅 confirmed 可触发否则 409；
  任务成功后文件落 raw/books/inbox、MySQL 行迁移为 sha256:<digest> 且 status=downloaded；
- `GET /resources?status=&course_id=&kind=&language=`：MySQL 行 + 本地清单合并，
  MySQL 状态为权威（同 sha256 时本地记录不重复出现）；
- `GET /resources/{id}/file`：仅 downloaded/approved 可访问（iframe 内嵌 PDF 预览），否则 404；
- `POST /resources/{id}/confirm|approve`：非法迁移返回 409；
- `POST /resources/{id}/reject`：body `{reason}` 必填（缺 422）；downloaded 拒绝时硬删文件、
  DB 记录保留留痕。

默认测试不得访问公网：下载走 MockTransport，数据库用 SQLite 文件库。
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.api.main import create_app
from qed_tracker.config import load_settings
from qed_tracker.db.models import Base, ResourceStatus
from qed_tracker.db.repository import ResourceRepository
from qed_tracker.downloader import DownloadManager
from qed_tracker.models import Candidate


@pytest.fixture
def repository(tmp_path):
    # 后台任务线程执行：必须用文件库（:memory: 每连接独立）
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    repo = ResourceRepository(lambda: factory())
    yield repo
    engine.dispose()


def mock_downloader(content: bytes) -> DownloadManager:
    manager = DownloadManager(retries=1)
    manager.client.close()
    manager.client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=content, request=request))
    )
    return manager


class FakeProvider:
    name = "fake"

    def __init__(self, candidate: Candidate):
        self.candidate = candidate

    def search(self, query, limit=10):
        return [self.candidate]

    def resolve(self, candidate):
        return candidate

    def close(self):
        return None


def make_client(tmp_path: Path, *, candidate: Candidate | None = None, downloader=None, repository=None) -> TestClient:
    settings = replace(load_settings(data_root=tmp_path), db_password="")
    providers = [FakeProvider(candidate)] if candidate else None
    app = create_app(
        settings,
        book_providers=providers,
        papers_provider=None,
        downloader=downloader,
        repository=repository,
    )
    return TestClient(app)


def _wait_finished(client: TestClient, task_id: str, timeout: float = 8.0) -> dict:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/v1/tasks/{task_id}").json()
        if data["status"] in ("succeeded", "failed"):
            return data
        time.sleep(0.02)
    raise AssertionError(f"task {task_id} 未在 {timeout}s 内结束")


def _seed_candidate(repository, *, title="Topology", resource_id=None, download_url="https://example.test/t.pdf"):
    row = repository.upsert_candidate(
        title=title,
        authors=["James Munkres"],
        language="en",
        year="2000",
        edition="2nd",
        kind="book",
        source={"provider": "fake", "provider_id": "x3", "download_url": download_url},
        catalog_ref={"catalog_id": "math-qe", "target_id": "03-munkres", "course_id": "03_topology"},
    )
    return row.resource_id if resource_id is None else resource_id


# ---- QED-015：下载任务改 {resource_id}，仅 confirmed 可触发 ----

def test_download_requires_database(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post("/api/v1/tasks/books/download", json={"resource_id": "cand_x"})
        assert response.status_code == 409


def test_download_unknown_resource_returns_409(tmp_path, repository):
    with make_client(tmp_path, repository=repository) as client:
        response = client.post("/api/v1/tasks/books/download", json={"resource_id": "cand_nope"})
        assert response.status_code == 409


def test_download_candidate_not_confirmed_returns_409(tmp_path, repository):
    resource_id = _seed_candidate(repository)
    with make_client(tmp_path, repository=repository) as client:
        response = client.post("/api/v1/tasks/books/download", json={"resource_id": resource_id})
        assert response.status_code == 409
        assert "confirmed" in response.json()["detail"]


def test_download_confirmed_resource_succeeds_and_migrates(tmp_path, repository, pdf_bytes):
    resource_id = _seed_candidate(repository)
    candidate = Candidate("fake", "x3", "Topology", ("James Munkres",), "en", year="2000", edition="2nd", download_url="https://example.test/t.pdf")
    with make_client(tmp_path, candidate=candidate, downloader=mock_downloader(pdf_bytes), repository=repository) as client:
        repository.confirm(resource_id)
        response = client.post("/api/v1/tasks/books/download", json={"resource_id": resource_id})
        assert response.status_code == 202
        task = _wait_finished(client, response.json()["task_id"])
        assert task["status"] == "succeeded"
        # 文件落盘
        pdfs = list((tmp_path / "raw" / "books" / "inbox").glob("*.pdf"))
        assert len(pdfs) == 1
        # MySQL 行迁移为 sha256: 主键且 downloaded
        rows = repository.list()
        assert len(rows) == 1
        row = rows[0]
        assert row.resource_id.startswith("sha256:")
        assert row.status == ResourceStatus.DOWNLOADED.value
        assert row.catalog_ref["target_id"] == "03-munkres"  # 迁移保留目录引用


def test_download_failure_marks_failed_and_retryable(tmp_path, repository):
    resource_id = _seed_candidate(repository)
    candidate = Candidate("fake", "x3", "Topology", ("James Munkres",), "en", download_url="https://example.test/t.pdf")
    failing = DownloadManager(retries=1)
    failing.client.close()
    failing.client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(500, request=request))
    )
    with make_client(tmp_path, candidate=candidate, downloader=failing, repository=repository) as client:
        repository.confirm(resource_id)
        response = client.post("/api/v1/tasks/books/download", json={"resource_id": resource_id})
        task = _wait_finished(client, response.json()["task_id"])
        assert task["status"] == "failed"
        assert repository.get(resource_id).status == ResourceStatus.FAILED.value


# ---- QED-014：/resources 合并清单与状态过滤 ----

def test_resources_merges_mysql_and_inventory(tmp_path, repository, pdf_bytes):
    resource_id = _seed_candidate(repository)
    from qed_tracker.application.resources import ResourceService
    from qed_tracker.inventory import Inventory

    settings = load_settings(data_root=tmp_path)
    service = ResourceService(Inventory(settings.data_root), mock_downloader(pdf_bytes))
    try:
        service.download_candidate(
            Candidate("fake", "x9", "Algebra", ("Lang",), "en", download_url="https://example.test/a.pdf"),
            kind="book",
            destination_dir=settings.data_root / "raw" / "books" / "inbox",
        )
    finally:
        service.close()
    with make_client(tmp_path, repository=repository) as client:
        items = client.get("/api/v1/resources").json()
        titles = {item["title"] for item in items}
        assert titles == {"Topology", "Algebra"}
        mysql_row = next(item for item in items if item["title"] == "Topology")
        assert mysql_row["resource_id"] == resource_id
        assert mysql_row["status"] == ResourceStatus.CANDIDATE.value
        assert mysql_row["catalog_ref"]["course_id"] == "03_topology"


def test_resources_filters_by_status(tmp_path, repository):
    _seed_candidate(repository, title="Topology")
    second = _seed_candidate(repository, title="Analysis", download_url="https://example.test/a.pdf")
    repository.confirm(second)
    with make_client(tmp_path, repository=repository) as client:
        confirmed = client.get("/api/v1/resources", params={"status": "confirmed"}).json()
        assert [item["title"] for item in confirmed] == ["Analysis"]
        candidates = client.get("/api/v1/resources", params={"status": "candidate"}).json()
        assert [item["title"] for item in candidates] == ["Topology"]


def test_resources_filters_by_course(tmp_path, repository):
    _seed_candidate(repository, title="Topology")
    other = _seed_candidate(repository, title="Algebra", download_url="https://example.test/a.pdf")
    # 改为别的课程引用
    row = repository.get(other)
    row.catalog_ref = {"catalog_id": "math-qe", "target_id": "04-bk", "course_id": "04_algebra"}
    from qed_tracker.db.repository import InvalidTransition  # noqa: F401

    with repository._session_factory() as session:  # noqa: SLF001 - 测试直接改写
        session.add(row)
        session.commit()
    with make_client(tmp_path, repository=repository) as client:
        items = client.get("/api/v1/resources", params={"course_id": "03_topology"}).json()
        assert [item["title"] for item in items] == ["Topology"]


# ---- QED-015：PDF 预览端点 ----

def test_resource_file_serves_pdf_for_downloaded(tmp_path, repository, pdf_bytes):
    resource_id = _seed_candidate(repository)
    candidate = Candidate("fake", "x3", "Topology", ("James Munkres",), "en", download_url="https://example.test/t.pdf")
    with make_client(tmp_path, candidate=candidate, downloader=mock_downloader(pdf_bytes), repository=repository) as client:
        repository.confirm(resource_id)
        task_id = client.post("/api/v1/tasks/books/download", json={"resource_id": resource_id}).json()["task_id"]
        _wait_finished(client, task_id)
        final_id = repository.list()[0].resource_id
        response = client.get(f"/api/v1/resources/{final_id}/file")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/pdf")
        assert response.content == pdf_bytes


def test_resource_file_forbidden_before_download(tmp_path, repository):
    resource_id = _seed_candidate(repository)
    repository.confirm(resource_id)
    with make_client(tmp_path, repository=repository) as client:
        response = client.get(f"/api/v1/resources/{resource_id}/file")
        assert response.status_code == 404


def test_resource_file_unknown_returns_404(tmp_path, repository):
    with make_client(tmp_path, repository=repository) as client:
        assert client.get("/api/v1/resources/sha256:deadbeef/file").status_code == 404


# ---- QED-016：confirm / approve / reject ----

def test_confirm_moves_candidate_to_confirmed(tmp_path, repository):
    resource_id = _seed_candidate(repository)
    with make_client(tmp_path, repository=repository) as client:
        response = client.post(f"/api/v1/resources/{resource_id}/confirm")
        assert response.status_code == 200
        assert response.json()["status"] == ResourceStatus.CONFIRMED.value
        assert repository.get(resource_id).status == ResourceStatus.CONFIRMED.value


def test_confirm_unknown_resource_returns_404(tmp_path, repository):
    with make_client(tmp_path, repository=repository) as client:
        assert client.post("/api/v1/resources/cand_nope/confirm").status_code == 404


def test_confirm_invalid_transition_returns_409(tmp_path, repository, pdf_bytes):
    resource_id = _seed_candidate(repository)
    candidate = Candidate("fake", "x3", "Topology", ("James Munkres",), "en", download_url="https://example.test/t.pdf")
    with make_client(tmp_path, candidate=candidate, downloader=mock_downloader(pdf_bytes), repository=repository) as client:
        repository.confirm(resource_id)
        task_id = client.post("/api/v1/tasks/books/download", json={"resource_id": resource_id}).json()["task_id"]
        _wait_finished(client, task_id)
        final_id = repository.list()[0].resource_id  # 下载后主键迁移为 sha256:<digest>
        assert final_id.startswith("sha256:")
        assert client.post(f"/api/v1/resources/{final_id}/confirm").status_code == 409


def test_approve_requires_downloaded(tmp_path, repository):
    resource_id = _seed_candidate(repository)
    with make_client(tmp_path, repository=repository) as client:
        assert client.post(f"/api/v1/resources/{resource_id}/approve").status_code == 409


def test_approve_downloaded_succeeds(tmp_path, repository, pdf_bytes):
    resource_id = _seed_candidate(repository)
    candidate = Candidate("fake", "x3", "Topology", ("James Munkres",), "en", download_url="https://example.test/t.pdf")
    with make_client(tmp_path, candidate=candidate, downloader=mock_downloader(pdf_bytes), repository=repository) as client:
        repository.confirm(resource_id)
        task_id = client.post("/api/v1/tasks/books/download", json={"resource_id": resource_id}).json()["task_id"]
        _wait_finished(client, task_id)
        final_id = repository.list()[0].resource_id
        response = client.post(f"/api/v1/resources/{final_id}/approve")
        assert response.status_code == 200
        assert repository.get(final_id).status == ResourceStatus.APPROVED.value


def test_reject_requires_reason(tmp_path, repository):
    resource_id = _seed_candidate(repository)
    with make_client(tmp_path, repository=repository) as client:
        assert client.post(f"/api/v1/resources/{resource_id}/reject", json={}).status_code == 422
        assert client.post(f"/api/v1/resources/{resource_id}/reject", json={"reason": "  "}).status_code == 422
        assert repository.get(resource_id).status == ResourceStatus.CANDIDATE.value


def test_reject_candidate_records_reason(tmp_path, repository):
    resource_id = _seed_candidate(repository)
    with make_client(tmp_path, repository=repository) as client:
        response = client.post(f"/api/v1/resources/{resource_id}/reject", json={"reason": "版本过旧"})
        assert response.status_code == 200
        row = repository.get(resource_id)
        assert row.status == ResourceStatus.REJECTED.value
        assert row.reject_reason == "版本过旧"
        assert row.rejected_by == "web"


def test_reject_downloaded_removes_file_keeps_record(tmp_path, repository, pdf_bytes):
    resource_id = _seed_candidate(repository)
    candidate = Candidate("fake", "x3", "Topology", ("James Munkres",), "en", download_url="https://example.test/t.pdf")
    with make_client(tmp_path, candidate=candidate, downloader=mock_downloader(pdf_bytes), repository=repository) as client:
        repository.confirm(resource_id)
        task_id = client.post("/api/v1/tasks/books/download", json={"resource_id": resource_id}).json()["task_id"]
        _wait_finished(client, task_id)
        final_id = repository.list()[0].resource_id
        pdfs = list((tmp_path / "raw" / "books" / "inbox").glob("*.pdf"))
        assert len(pdfs) == 1
        pdf_path = pdfs[0]
        response = client.post(f"/api/v1/resources/{final_id}/reject", json={"reason": "内容错误"})
        assert response.status_code == 200
        assert not pdf_path.exists()  # 文件硬删
        row = repository.get(final_id)
        assert row.status == ResourceStatus.REJECTED.value  # DB 记录保留留痕
        assert row.reject_reason == "内容错误"
