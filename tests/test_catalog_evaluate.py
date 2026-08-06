"""catalog/evaluate 评估任务的定向测试（SQLite 内存 + 假提供者，不访问公网）。

契约（docs/design/tracker-service.md QED-013）：
- POST /tasks/catalog/evaluate {course_id?}：按课程搜索源 → LLM 评估 → 候选落库（candidate +
  llm_evaluation + catalog_ref）；宁缺勿滥（低分不收录）；
- 中文书来源不可得登记 pending_manual；英文书登记 not_found；
- 已拒同源（catalog_ref + title）跳过不重复推荐；
- 无 LLM key 时降级：跳过评估，仍落候选（无 llm_evaluation）。
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.db.models import Base, ResourceStatus
from qed_tracker.db.repository import ResourceRepository
from qed_tracker.models import Candidate


@pytest.fixture
def repository(tmp_path):
    # 后台任务线程执行：SQLite 必须用文件库（:memory: 每连接独立，任务线程看不到表）
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    repo = ResourceRepository(lambda: factory())
    yield repo
    engine.dispose()


class FakeProvider:
    name = "fake"

    def __init__(self, candidate: Candidate | None = None, candidates: list[Candidate] | None = None):
        self.candidates = candidates if candidates is not None else ([candidate] if candidate else [])

    def search(self, query, limit=10):
        return self.candidates

    def resolve(self, candidate):
        return candidate

    def close(self):
        return None


class FakeAdvisor:
    def __init__(self, score: int = 85, verdict: str = "recommend"):
        self.score = score
        self.verdict = verdict
        self.model_name = "fake-model"

    def assess(self, candidates, *, target):
        from qed_tracker.models import BookAssessment

        return [
            BookAssessment(
                provider_id=item.provider_id,
                score=self.score,
                verdict=self.verdict,
                summary="匹配课程目标",
            )
            for item in candidates
        ]

    def metadata(self):
        return {"model": self.model_name, "contract_version": "book-eval-v1", "calls": 1}

    def close(self):
        return None


def make_client(tmp_path: Path, *, provider: FakeProvider | None = None, advisor=None, repository=None):
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from qed_tracker.api.main import create_app
    from qed_tracker.config import load_settings

    settings = replace(load_settings(data_root=tmp_path), db_password="")
    app = create_app(
        settings,
        book_providers=[provider] if provider else None,
        papers_provider=None,
        repository=repository,
        advisor=advisor,
    )
    return TestClient(app)


def _wait_finished(client, task_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()
        if data["status"] in ("succeeded", "failed"):
            return data
        time.sleep(0.02)
    raise AssertionError(f"task {task_id} 未在 {timeout}s 内结束")


def _submit_evaluate(client, course_id: str | None = None) -> dict:
    payload = {"course_id": course_id} if course_id else {}
    response = client.post("/api/v1/tasks/catalog/evaluate", json=payload)
    assert response.status_code == 202
    return _wait_finished(client, response.json()["task_id"])


class BrokenProvider:
    """模拟 DNS 污染/连接黑洞：搜索抛连接错误。"""

    name = "broken"

    def search(self, query, limit=10):
        raise ConnectionError("connect to 69.63.184.142:443 failed: timeout")

    def resolve(self, candidate):
        return candidate

    def close(self):
        return None


def test_evaluate_reports_provider_failure_details(tmp_path, repository):
    """来源失败 reason 必须包含每个 provider 的具体错误，便于定位卡点。"""
    with make_client(tmp_path, provider=BrokenProvider(), advisor=None, repository=repository) as client:
        task = _submit_evaluate(client, course_id="03")
        assert task["status"] == "succeeded"
        not_found = [item for item in task["result"]["not_found"] if item["target_id"] == "03-munkres"]
        assert not_found
        assert "broken" in not_found[0]["reason"]
        assert "69.63.184.142" in not_found[0]["reason"]


def test_evaluate_logs_provider_failure(tmp_path, repository, caplog):
    """来源搜索失败必须输出 warning 日志（含 provider 名），联调时能直接看服务日志定位。"""
    import logging

    with caplog.at_level(logging.WARNING, logger="qed_tracker"):
        with make_client(tmp_path, provider=BrokenProvider(), advisor=None, repository=repository) as client:
            task = _submit_evaluate(client, course_id="03")
            assert task["status"] == "succeeded"
    records = [(r.levelname, r.getMessage()) for r in caplog.records]
    assert any("broken" in msg and "69.63.184.142" in msg for _, msg in records), f"无来源失败日志：{records}"


def test_evaluate_progress_reports_targets(tmp_path, repository):
    """进度回调按 target 推进并带目标标识，前端轮询可看到卡在哪个目标。"""
    from dataclasses import replace

    from qed_tracker.application.books import BookService
    from qed_tracker.application.catalog_evaluate import CatalogEvaluator
    from qed_tracker.application.resources import ResourceService
    from qed_tracker.catalog import load_catalog
    from qed_tracker.config import load_settings
    from qed_tracker.downloader import DownloadManager
    from qed_tracker.inventory import Inventory

    settings = replace(load_settings(data_root=tmp_path), db_password="")
    books = BookService([FakeProvider()], ResourceService(Inventory(settings.data_root), DownloadManager()))
    evaluator = CatalogEvaluator(books, repository, advisor=FakeAdvisor())
    messages: list[tuple[int, str]] = []
    evaluator.evaluate(load_catalog("math-qe"), course="03", progress=lambda pct, msg: messages.append((pct, msg)))
    assert messages, "progress 回调未被调用"
    assert any("03-munkres" in msg for _, msg in messages), f"进度消息未含目标标识：{messages}"
    assert messages[0][0] > 0
    # 进度单调不减
    percents = [pct for pct, _ in messages]
    assert percents == sorted(percents)


def _row_by_target(repository, target_id: str):
    return next((row for row in repository.list() if row.catalog_ref and row.catalog_ref.get("target_id") == target_id), None)


def test_evaluate_registers_candidate_with_evaluation_and_catalog_ref(tmp_path, repository):
    candidate = Candidate(
        "fake", "x3", "Topology", ("James Munkres",), "en", year="2000", edition="2nd",
        download_url="https://example.test/t.pdf",
    )
    with make_client(tmp_path, provider=FakeProvider(candidate), advisor=FakeAdvisor(score=85), repository=repository) as client:
        task = _submit_evaluate(client, course_id="03")
        assert task["status"] == "succeeded"
        row = _row_by_target(repository, "03-munkres")
        assert row is not None
        assert row.status == ResourceStatus.CANDIDATE.value
        assert row.catalog_ref == {"catalog_id": "math-qe", "target_id": "03-munkres", "course_id": "03_topology"}
        assert row.llm_evaluation["score"] == 85
        assert row.llm_evaluation["verdict"] == "recommend"
        assert row.source["provider"] == "fake"


def test_evaluate_skips_low_score_candidates(tmp_path, repository):
    candidate = Candidate("fake", "x3", "Topology", ("James Munkres",), "en", download_url="https://example.test/t.pdf")
    with make_client(tmp_path, provider=FakeProvider(candidate), advisor=FakeAdvisor(score=30, verdict="uncertain"), repository=repository) as client:
        task = _submit_evaluate(client, course_id="03")
        assert task["status"] == "succeeded"
        assert repository.list(status="candidate") == []


def test_evaluate_marks_chinese_book_pending_manual_when_unavailable(tmp_path, repository):
    with make_client(tmp_path, provider=FakeProvider(), advisor=FakeAdvisor(), repository=repository) as client:
        task = _submit_evaluate(client, course_id="01")
        assert task["status"] == "succeeded"
        rows = [row for row in repository.list() if row.status == ResourceStatus.PENDING_MANUAL.value]
        assert rows
        assert rows[0].title == "数学分析原理"
        assert rows[0].catalog_ref["course_id"] == "01_math_analysis"


def test_evaluate_marks_english_book_not_found_when_unavailable(tmp_path, repository):
    with make_client(tmp_path, provider=FakeProvider(), advisor=FakeAdvisor(), repository=repository) as client:
        task = _submit_evaluate(client, course_id="11")
        assert task["status"] == "succeeded"
        rows = [row for row in repository.list() if row.status == ResourceStatus.NOT_FOUND.value]
        assert rows


def test_evaluate_skips_rejected_same_source(tmp_path, repository):
    row = repository.upsert_candidate(
        title="Topology",
        authors=["James Munkres"],
        language="en",
        kind="book",
        source={"provider": "fake", "provider_id": "x3", "download_url": "https://example.test/t.pdf"},
        catalog_ref={"catalog_id": "math-qe", "target_id": "03-munkres", "course_id": "03"},
    )
    repository.reject(row.resource_id, reason="人工核对为错误版本", by="cli")
    candidate = Candidate("fake", "x3", "Topology", ("James Munkres",), "en", download_url="https://example.test/t.pdf")
    with make_client(tmp_path, provider=FakeProvider(candidate), advisor=FakeAdvisor(score=90), repository=repository) as client:
        task = _submit_evaluate(client, course_id="03")
        assert task["status"] == "succeeded"
        # 同源已拒候选不得重新推荐
        assert repository.list(status="candidate") == []
        assert _row_by_target(repository, "03-munkres").status == ResourceStatus.REJECTED.value


def test_evaluate_skips_backup_and_approved_targets(tmp_path, repository):
    """已评估目标（backup/approved）不得被重新评估重置回 candidate（QED-017）。"""
    # backup 目标：03-munkres 被人工标为备选
    row = repository.upsert_candidate(
        title="Topology",
        authors=["James Munkres"],
        language="en",
        kind="book",
        source={"provider": "fake", "provider_id": "x3", "download_url": "https://example.test/t.pdf"},
        catalog_ref={"catalog_id": "math-qe", "target_id": "03-munkres", "course_id": "03"},
    )
    repository.mark_backup(row.resource_id)
    candidate = Candidate("fake", "x3", "Topology", ("James Munkres",), "en", download_url="https://example.test/t.pdf")
    with make_client(tmp_path, provider=FakeProvider(candidate), advisor=FakeAdvisor(score=90), repository=repository) as client:
        task = _submit_evaluate(client, course_id="03")
        assert task["status"] == "succeeded"
        skipped = [item for item in task["result"]["skipped"] if item["target_id"] == "03-munkres"]
        assert skipped, "backup 目标应进入 skipped"
        assert repository.get(row.resource_id).status == ResourceStatus.BACKUP.value  # 不被重置
        assert repository.list(status="candidate") == []


def test_evaluate_skips_downloaded_and_confirmed_targets(tmp_path, repository):
    """已确认/已下载目标同样不被重置（此前 find_candidate_by_ref 只查 candidate，会漏判）。"""
    row = repository.upsert_candidate(
        title="Topology",
        authors=["James Munkres"],
        language="en",
        kind="book",
        source={"provider": "fake", "provider_id": "x3", "download_url": "https://example.test/t.pdf"},
        catalog_ref={"catalog_id": "math-qe", "target_id": "03-munkres", "course_id": "03"},
    )
    repository.confirm(row.resource_id)
    candidate = Candidate("fake", "x3", "Topology", ("James Munkres",), "en", download_url="https://example.test/t.pdf")
    with make_client(tmp_path, provider=FakeProvider(candidate), advisor=FakeAdvisor(score=90), repository=repository) as client:
        task = _submit_evaluate(client, course_id="03")
        assert task["status"] == "succeeded"
        skipped = [item for item in task["result"]["skipped"] if item["target_id"] == "03-munkres"]
        assert skipped, "confirmed 目标应进入 skipped"
        assert repository.get(row.resource_id).status == ResourceStatus.CONFIRMED.value
        assert repository.list(status="candidate") == []


def test_evaluate_without_advisor_still_registers_candidates(tmp_path, repository):
    candidate = Candidate("fake", "x3", "Topology", ("James Munkres",), "en", year="2000", edition="2nd", download_url="https://example.test/t.pdf")
    with make_client(tmp_path, provider=FakeProvider(candidate), advisor=None, repository=repository) as client:
        task = _submit_evaluate(client, course_id="03")
        assert task["status"] == "succeeded"
        row = _row_by_target(repository, "03-munkres")
        assert row is not None
        assert row.status == ResourceStatus.CANDIDATE.value
        assert row.llm_evaluation is None


def test_evaluate_without_database_fails_task(tmp_path):
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from qed_tracker.api.main import create_app
    from qed_tracker.config import load_settings

    settings = replace(load_settings(data_root=tmp_path), db_password="")
    app = create_app(settings, book_providers=[FakeProvider()], papers_provider=None, repository=None)
    with TestClient(app) as client:
        response = client.post("/api/v1/tasks/catalog/evaluate", json={"course_id": "03"})
        assert response.status_code == 202
        task = _wait_finished(client, response.json()["task_id"])
        assert task["status"] == "failed"
        assert "数据库" in task["error"]
