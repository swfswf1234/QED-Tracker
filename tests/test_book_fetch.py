"""BookFetchService 定向测试：五阶段取书、状态机（QED-060）与落盘域。

默认测试不得访问公网：提供者为假实现，下载走 MockTransport；
候选级预算用注入的小值（秒级），不等待真实 300s。机器验收门在测试中放宽为
1 页/1 字节（`pdf_bytes` 为单页小 PDF）。
"""

from __future__ import annotations

import time

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.application.book_fetch import BookFetchError, BookFetchService
from qed_tracker.application.books import BookService
from qed_tracker.application.resources import ResourceService
from qed_tracker.db.knowledge_repository import KnowledgeRepository
from qed_tracker.db.models import Base, QedCourse, QedDomain
from qed_tracker.downloader import DownloadManager
from qed_tracker.inventory import Inventory
from qed_tracker.models import Availability, Candidate, DownloadLink

# ---------------- 假提供者与下载器 ----------------


class FakeProvider:
    def __init__(self, name: str, candidates: list[Candidate] | None = None, error: Exception | None = None):
        self.name = name
        self.candidates = candidates or []
        self.error = error
        self.queries: list[str] = []

    def search(self, query, limit=10):
        self.queries.append(query)
        if self.error:
            raise self.error
        return list(self.candidates)

    def resolve(self, candidate):
        return candidate

    def close(self):
        return None


def mock_downloader(handler) -> DownloadManager:
    manager = DownloadManager(retries=1)
    manager.client.close()
    manager.client = httpx.Client(transport=httpx.MockTransport(handler))
    return manager


def make_candidate(provider: str, title: str, *, downloadable: bool = True) -> Candidate:
    return Candidate(
        provider,
        f"{provider}-1",
        title,
        ("Author",),
        "zh",
        year="2024",
        download_url=f"https://example.com/{provider}.pdf" if downloadable else "",
        availability=Availability.DOWNLOADABLE if downloadable else Availability.METADATA_ONLY,
        links=() if downloadable else (DownloadLink(label="mirrors", url=f"https://libgen.example/{provider}"),),
    )


def build_service(repo, providers, handler, *, candidate_budget: float = 5.0, data_root):
    def factory():
        downloader = mock_downloader(handler)
        return BookService(list(providers), ResourceService(Inventory(data_root), downloader))

    return BookFetchService(
        repo, factory, data_root=data_root, candidate_budget=candidate_budget,
        min_pages=1, min_size_bytes=1, llm_query=False, llm_confirm=False,
    )


def static_handler(pdf: bytes):
    return lambda request: httpx.Response(200, content=pdf, request=request)


def _author(name: str = "Author") -> list[dict]:
    return [{"name": name, "role": "author"}]


# ---------------- 夹具 ----------------


@pytest.fixture
def repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fetch.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    from qed_tracker.db.engine import utc_now

    now = utc_now()
    session.add(QedDomain(domain_id="math-advanced", name="数学（高等数学）", description="d",
                          stages=["基础", "主干", "分支", "前沿"], created_at=now, updated_at=now))
    session.add(QedCourse(course_id="math_analysis", domain_id="math-advanced", sort_order=1, name="数学分析",
                          aliases=[], stage="基础", prerequisites=[], related_targets=[],
                          created_at=now, updated_at=now))
    session.commit()
    yield KnowledgeRepository(lambda: factory())
    engine.dispose()


@pytest.fixture
def seeded_book(repo):
    knowledge = repo.create_knowledge(course_id="math_analysis", set_no="1", name="教程1：测试")
    book = repo.create_book(
        "mathanalysis-b01", title="测试书", authors=_author(), language="zh", domain_id="math-advanced",
    )
    knowledge.textbook_ref = [{"book_id": book.book_id, "title": book.title}]
    session = repo.session_factory()
    session.merge(knowledge)
    session.commit()
    session.close()
    return book


# ---------------- 测试 ----------------


def test_fetch_success_first_candidate(repo, seeded_book, pdf_bytes, tmp_path):
    """首候选可下载 → holding=owned + status=downloaded + 渠道留痕 ok=True。"""
    provider = FakeProvider("fake", [make_candidate("fake", "测试书")])
    service = build_service(repo, [provider], static_handler(pdf_bytes), data_root=tmp_path)
    outcome = service.fetch(seeded_book.book_id)
    assert outcome["ok"] is True
    assert outcome["file_path"]
    book = repo.get_book(seeded_book.book_id)
    assert book.status == "downloaded"
    assert book.holding == "owned"
    sources = repo.list_sources(seeded_book.book_id)
    assert len(sources) == 1
    assert sources[0].ok is True
    assert sources[0].channel == "fake"


def test_fetch_lands_in_real_domain_course_dir(repo, seeded_book, pdf_bytes, tmp_path):
    """QED-060：落盘用书籍真实 domain_id → raw/math-advanced/math_analysis/。"""
    provider = FakeProvider("fake", [make_candidate("fake", "测试书")])
    service = build_service(repo, [provider], static_handler(pdf_bytes), data_root=tmp_path)
    outcome = service.fetch(seeded_book.book_id)
    assert outcome["file_path"].startswith("raw/math-advanced/math_analysis/")
    assert (tmp_path / "raw" / "math-advanced" / "math_analysis").exists()
    assert not (tmp_path / "raw" / "math").exists()


