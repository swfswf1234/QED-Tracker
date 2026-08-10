"""服务化轮：FastAPI 服务骨架与后台任务层的定向测试。

默认测试不得访问公网：所有提供者都是注入的假实现，下载走 MockTransport。
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from qed_tracker.config import load_settings
from qed_tracker.downloader import DownloadManager
from qed_tracker.models import Candidate


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


class FakeArxiv:
    def search(self, query="", *, category="", author="", limit=10):
        return [
            Candidate(
                "arxiv",
                "2401.00001",
                "A Test Paper",
                ("Alice",),
                "en",
                year="2024",
                download_url="https://arxiv.org/pdf/2401.00001",
            )
        ]

    def search_terms(self, terms, *, category, limit=10):
        return []

    def get(self, identifier):
        return self.search(identifier, limit=1)[0]

    def close(self):
        return None


def make_client(tmp_path: Path, *, candidate: Candidate | None = None, handlers: dict | None = None, downloader: DownloadManager | None = None, repository=None) -> TestClient:
    # 测试隔离：强制无数据库凭据（降级路径），不依赖本机环境
    from dataclasses import replace

    settings = replace(load_settings(data_root=tmp_path), db_password="")
    from qed_tracker.api.main import create_app

    providers = [FakeProvider(candidate)] if candidate else None
    app = create_app(settings, book_providers=providers, papers_provider=FakeArxiv(), downloader=downloader, extra_handlers=handlers, repository=repository)
    return TestClient(app)


def _file_repository(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from qed_tracker.db.models import Base
    from qed_tracker.db.repository import ResourceRepository

    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return ResourceRepository(lambda: factory())


def _seed_confirmed(repository, *, title="Topology 2nd Edition", provider_id="x3", download_url="https://example.test/t.pdf"):
    row = repository.upsert_candidate(
        title=title,
        authors=["James Munkres"],
        language="English",
        kind="book",
        source={"provider": "fake", "provider_id": provider_id, "download_url": download_url},
        catalog_ref={"catalog_id": "math-qe", "target_id": "03-munkres", "course_id": "03_topology"},
    )
    repository.confirm(row.resource_id)
    return row.resource_id


def _wait_finished(client: TestClient, task_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()
        if data["status"] in ("succeeded", "failed"):
            return data
        time.sleep(0.02)
    raise AssertionError(f"task {task_id} 未在 {timeout}s 内结束")


def test_health_returns_ok(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_books_search_is_sync_and_returns_candidates(tmp_path):
    candidate = Candidate("fake", "x1", "Topology", ("James Munkres",), "English", download_url="https://example.test/t.pdf")
    with make_client(tmp_path, candidate=candidate) as client:
        response = client.get("/api/v1/books/search", params={"q": "topology"})
        assert response.status_code == 200
        items = response.json()
        assert isinstance(items, list)
        assert items[0]["title"] == "Topology"
        assert items[0]["provider"] == "fake"


def test_resources_endpoint_lists_inventory(tmp_path, pdf_bytes):
    with make_client(tmp_path, downloader=mock_downloader(pdf_bytes)) as client:
        empty = client.get("/api/v1/resources")
        assert empty.status_code == 200
        assert empty.json() == []
        # 登记一个资源后应可列出
        from qed_tracker.application.resources import ResourceService
        from qed_tracker.inventory import Inventory

        settings = load_settings(data_root=tmp_path)
        service = ResourceService(Inventory(settings.data_root), mock_downloader(pdf_bytes))
        try:
            service.download_candidate(
                Candidate("fake", "x2", "Algebra", ("Lang",), "English", download_url="https://example.test/a.pdf"),
                kind="book",
                destination_dir=settings.data_root / "raw" / "books" / "inbox",
            )
        finally:
            service.close()
        response = client.get("/api/v1/resources")
        assert response.status_code == 200
        assert response.json()[0]["title"] == "Algebra"


def test_catalogs_endpoint_lists_builtin_catalogs(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get("/api/v1/catalogs")
        assert response.status_code == 200
        ids = [item["id"] for item in response.json()]
        assert "math-qe" in ids


def test_download_task_submits_and_polls_to_success(tmp_path, pdf_bytes):
    candidate = Candidate("fake", "x3", "Topology 2nd Edition", ("James Munkres",), "English", download_url="https://example.test/t.pdf")
    repository = _file_repository(tmp_path)
    resource_id = _seed_confirmed(repository)
    with make_client(tmp_path, candidate=candidate, downloader=mock_downloader(pdf_bytes), repository=repository) as client:
        response = client.post("/api/v1/tasks/books/download", json={"resource_id": resource_id})
        assert response.status_code == 202
        task_id = response.json()["task_id"]
        data = _wait_finished(client, task_id)
        assert data["status"] == "succeeded"
        assert (tmp_path / "raw" / "books" / "math-qe" / "03_topology").exists()
        assert list((tmp_path / "raw" / "books" / "math-qe" / "03_topology").glob("*.pdf"))


def test_task_records_are_persisted_under_meta_tasks(tmp_path, pdf_bytes):
    candidate = Candidate("fake", "x4", "Analysis", ("Rudin",), "English", download_url="https://example.test/a.pdf")
    repository = _file_repository(tmp_path)
    resource_id = _seed_confirmed(repository, title="Analysis", provider_id="x4", download_url="https://example.test/a.pdf")
    with make_client(tmp_path, candidate=candidate, downloader=mock_downloader(pdf_bytes), repository=repository) as client:
        response = client.post("/api/v1/tasks/books/download", json={"resource_id": resource_id})
        task_id = response.json()["task_id"]
        _wait_finished(client, task_id)
        assert (tmp_path / "meta" / "tasks" / f"{task_id}.json").exists()


def test_concurrency_is_capped_at_two(tmp_path):
    def slow_handler(params, progress):
        progress(10, "started")
        time.sleep(0.4)
        progress(100, "done")
        return {"ok": True}

    with make_client(tmp_path, handlers={"sleep": slow_handler}) as client:
        ids = [client.post("/api/v1/tasks/sleep", json={}).json()["task_id"] for _ in range(3)]
        time.sleep(0.1)  # 三个任务都进入运行阶段
        states = [client.get(f"/api/v1/tasks/{task_id}").json() for task_id in ids]
        running = sum(1 for item in states if item["status"] == "running")
        assert running <= 2, f"并发运行任务超过 2：{running}"
        for task_id in ids:
            assert _wait_finished(client, task_id)["status"] == "succeeded"


def test_duplicate_download_is_idempotent(tmp_path, pdf_bytes):
    candidate = Candidate("fake", "x5", "Topology 2nd Edition", ("James Munkres",), "English", download_url="https://example.test/t.pdf")
    repository = _file_repository(tmp_path)
    resource_id = _seed_confirmed(repository, provider_id="x5")
    with make_client(tmp_path, candidate=candidate, downloader=mock_downloader(pdf_bytes), repository=repository) as client:
        first = client.post("/api/v1/tasks/books/download", json={"resource_id": resource_id})
        first_id = first.json()["task_id"]
        _wait_finished(client, first_id)
        second = client.post("/api/v1/tasks/books/download", json={"resource_id": resource_id})
        assert second.status_code == 409  # 下载后已非 confirmed，不可重复触发
        pdfs = list((tmp_path / "raw" / "books" / "math-qe" / "03_topology").glob("*.pdf"))
        assert len(pdfs) == 1


def test_cors_allows_frontend_origin(tmp_path):
    with make_client(tmp_path) as client:
        response = client.options("/api/v1/health", headers={"Origin": "http://127.0.0.1:8903", "Access-Control-Request-Method": "GET"})
        assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:8903"
