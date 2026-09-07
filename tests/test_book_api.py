"""书库化 API 契约定向测试（QED-050 书库化 + 五阶段取书 + 并发防护）。

覆盖：书库化创建（201/409/422）、原地登记与人工导入（mark_owned 唯一写入口、
D9 命名、无归属 422、不覆盖用户文件 409、跳过初筛门槛）、书级 fetch（202、
任务成功 owned / 已 owned no-op / 退役 409）、教程级 fetch（refs 聚合 /
include_parallel / 404）、同书与同教程活动任务查重 409。

默认测试不访问公网：providers 为假实现，下载走 MockTransport；LLM 由
monkeypatch 清空。
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import replace
from io import BytesIO

import httpx
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.api.main import create_app
from qed_tracker.application.books import BookService
from qed_tracker.application.resources import ResourceService
from qed_tracker.config import load_settings
from qed_tracker.db.knowledge_repository import KnowledgeRepository
from qed_tracker.db.models import Base, QedCourse, QedDomain
from qed_tracker.downloader import DownloadManager
from qed_tracker.inventory import Inventory
from qed_tracker.models import Availability, Candidate

COURSE = "01_math_analysis"
ABBR = "01mathanalysis"


# ---------------- 夹具与假实现 ----------------


@pytest.fixture
def repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'book_api.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    from qed_tracker.db.engine import utc_now

    now = utc_now()
    session.add(QedDomain(domain_id="math", name="数学", description="d", stages=["基础"],
                          created_at=now, updated_at=now))
    session.add(QedCourse(course_id=COURSE, domain_id="math", sort_order=1, name="数学分析",
                          aliases=[], stage="基础", prerequisites=[], related_targets=[],
                          created_at=now, updated_at=now))
    session.commit()
    yield KnowledgeRepository(lambda: factory())
    engine.dispose()


@pytest.fixture
def client(tmp_path, repo, monkeypatch):
    _strip_llm(monkeypatch)
    settings = replace(load_settings(data_root=tmp_path), db_password="")
    app = create_app(settings, knowledge_repository=repo)
    with TestClient(app) as test_client:
        yield test_client


def _strip_llm(monkeypatch) -> None:
    """清空 LLM 键（本机 .env 常有真实键）：main 直读 settings.llm_configured 两处引用都置空。"""
    monkeypatch.setattr("qed_tracker.api.main.llm_api_key", lambda: "")
    monkeypatch.setattr("qed_tracker.config.llm_api_key", lambda: "")


def _ref(book_id: str, title: str, **extra) -> dict:
    value = {
        "book_id": book_id, "title": title, "part": "",
        "authors": [{"name": "菲赫金哥尔茨", "role": "author"}],
        "publisher": "高等教育出版社", "edition": "第3版", "year": 2006,
        "language": "zh", "roles": ["textbook"],
    }
    value.update(extra)
    return value


def _adopt(repo: KnowledgeRepository, set_no: str, *, textbook: list[dict],
           exercise: list[dict] | None = None, parallel: list[dict] | None = None) -> str:
    results = repo.adopt_tutorials(COURSE, [{
        "set_no": set_no, "name": f"教程{set_no}：测试", "position": "beginner",
        "intro": "测试教程" * 20, "textbook_ref": textbook,
        "exercise_ref": exercise, "parallel_ref": parallel,
    }])
    return results[0]["knowledge_id"]


def _passing_pdf_bytes(*, pages: int = 12, pad: int = 260_000) -> bytes:
    """能通过默认机器验收门（>=10 页 / >=200KB）的 PDF；人工路径完整性校验亦通过。"""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    writer.add_metadata({"/Producer": "Q" * pad})
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


def _sha8(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()[:8]


def _make_candidate(title: str, *, pid: str = "fake-1") -> Candidate:
    return Candidate(
        "fake", pid, title, ("菲赫金哥尔茨",), "Chinese", year="2006",
        download_url="https://example.com/fake.pdf",
        availability=Availability.DOWNLOADABLE,
    )


class FakeProvider:
    """按 query 返回候选的假渠道（契约同 test_book_fetch.FakeProvider）。"""

    def __init__(self, by_query: dict[str, list[Candidate]] | None = None,
                 *, static: list[Candidate] | None = None):
        self.name = "fake"
        self.by_query = by_query or {}
        self.static = static
        self.queries: list[str] = []

    def search(self, query, limit=10):
        self.queries.append(query)
        if self.static is not None:
            return list(self.static)
        return list(self.by_query.get(query, []))

    def resolve(self, candidate):
        return candidate

    def close(self):
        return None


def _fetch_client(tmp_path, repo, provider, pdf: bytes, monkeypatch) -> TestClient:
    """带假 book_service_factory 的离线 client：fetch 任务全程不触网、不用 LLM。"""
    _strip_llm(monkeypatch)

    def handler(request):
        return httpx.Response(200, content=pdf, request=request)

    def factory():
        manager = DownloadManager(retries=1)
        manager.client.close()
        manager.client = httpx.Client(transport=httpx.MockTransport(handler))
        return BookService([provider], ResourceService(Inventory(tmp_path), manager))

    settings = replace(load_settings(data_root=tmp_path), db_password="")
    app = create_app(settings, knowledge_repository=repo, book_service_factory=factory)
    return TestClient(app)


def _wait(client: TestClient, task_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        record = client.get(f"/api/v1/tasks/{task_id}").json()
        if record["status"] in ("succeeded", "failed"):
            return record
        time.sleep(0.05)
    raise AssertionError("任务未在超时内结束")


def _blocking_client(tmp_path, repo, task_type: str, started: threading.Event,
                     release: threading.Event) -> TestClient:
    """覆盖指定任务类型为阻塞桩：并发查重测试用（不触编排层）。"""

    def handler(params, progress):
        started.set()
        release.wait(timeout=10)
        return {"ok": True}

    settings = replace(load_settings(data_root=tmp_path), db_password="")
    app = create_app(settings, knowledge_repository=repo, extra_handlers={task_type: handler})
    return TestClient(app)


# ---------------- 书库化创建（POST /books） ----------------


def test_create_book_library_style(client):
    resp = client.post("/api/v1/books", json={
        "book_id": f"{ABBR}-b01", "title": "微积分学教程", "part": "第一卷",
        "original_title": "Курс дифференциального исчисления",
        "authors": [{"name": "菲赫金哥尔茨", "role": "author"}],
        "language": "zh", "roles": ["textbook"], "domain_id": "math",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["book_id"] == f"{ABBR}-b01"
    assert body["title"] == "微积分学教程"
    assert body["status"] == "candidate"
    assert body["holding"] == "missing"
    assert body["original_title"].startswith("Курс")
    assert body["authors"] == [{"name": "菲赫金哥尔茨", "role": "author"}]


def test_create_book_validations(client):
    base = {"book_id": f"{ABBR}-b01", "title": "微积分学教程"}
    assert client.post("/api/v1/books", json={"book_id": "bad id!", "title": "t"}).status_code == 422
    assert client.post("/api/v1/books", json={"book_id": f"{ABBR}-b01"}).status_code == 422
    assert client.post("/api/v1/books", json={**base, "status": "downloaded"}).status_code == 422
    assert client.post("/api/v1/books", json={**base, "authors": ["文本作者"]}).status_code == 422
    assert client.post("/api/v1/books", json={**base, "year": "2006"}).status_code == 422


def test_create_book_duplicate_409(client):
    payload = {"book_id": f"{ABBR}-b01", "title": "微积分学教程"}
    assert client.post("/api/v1/books", json=payload).status_code == 201
    resp = client.post("/api/v1/books", json=payload)
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "BOOK_ALREADY_EXISTS"


# ---------------- 原地登记（POST /books/{id}/register） ----------------


def test_register_in_place_marks_owned(client, repo, tmp_path, pdf_bytes):
    repo.create_book(f"{ABBR}-b01", title="微积分学教程", language="zh")
    rel = "raw/math/01_math_analysis/manual.pdf"
    target = tmp_path / rel
    target.parent.mkdir(parents=True)
    target.write_bytes(pdf_bytes)
    resp = client.post(f"/api/v1/books/{ABBR}-b01/register", json={"relative_path": rel})
    assert resp.status_code == 200
    body = resp.json()
    assert body["holding"] == "owned"
    assert body["file_path"] == rel
    sources = repo.list_sources(f"{ABBR}-b01")
    assert len(sources) == 1 and sources[0].ok is True and sources[0].channel == "local_import"


def test_register_validations(client, repo, tmp_path):
    repo.create_book(f"{ABBR}-b01", title="微积分学教程")
    assert client.post("/api/v1/books/nope-b01/register", json={"relative_path": "x.pdf"}).status_code == 404
    assert client.post(f"/api/v1/books/{ABBR}-b01/register", json={}).status_code == 422
    assert client.post(f"/api/v1/books/{ABBR}-b01/register",
                       json={"relative_path": "../escape.pdf"}).status_code == 400
    assert client.post(f"/api/v1/books/{ABBR}-b01/register",
                       json={"relative_path": "raw/missing.pdf"}).status_code == 404
    bad = tmp_path / "raw" / "not_pdf.txt"
    bad.parent.mkdir(parents=True)
    bad.write_text("not a pdf", encoding="utf-8")
    resp = client.post(f"/api/v1/books/{ABBR}-b01/register", json={"relative_path": "raw/not_pdf.txt"})
    assert resp.status_code == 400
    assert repo.get_book(f"{ABBR}-b01").holding == "missing"  # 校验失败不登记


# ---------------- 人工导入（POST /books/{id}/import） ----------------


def test_import_default_bucket_and_d9_naming(client, repo, tmp_path, pdf_bytes):
    knowledge_id = _adopt(repo, "1", textbook=[_ref(f"{ABBR}-b01", "微积分学教程")])
    assert knowledge_id
    source = tmp_path / "inbox" / "下载.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(pdf_bytes)
    resp = client.post(f"/api/v1/books/{ABBR}-b01/import", json={"file_path": str(source)})
    assert resp.status_code == 200
    expected = (tmp_path / "raw" / "math" / COURSE / f"微积分学教程_{_sha8(pdf_bytes)}.pdf")
    assert expected.is_file()
    body = resp.json()
    assert body["holding"] == "owned"
    assert body["file_path"] == expected.relative_to(tmp_path).as_posix()
    note = repo.list_sources(f"{ABBR}-b01")[0].note
    assert "手工导入" in note and "跳过初筛门槛" in note


def test_import_requires_target_without_course_ref(client, repo, tmp_path, pdf_bytes):
    repo.create_book(f"{ABBR}-b01", title="微积分学教程", domain_id="math")
    source = tmp_path / "s.pdf"
    source.write_bytes(pdf_bytes)
    resp = client.post(f"/api/v1/books/{ABBR}-b01/import", json={"file_path": str(source)})
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "NO_COURSE_REF"


def test_import_explicit_target_d9(client, repo, tmp_path, pdf_bytes):
    repo.create_book(f"{ABBR}-b01", title="微积分学教程", domain_id="math")
    source = tmp_path / "s.pdf"
    source.write_bytes(pdf_bytes)
    resp = client.post(f"/api/v1/books/{ABBR}-b01/import", json={
        "file_path": str(source), "target_path": "raw/math/01_math_analysis/manual.pdf",
    })
    assert resp.status_code == 200
    assert (tmp_path / "raw" / "math" / COURSE / f"manual_{_sha8(pdf_bytes)}.pdf").is_file()


def test_import_same_sha_reuses_existing_file(client, repo, tmp_path, pdf_bytes):
    _adopt(repo, "1", textbook=[_ref(f"{ABBR}-b01", "微积分学教程")])
    target = tmp_path / "raw" / "math" / COURSE / f"微积分学教程_{_sha8(pdf_bytes)}.pdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(pdf_bytes)
    source = tmp_path / "s.pdf"
    source.write_bytes(pdf_bytes)
    resp = client.post(f"/api/v1/books/{ABBR}-b01/import", json={"file_path": str(source)})
    assert resp.status_code == 200
    assert repo.get_book(f"{ABBR}-b01").holding == "owned"
    assert len(list((tmp_path / "raw" / "math" / COURSE).glob("*.pdf"))) == 1  # 不重复落盘


def test_import_target_conflict_409(client, repo, tmp_path, pdf_bytes):
    """目标已存在且内容不同：409 不覆盖用户文件（治理约束：不隐式移动/删除用户 PDF）。"""
    _adopt(repo, "1", textbook=[_ref(f"{ABBR}-b01", "微积分学教程")])
    target = tmp_path / "raw" / "math" / COURSE / f"微积分学教程_{_sha8(pdf_bytes)}.pdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"keep user file")
    source = tmp_path / "s.pdf"
    source.write_bytes(pdf_bytes)
    resp = client.post(f"/api/v1/books/{ABBR}-b01/import", json={"file_path": str(source)})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "TARGET_CONFLICT"
    assert target.read_bytes() == b"keep user file"
    assert repo.get_book(f"{ABBR}-b01").holding == "missing"


def test_import_rejects_non_pdf(client, repo, tmp_path):
    _adopt(repo, "1", textbook=[_ref(f"{ABBR}-b01", "微积分学教程")])
    source = tmp_path / "s.txt"
    source.write_text("not a pdf", encoding="utf-8")
    resp = client.post(f"/api/v1/books/{ABBR}-b01/import", json={"file_path": str(source)})
    assert resp.status_code == 400
    assert repo.get_book(f"{ABBR}-b01").holding == "missing"


def test_import_outside_data_root_target_400(client, repo, tmp_path, pdf_bytes):
    _adopt(repo, "1", textbook=[_ref(f"{ABBR}-b01", "微积分学教程")])
    source = tmp_path / "s.pdf"
    source.write_bytes(pdf_bytes)
    resp = client.post(f"/api/v1/books/{ABBR}-b01/import", json={
        "file_path": str(source), "target_path": "../escape.pdf",
    })
    assert resp.status_code == 400


# ---------------- 书级 fetch（五阶段编排后台任务） ----------------


def test_book_fetch_task_marks_owned_then_noop(tmp_path, repo, monkeypatch):
    pdf = _passing_pdf_bytes()
    knowledge_id = _adopt(repo, "1", textbook=[_ref(f"{ABBR}-b01", "微积分学教程")])
    book_id = repo.list_books(knowledge_id)[0].book_id
    provider = FakeProvider(static=[_make_candidate("微积分学教程")])
    with _fetch_client(tmp_path, repo, provider, pdf, monkeypatch) as fetch_client:
        resp = fetch_client.post(f"/api/v1/books/{book_id}/fetch")
        assert resp.status_code == 202
        assert resp.json()["book_id"] == book_id
        record = _wait(fetch_client, resp.json()["task_id"])
        assert record["status"] == "succeeded", record
        result = record["result"]
        assert result["ok"] is True and result["skipped"] is False
        book = repo.get_book(book_id)
        assert book.holding == "owned"
        assert book.file_path == result["file_path"]
        final = tmp_path / result["file_path"]
        assert final.is_file() and final.parent == tmp_path / "raw" / "math" / COURSE
        assert repo.list_sources(book_id)[0].ok is True

        # 已 owned 重复 fetch：任务成功且 no-op（编排层跳过）
        resp2 = fetch_client.post(f"/api/v1/books/{book_id}/fetch")
        assert resp2.status_code == 202
        result2 = _wait(fetch_client, resp2.json()["task_id"])["result"]
        assert result2["skipped"] is True and result2["reason"] == "已 owned，无需取书"


def test_book_fetch_retired_409_and_unknown_404(client, repo):
    repo.create_book(f"{ABBR}-b01", title="微积分学教程")
    repo.retire_book(f"{ABBR}-b01", reason="版本换代")
    resp = client.post(f"/api/v1/books/{ABBR}-b01/fetch")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "BOOK_RETIRED"
    assert client.post("/api/v1/books/nope-b01/fetch").status_code == 404


# ---------------- 教程级 fetch（批量取书） ----------------


def test_knowledge_fetch_processes_all_decided_books(tmp_path, repo, monkeypatch):
    pdf = _passing_pdf_bytes()
    knowledge_id = _adopt(
        repo, "1",
        textbook=[_ref(f"{ABBR}-b01", "微积分学教程"), _ref(f"{ABBR}-b02", "微积分学教程 下册")],
        exercise=[_ref(f"{ABBR}-b03", "习题集", roles=["exercises"])],
        parallel=[_ref(f"{ABBR}-b04", "平行读物", roles=["textbook"])],
    )
    provider = FakeProvider(by_query={
        "微积分学教程": [_make_candidate("微积分学教程", pid="fake-1")],
        "微积分学教程 下册": [_make_candidate("微积分学教程 下册", pid="fake-2")],
        "习题集": [_make_candidate("习题集", pid="fake-3")],
    })
    with _fetch_client(tmp_path, repo, provider, pdf, monkeypatch) as fetch_client:
        resp = fetch_client.post(f"/api/v1/knowledge/{knowledge_id}/fetch")
        assert resp.status_code == 202
        assert resp.json()["knowledge_id"] == knowledge_id
        record = _wait(fetch_client, resp.json()["task_id"])
        assert record["status"] == "succeeded", record
        result = record["result"]
        assert result["ok"] is True and result["failed_count"] == 0
        assert result["include_parallel"] is False
        by_book = {item["book_id"]: item for item in result["processed"]}
        # parallel 未纳入：仅 textbook+exercise 三本
        assert set(by_book) == {f"{ABBR}-b01", f"{ABBR}-b02", f"{ABBR}-b03"}
        assert all(item["ok"] for item in by_book.values())
    for book_id in (f"{ABBR}-b01", f"{ABBR}-b02", f"{ABBR}-b03"):
        assert repo.get_book(book_id).holding == "owned"
    assert repo.get_book(f"{ABBR}-b04").holding == "missing"


def test_knowledge_fetch_include_parallel_and_unknown_404(tmp_path, repo, monkeypatch):
    knowledge_id = _adopt(repo, "1", textbook=[_ref(f"{ABBR}-b01", "微积分学教程")],
                          parallel=[_ref(f"{ABBR}-b04", "平行读物", roles=["textbook"])])
    provider = FakeProvider(by_query={
        "微积分学教程 菲赫金哥尔茨": [_make_candidate("微积分学教程", pid="fake-1")],
        "平行读物 菲赫金哥尔茨": [_make_candidate("平行读物", pid="fake-4")],
    })
    with _fetch_client(tmp_path, repo, provider, _passing_pdf_bytes(), monkeypatch) as fetch_client:
        assert fetch_client.post("/api/v1/knowledge/kt-none-9/fetch").status_code == 404
        # 默认不含 parallel：仅处理 textbook 书
        resp = fetch_client.post(f"/api/v1/knowledge/{knowledge_id}/fetch")
        record = _wait(fetch_client, resp.json()["task_id"])
        assert record["status"] == "succeeded", record
        by_book = {item["book_id"] for item in record["result"]["processed"]}
        assert by_book == {f"{ABBR}-b01"}
        assert "平行读物" not in " ".join(provider.queries)
        # include_parallel=true 显式纳入：平行读物被取回（b01 已 owned 跳过）
        resp2 = fetch_client.post(f"/api/v1/knowledge/{knowledge_id}/fetch",
                                  json={"include_parallel": True})
        record2 = _wait(fetch_client, resp2.json()["task_id"])
        assert record2["status"] == "succeeded", record2
        assert record2["result"]["include_parallel"] is True
        by_book2 = {item["book_id"] for item in record2["result"]["processed"]}
        assert by_book2 == {f"{ABBR}-b01", f"{ABBR}-b04"}
        assert repo.get_book(f"{ABBR}-b04").holding == "owned"


# ---------------- 并发防护（同书/同教程活动任务查重：409） ----------------


def test_book_fetch_concurrent_dedup_409(tmp_path, repo):
    repo.create_book(f"{ABBR}-b01", title="微积分学教程")
    started, release = threading.Event(), threading.Event()
    with _blocking_client(tmp_path, repo, "book_download", started, release) as fetch_client:
        first = fetch_client.post(f"/api/v1/books/{ABBR}-b01/fetch")
        assert first.status_code == 202
        assert started.wait(timeout=5)
        second = fetch_client.post(f"/api/v1/books/{ABBR}-b01/fetch")
        assert second.status_code == 409
        assert second.json()["detail"]["code"] == "TASK_ALREADY_RUNNING"
        # 不同书不受影响
        repo.create_book(f"{ABBR}-b02", title="数学分析原理")
        other = fetch_client.post(f"/api/v1/books/{ABBR}-b02/fetch")
        assert other.status_code == 202
        release.set()
        assert _wait(fetch_client, first.json()["task_id"])["status"] == "succeeded"
        # 已结束任务不阻塞重新提交
        again = fetch_client.post(f"/api/v1/books/{ABBR}-b01/fetch")
        assert again.status_code == 202
        assert _wait(fetch_client, again.json()["task_id"])["status"] == "succeeded"


def test_knowledge_fetch_concurrent_dedup_409(tmp_path, repo):
    knowledge_id = _adopt(repo, "1", textbook=[_ref(f"{ABBR}-b01", "微积分学教程")])
    started, release = threading.Event(), threading.Event()
    with _blocking_client(tmp_path, repo, "tutorial_fetch", started, release) as fetch_client:
        first = fetch_client.post(f"/api/v1/knowledge/{knowledge_id}/fetch")
        assert first.status_code == 202
        assert started.wait(timeout=5)
        second = fetch_client.post(f"/api/v1/knowledge/{knowledge_id}/fetch")
        assert second.status_code == 409
        assert second.json()["detail"]["code"] == "TASK_ALREADY_RUNNING"
        release.set()
        assert _wait(fetch_client, first.json()["task_id"])["status"] == "succeeded"
