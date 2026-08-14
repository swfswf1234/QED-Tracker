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


def make_client(
    tmp_path: Path,
    *,
    candidate: Candidate | None = None,
    handlers: dict | None = None,
    downloader: DownloadManager | None = None,
) -> TestClient:
    # 测试隔离：强制无数据库凭据（降级路径），不依赖本机环境
    from dataclasses import replace

    settings = replace(load_settings(data_root=tmp_path), db_password="")
    from qed_tracker.api.main import create_app

    providers = [FakeProvider(candidate)] if candidate else None
    app = create_app(
        settings, book_providers=providers, papers_provider=FakeArxiv(), downloader=downloader, extra_handlers=handlers
    )
    return TestClient(app)


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
    candidate = Candidate(
        "fake", "x1", "Topology", ("James Munkres",), "English", download_url="https://example.test/t.pdf"
    )
    with make_client(tmp_path, candidate=candidate) as client:
        response = client.get("/api/v1/books/search", params={"q": "topology"})
        assert response.status_code == 200
        items = response.json()
        assert isinstance(items, list)
        assert items[0]["title"] == "Topology"
        assert items[0]["provider"] == "fake"


def test_catalogs_endpoint_lists_builtin_catalogs(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get("/api/v1/catalogs")
        assert response.status_code == 200
        ids = [item["id"] for item in response.json()]
        assert "math-qe" in ids


def test_task_records_are_persisted_under_meta_tasks(tmp_path):
    def ok_handler(params, progress):
        progress(100, "done")
        return {"ok": True}

    with make_client(tmp_path, handlers={"persist": ok_handler}) as client:
        task_id = client.post("/api/v1/tasks/persist", json={}).json()["task_id"]
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


def test_cors_allows_frontend_origin(tmp_path):
    with make_client(tmp_path) as client:
        response = client.options(
            "/api/v1/health", headers={"Origin": "http://127.0.0.1:8903", "Access-Control-Request-Method": "GET"}
        )
        assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:8903"
