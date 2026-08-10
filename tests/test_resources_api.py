"""工作台闭环（QED-014/015/016）：资源状态迁移、下载任务与 PDF 预览端点的定向测试。

契约（docs/design/tracker-service.md）：
- `POST /tasks/books/download`：body `{resource_id}`，仅 confirmed 可触发否则 409；
  任务成功后文件落 raw/books/<catalog_id>/<course_id>/（无目录引用时 inbox）、
  MySQL 行迁移为 sha256:<digest> 且 status=downloaded；
- `GET /resources?status=&course_id=&kind=&language=`：MySQL 行 + 本地清单合并，
  MySQL 状态为权威（同 sha256 时本地记录不重复出现）；
- `GET /resources/{id}/file`：仅 downloaded/approved 可访问（iframe 内嵌 PDF 预览），否则 404；
- `POST /resources/{id}/confirm|backup|approve`：非法迁移返回 409；
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


def mock_downloader(content: bytes, delay: float = 0.0) -> DownloadManager:
    manager = DownloadManager(retries=1)
    manager.client.close()

    def handler(request: httpx.Request) -> httpx.Response:
        if delay:
            import time

            time.sleep(delay)
        return httpx.Response(200, content=content, request=request)

    manager.client = httpx.Client(transport=httpx.MockTransport(handler))
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


def _wait_running_message(client: TestClient, task_id: str, timeout: float = 8.0) -> list[str]:
    """任务运行期间收集 message 快照，用于断言进度步骤。"""
    import time

    messages: list[str] = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/v1/tasks/{task_id}").json()
        if data["status"] in ("succeeded", "failed"):
            break
        if data.get("message") and (not messages or messages[-1] != data["message"]):
            messages.append(data["message"])
        time.sleep(0.01)
    return messages


def test_download_failure_logs_error(tmp_path, repository, caplog):
    """任务失败必须输出结构化日志（含任务类型与错误），便于定位卡点。"""
    import logging

    resource_id = _seed_candidate(repository)
    candidate = Candidate("fake", "x3", "Topology", ("James Munkres",), "en", download_url="https://example.test/t.pdf")
    failing = DownloadManager(retries=1)
    failing.client.close()
    failing.client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500, request=request)))
    with caplog.at_level(logging.INFO, logger="qed_tracker"):
        with make_client(tmp_path, candidate=candidate, downloader=failing, repository=repository) as client:
            repository.confirm(resource_id)
            task_id = client.post("/api/v1/tasks/books/download", json={"resource_id": resource_id}).json()["task_id"]
            task = _wait_finished(client, task_id)
            assert task["status"] == "failed"
    records = [(r.levelname, r.getMessage()) for r in caplog.records]
    assert any("任务失败" in msg for _, msg in records), f"无任务失败日志：{records}"
    assert any("books/download" in msg for _, msg in records), f"日志未含任务类型：{records}"


def test_download_resolves_missing_url_before_fetch(tmp_path, repository, pdf_bytes):
    """evaluate 落库的 archive 候选无 download_url；下载时先经 provider.resolve 补齐并回填。"""

    from dataclasses import replace

    from qed_tracker.api.main import Application, _make_download_handler
    from qed_tracker.config import load_settings

    class ResolvingProvider(FakeProvider):
        def resolve(self, candidate):
            return replace(candidate, download_url="https://example.test/t.pdf")

    resource_id = _seed_candidate(repository, download_url="")
    candidate = Candidate("fake", "x3", "Topology", ("James Munkres",), "en", download_url="")
    settings = replace(load_settings(data_root=tmp_path), db_password="")
    container = Application(
        settings,
        book_providers=[ResolvingProvider(candidate)],
        papers_provider=None,
        downloader=mock_downloader(pdf_bytes),
        repository=repository,
    )
    repository.confirm(resource_id)
    handler = _make_download_handler(container)
    result = handler({"resource_id": resource_id}, lambda pct, msg: None)
    assert result["file"]["sha256"]
    # 候选行主键迁移为 sha256:<digest>
    row = repository.get(f"sha256:{result['file']['sha256']}")
    assert row is not None and row.status == "downloaded"
    assert row.source["download_url"] == "https://example.test/t.pdf"


def test_download_passes_file_keywords_to_resolve(tmp_path, repository, pdf_bytes):
    """source.file_keywords（QED-019 习题答案 file_hint）必须在下载 resolve 时传递给 provider，
    否则同条目多 PDF 会选错文件（默认取最大 PDF=教材本体）。"""

    from dataclasses import replace

    from qed_tracker.api.main import Application, _make_download_handler
    from qed_tracker.config import load_settings

    seen_keywords = {}

    class HintResolvingProvider(FakeProvider):
        def resolve(self, candidate):
            seen_keywords["keywords"] = candidate.file_keywords
            return replace(candidate, download_url="https://example.test/answers.pdf")

    row = repository.upsert_candidate(
        title="数学分析 陈纪修 大学教材",
        authors=["陈纪修"],
        language="chi",
        kind="exercise",
        source={
            "provider": "fake",
            "provider_id": "math_analysis_chenjixiu",
            "download_url": "",
            "file_keywords": ["习题答案"],
        },
        catalog_ref={"catalog_id": "math-qe", "target_id": "01-chenjixiu-exercises", "course_id": "01_math_analysis"},
    )
    candidate = Candidate("fake", "math_analysis_chenjixiu", "数学分析 陈纪修 大学教材", ("陈纪修",), "chi", download_url="")
    settings = replace(load_settings(data_root=tmp_path), db_password="")
    container = Application(
        settings,
        book_providers=[HintResolvingProvider(candidate)],
        papers_provider=None,
        downloader=mock_downloader(pdf_bytes),
        repository=repository,
    )
    repository.confirm(row.resource_id)
    handler = _make_download_handler(container)
    handler({"resource_id": row.resource_id}, lambda pct, msg: None)
    assert seen_keywords["keywords"] == ("习题答案",)


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
        # 文件落盘到课程目录（catalog_ref 派生），文件名带 target_id 前缀
        pdfs = list((tmp_path / "raw" / "books" / "math-qe" / "03_topology").glob("*.pdf"))
        assert len(pdfs) == 1
        assert pdfs[0].name.startswith("03-munkres_")
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
        assert task["error"]  # 失败原因落盘


def test_download_task_reports_progress_steps(tmp_path, repository, pdf_bytes):
    """下载任务 message 随进度更新：下载中(URL) → 校验落盘 → 登记完成。"""
    from dataclasses import replace

    from qed_tracker.api.main import Application, _make_download_handler
    from qed_tracker.config import load_settings

    resource_id = _seed_candidate(repository)
    candidate = Candidate("fake", "x3", "Topology", ("James Munkres",), "en", download_url="https://example.test/t.pdf")
    settings = replace(load_settings(data_root=tmp_path), db_password="")
    container = Application(
        settings,
        book_providers=[FakeProvider(candidate)],
        papers_provider=None,
        downloader=mock_downloader(pdf_bytes),
        repository=repository,
    )
    repository.confirm(resource_id)
    handler = _make_download_handler(container)
    calls: list[tuple[int, str]] = []
    result = handler({"resource_id": resource_id}, lambda pct, msg: calls.append((pct, msg)))
    assert result["file"]["sha256"]
    combined = "\n".join(msg for _, msg in calls)
    assert "https://example.test/t.pdf" in combined, f"进度消息未含下载地址：{calls}"
    assert "校验" in combined, f"进度消息未含校验步骤：{calls}"
    assert "登记" in combined, f"进度消息未含登记步骤：{calls}"
    assert calls[-1][0] == 100
    percents = [pct for pct, _ in calls]
    assert percents == sorted(percents), f"进度非单调：{calls}"


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


# ---- QED-017：人工评估三态（confirm / backup / reject） ----

def test_backup_moves_candidate_to_backup(tmp_path, repository):
    resource_id = _seed_candidate(repository)
    with make_client(tmp_path, repository=repository) as client:
        response = client.post(f"/api/v1/resources/{resource_id}/backup")
        assert response.status_code == 200
        assert response.json()["status"] == ResourceStatus.BACKUP.value
        assert repository.get(resource_id).status == ResourceStatus.BACKUP.value


def test_backup_unknown_resource_returns_404(tmp_path, repository):
    with make_client(tmp_path, repository=repository) as client:
        assert client.post("/api/v1/resources/cand_nope/backup").status_code == 404


def test_backup_invalid_transition_returns_409(tmp_path, repository):
    resource_id = _seed_candidate(repository)
    with make_client(tmp_path, repository=repository) as client:
        repository.confirm(resource_id)
        assert client.post(f"/api/v1/resources/{resource_id}/backup").status_code == 409


def test_backup_then_confirm_promotes(tmp_path, repository):
    """备选转正：backup → confirm 进入下载流程。"""
    resource_id = _seed_candidate(repository)
    with make_client(tmp_path, repository=repository) as client:
        assert client.post(f"/api/v1/resources/{resource_id}/backup").status_code == 200
        response = client.post(f"/api/v1/resources/{resource_id}/confirm")
        assert response.status_code == 200
        assert repository.get(resource_id).status == ResourceStatus.CONFIRMED.value


def test_backup_then_reject_records_reason(tmp_path, repository):
    """放弃备选：backup → reject（原因必填）。"""
    resource_id = _seed_candidate(repository)
    with make_client(tmp_path, repository=repository) as client:
        client.post(f"/api/v1/resources/{resource_id}/backup")
        assert client.post(f"/api/v1/resources/{resource_id}/reject", json={}).status_code == 422
        response = client.post(f"/api/v1/resources/{resource_id}/reject", json={"reason": "放弃备选"})
        assert response.status_code == 200
        row = repository.get(resource_id)
        assert row.status == ResourceStatus.REJECTED.value
        assert row.reject_reason == "放弃备选"


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
        pdfs = list((tmp_path / "raw" / "books" / "math-qe" / "03_topology").glob("*.pdf"))
        assert len(pdfs) == 1
        pdf_path = pdfs[0]
        response = client.post(f"/api/v1/resources/{final_id}/reject", json={"reason": "内容错误"})
        assert response.status_code == 200
        assert not pdf_path.exists()  # 文件硬删
        row = repository.get(final_id)
        assert row.status == ResourceStatus.REJECTED.value  # DB 记录保留留痕
        assert row.reject_reason == "内容错误"


# ---- QED-020：人工评估建议（review_note） ----

def test_confirm_with_note_persists_review_note(tmp_path, repository):
    """confirm 可携带建议 note，落库 review_note 供 Axiom-Flow 参考。"""
    resource_id = _seed_candidate(repository)
    with make_client(tmp_path, repository=repository) as client:
        response = client.post(f"/api/v1/resources/{resource_id}/confirm", json={"note": "版本较新，采用"})
        assert response.status_code == 200
        row = repository.get(resource_id)
        assert row.status == ResourceStatus.CONFIRMED.value
        assert row.review_note == "版本较新，采用"


def test_backup_with_note_persists_review_note(tmp_path, repository):
    resource_id = _seed_candidate(repository)
    with make_client(tmp_path, repository=repository) as client:
        response = client.post(f"/api/v1/resources/{resource_id}/backup", json={"note": "与英文版重复，仅备选"})
        assert response.status_code == 200
        assert repository.get(resource_id).review_note == "与英文版重复，仅备选"


def test_reject_with_note_persists_review_note(tmp_path, repository):
    """拒绝留痕同时支持 reason（必填）与建议 note（可选）。"""
    resource_id = _seed_candidate(repository)
    with make_client(tmp_path, repository=repository) as client:
        response = client.post(
            f"/api/v1/resources/{resource_id}/reject",
            json={"reason": "版本过旧", "note": "已有第 3 版"},
        )
        assert response.status_code == 200
        row = repository.get(resource_id)
        assert row.reject_reason == "版本过旧"
        assert row.review_note == "已有第 3 版"


def test_review_note_absent_when_not_provided(tmp_path, repository):
    """不传 note 时 review_note 保持空字符串（不破坏既有调用）。"""
    resource_id = _seed_candidate(repository)
    with make_client(tmp_path, repository=repository) as client:
        response = client.post(f"/api/v1/resources/{resource_id}/confirm")
        assert response.status_code == 200
        assert repository.get(resource_id).review_note == ""


def test_resources_list_returns_review_note(tmp_path, repository):
    resource_id = _seed_candidate(repository)
    repository.confirm(resource_id, note="版本较新，采用")
    with make_client(tmp_path, repository=repository) as client:
        response = client.get("/api/v1/resources?status=confirmed")
        assert response.status_code == 200
        assert response.json()[0]["review_note"] == "版本较新，采用"


# ---- QED-021：人工下载登记（register 端点） ----

def _seed_pending_manual(repository, *, target_id="01-fikhtengolts-v1"):
    row = repository.upsert_candidate(
        title="微积分学教程 第一卷",
        authors=["菲赫金哥尔茨"],
        language="zh",
        kind="book",
        source={"provider": "libgen_li", "provider_id": "138660986", "links": [{"label": "Torrent", "url": "magnet:?xt=urn:btih:abc", "kind": "torrent"}]},
        catalog_ref={"catalog_id": "math-qe", "target_id": target_id, "course_id": "01_math_analysis"},
    )
    repository.mark_pending_manual(row.resource_id)
    return row.resource_id


def test_register_manual_file_promotes_to_downloaded(tmp_path, repository, pdf_bytes):
    """人工按 libgen 方案下载后放置文件，register 登记：pending_manual → downloaded，
    sha256 回填 + 主键迁移 + 本地清单落库（QED-021）。"""
    resource_id = _seed_pending_manual(repository)
    manual_dir = tmp_path / "raw" / "books" / "math-qe" / "01_math_analysis"
    manual_dir.mkdir(parents=True)
    path = manual_dir / "fikhtengolts_v1.pdf"
    path.write_bytes(pdf_bytes)
    with make_client(tmp_path, repository=repository) as client:
        response = client.post(
            f"/api/v1/resources/{resource_id}/register",
            json={"relative_path": "raw/books/math-qe/01_math_analysis/fikhtengolts_v1.pdf"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == ResourceStatus.DOWNLOADED.value
        assert data["resource_id"].startswith("sha256:")
        assert data["sha256"]
        # 同 sha256 在 MySQL 索引中唯一
        rows = repository.list(status="downloaded")
        assert len(rows) == 1
        assert rows[0].relative_path == "raw/books/math-qe/01_math_analysis/fikhtengolts_v1.pdf"


def test_register_requires_path_inside_data_root(tmp_path, repository, pdf_bytes):
    resource_id = _seed_pending_manual(repository)
    with make_client(tmp_path, repository=repository) as client:
        response = client.post(
            f"/api/v1/resources/{resource_id}/register",
            json={"relative_path": "../outside.pdf"},
        )
        assert response.status_code == 400
        assert repository.get(resource_id).status == ResourceStatus.PENDING_MANUAL.value  # 状态不变


def test_register_unknown_resource_returns_404(tmp_path, repository):
    with make_client(tmp_path, repository=repository) as client:
        assert client.post("/api/v1/resources/cand_nope/register", json={"relative_path": "x.pdf"}).status_code == 404


def test_register_rejects_non_pdf_file(tmp_path, repository):
    resource_id = _seed_pending_manual(repository)
    manual_dir = tmp_path / "raw" / "books" / "math-qe" / "01_math_analysis"
    manual_dir.mkdir(parents=True)
    (manual_dir / "note.txt").write_text("not a pdf", encoding="utf-8")
    with make_client(tmp_path, repository=repository) as client:
        response = client.post(
            f"/api/v1/resources/{resource_id}/register",
            json={"relative_path": "raw/books/math-qe/01_math_analysis/note.txt"},
        )
        assert response.status_code == 400
        assert repository.get(resource_id).status == ResourceStatus.PENDING_MANUAL.value