def test_fetch_query_uses_title_and_authors(repo, seeded_book, tmp_path):
    """检索词用书籍 title+authors，不用 knowledge.name 的展示名。"""
    provider = FakeProvider("fake", [])
    service = build_service(repo, [provider], static_handler(b""), data_root=tmp_path)
    with pytest.raises(BookFetchError):
        service.fetch(seeded_book.book_id)
    assert provider.queries[0] == "测试书 Author"


def test_fetch_timeout_switches_to_next_candidate(repo, seeded_book, pdf_bytes, tmp_path):
    """首候选预算内无响应 → 记失败并切换下一候选。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if "slow" in str(request.url):
            time.sleep(0.5)
        return httpx.Response(200, content=pdf_bytes, request=request)

    slow = FakeProvider("slow", [make_candidate("slow", "测试书")])
    fast = FakeProvider("fast", [make_candidate("fast", "测试书")])
    service = build_service(repo, [slow, fast], handler, candidate_budget=0.1, data_root=tmp_path)
    outcome = service.fetch(seeded_book.book_id)
    assert outcome["ok"] is True
    attempts = {a["provider"]: a for a in outcome["attempts"]}
    assert "超时" in attempts["slow"]["note"]
    assert attempts["fast"]["ok"] is True
    assert repo.get_book(seeded_book.book_id).status == "downloaded"


def test_fetch_all_fail_marks_failed(repo, seeded_book, tmp_path):
    """可下载候选下载失败（HTTP 500）→ status=failed + 全部渠道 ok=False。"""
    provider = FakeProvider("broken", [make_candidate("broken", "测试书")])
    service = build_service(
        repo, [provider], lambda request: httpx.Response(500, request=request), data_root=tmp_path
    )
    with pytest.raises(BookFetchError) as exc_info:
        service.fetch(seeded_book.book_id)
    assert "broken" in str(exc_info.value)
    book = repo.get_book(seeded_book.book_id)
    assert book.status == "failed"
    assert book.holding == "missing"
    sources = repo.list_sources(seeded_book.book_id)
    assert sources and all(source.ok is False for source in sources)


def test_fetch_no_downloadable_candidates(repo, seeded_book, tmp_path):
    """只有 metadata_only 候选 → failed + 人工链接指引。"""
    provider = FakeProvider("libgen_li", [make_candidate("libgen_li", "测试书", downloadable=False)])
    service = build_service(repo, [provider], static_handler(b""), data_root=tmp_path)
    with pytest.raises(BookFetchError) as exc_info:
        service.fetch(seeded_book.book_id)
    assert "libgen.example" in str(exc_info.value)
    assert repo.get_book(seeded_book.book_id).status == "failed"


def test_fetch_rejects_stuck_downloading_book(repo, seeded_book, tmp_path):
    """downloading 卡住的书不可直接 fetch（需先 cancel 复位到 decided）。"""
    repo.decide_book(seeded_book.book_id)
    repo.start_download(seeded_book.book_id)
    service = build_service(repo, [FakeProvider("fake", [])], static_handler(b""), data_root=tmp_path)
    with pytest.raises(ValueError, match="candidate/decided/parallel/failed"):
        service.fetch(seeded_book.book_id)


def test_fetch_candidate_flow_decides_and_starts(repo, seeded_book, pdf_bytes, tmp_path):
    """candidate 状态直接 fetch：自动 decide → start → downloaded。"""
    provider = FakeProvider("fake", [make_candidate("fake", "测试书")])
    service = build_service(repo, [provider], static_handler(pdf_bytes), data_root=tmp_path)
    outcome = service.fetch(seeded_book.book_id)
    assert outcome["ok"] is True
    assert repo.get_book(seeded_book.book_id).status == "downloaded"


def test_cancel_download_resets_to_decided(repo, seeded_book):
    """cancel_download：downloading → decided，可重新 start。"""
    repo.decide_book(seeded_book.book_id)
    repo.start_download(seeded_book.book_id)
    book = repo.cancel_download(seeded_book.book_id)
    assert book.status == "decided"
    assert repo.start_download(seeded_book.book_id).status == "downloading"


def test_fetch_tutorial_continues_after_invalid_status(repo, pdf_bytes, tmp_path):
    """QED-060：教程级批处理遇单本非法状态不整批中断，汇总为该书失败继续下一本。"""
    knowledge = repo.create_knowledge(course_id="math_analysis", set_no="1", name="教程1：批量")
    stuck = repo.create_book("mathanalysis-b01", title="卡住书", authors=_author(), language="zh",
                             domain_id="math-advanced")
    good = repo.create_book("mathanalysis-b02", title="可下书", authors=_author(), language="zh",
                            domain_id="math-advanced")
    knowledge.textbook_ref = [{"book_id": stuck.book_id}, {"book_id": good.book_id}]
    session = repo.session_factory()
    session.merge(knowledge)
    session.commit()
    session.close()
    repo.decide_book(stuck.book_id)
    repo.start_download(stuck.book_id)  # 卡在 downloading

    provider = FakeProvider("fake", [make_candidate("fake", "可下书")])
    service = build_service(repo, [provider], static_handler(pdf_bytes), data_root=tmp_path)
    result = service.fetch_tutorial(knowledge.knowledge_id)
    by_id = {item["book_id"]: item for item in result["processed"]}
    assert result["ok"] is False
    assert by_id[stuck.book_id]["ok"] is False
    assert by_id[good.book_id]["ok"] is True
    assert repo.get_book(good.book_id).status == "downloaded"
