"""BookFetchService 定向测试：搜索→逐候选限时下载→状态转移与渠道留痕。

默认测试不得访问公网：提供者为假实现，下载走 MockTransport；
超时语义用 attempt_timeout 注入（秒级），不等待真实 600s。
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


def build_service(repo, providers, handler, *, attempt_timeout: float = 5.0, data_root):
    def factory():
        downloader = mock_downloader(handler)
        return BookService(list(providers), ResourceService(Inventory(data_root), downloader))

    return BookFetchService(repo, factory, data_root=data_root, attempt_timeout=attempt_timeout)


def static_handler(pdf: bytes):
    return lambda request: httpx.Response(200, content=pdf, request=request)


# ---------------- 夹具 ----------------


@pytest.fixture
def repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fetch.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    from qed_tracker.database import utc_now

    now = utc_now()
    session.add(QedDomain(domain_id="math", name="数学", description="d", stages=["基础"],
                          created_at=now, updated_at=now))
    session.add(QedCourse(course_id="01_math_analysis", domain_id="math", sort_order=1, name="数学分析",
                          aliases=[], stage="基础", prerequisites=[], related_targets=[],
                          created_at=now, updated_at=now))
    session.commit()
    yield KnowledgeRepository(lambda: factory())
    engine.dispose()


@pytest.fixture
def seeded_book(repo):
    knowledge = repo.create_knowledge(
        domain_id="math", course_id="01_math_analysis", kind="tutorial", set_no="1", name="教程1：测试",
    )
    repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref={"title": "测试书"})
    return repo.create_book(knowledge.knowledge_id, kind="textbook", roles=["textbook"],
                            title="测试书", authors=["Author"])


# ---------------- 测试 ----------------


def test_fetch_success_first_candidate(repo, seeded_book, pdf_bytes, tmp_path):
    """首候选可下载 → downloaded + 渠道留痕 ok=True。"""
    provider = FakeProvider("fake", [make_candidate("fake", "测试书")])
    service = build_service(repo, [provider], static_handler(pdf_bytes), data_root=tmp_path)
    outcome = service.fetch(seeded_book.book_id)
    assert outcome["ok"] is True
    assert outcome["status"] == "downloaded"
    assert outcome["relative_path"]
    book = repo.get_book(seeded_book.book_id, include_hidden=True)
    assert book.status == "downloaded"
    sources = repo.list_sources(seeded_book.book_id)
    assert len(sources) == 1
    assert sources[0].ok is True
    assert sources[0].channel == "fake"


def test_fetch_query_uses_title_and_authors(repo, seeded_book, tmp_path):
    """检索词用书籍 title+authors，不用 knowledge.name 的展示名。"""
    provider = FakeProvider("fake", [])
    service = build_service(repo, [provider], static_handler(b""), data_root=tmp_path)
    with pytest.raises(BookFetchError):
        service.fetch(seeded_book.book_id)
    assert provider.queries == ["测试书 Author"]


def _seed_with_ref(repo, *, ref: dict):
    """自建 knowledge+book（可自定义 textbook_ref，避免 confirm 二次转移）。"""
    knowledge = repo.create_knowledge(
        domain_id="math", course_id="01_math_analysis", kind="tutorial", set_no="9", name="教程9：引用测试",
    )
    repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref=ref)
    return repo.create_book(knowledge.knowledge_id, kind="textbook", roles=["textbook"],
                            title="测试书", authors=["Author"])


def test_fetch_prefers_original_title(repo, pdf_bytes, tmp_path):
    """决策引用含 original_title（英文原名）时优先检索，命中即止。"""
    book = _seed_with_ref(repo, ref={"title": "测试书", "original_title": "Calculus"})
    provider = FakeProvider("fake", [make_candidate("fake", "Calculus")])
    service = build_service(repo, [provider], static_handler(pdf_bytes), data_root=tmp_path)
    outcome = service.fetch(book.book_id)
    assert outcome["ok"] is True
    assert provider.queries == ["Calculus Author"]  # 英文命中后不再用中文书名搜索


def test_fetch_falls_back_to_chinese_title(repo, pdf_bytes, tmp_path):
    """英文原名无候选 → 回退中文书名检索。"""

    class SelectiveProvider(FakeProvider):
        def search(self, query, limit=10):
            self.queries.append(query)
            if query.startswith("Calculus"):
                return []
            return [make_candidate("fake", "测试书")]

    book = _seed_with_ref(repo, ref={"title": "测试书", "original_title": "Calculus"})
    provider = SelectiveProvider("fake")
    service = build_service(repo, [provider], static_handler(pdf_bytes), data_root=tmp_path)
    outcome = service.fetch(book.book_id)
    assert outcome["ok"] is True
    assert provider.queries == ["Calculus Author", "测试书 Author"]


def test_fetch_timeout_switches_to_next_candidate(repo, seeded_book, pdf_bytes, tmp_path):
    """首候选预算内无响应 → 记失败并切换下一候选。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if "slow" in str(request.url):
            time.sleep(0.5)
            return httpx.Response(200, content=pdf_bytes, request=request)
        return httpx.Response(200, content=pdf_bytes, request=request)

    slow = FakeProvider("slow", [make_candidate("slow", "测试书")])
    fast = FakeProvider("fast", [make_candidate("fast", "测试书")])
    service = build_service(repo, [slow, fast], handler, attempt_timeout=0.1, data_root=tmp_path)
    outcome = service.fetch(seeded_book.book_id)
    assert outcome["ok"] is True
    attempts = {a["provider"]: a for a in outcome["attempts"]}
    assert "超时" in attempts["slow"]["note"]
    assert attempts["fast"]["ok"] is True
    book = repo.get_book(seeded_book.book_id, include_hidden=True)
    assert book.status == "downloaded"


def test_fetch_all_fail_marks_failed(repo, seeded_book, tmp_path):
    """可下载候选下载失败（HTTP 500）→ 书籍 failed + 全部渠道 ok=False。"""
    provider = FakeProvider("broken", [make_candidate("broken", "测试书")])
    service = build_service(
        repo, [provider], lambda request: httpx.Response(500, request=request), data_root=tmp_path
    )
    with pytest.raises(BookFetchError) as exc_info:
        service.fetch(seeded_book.book_id)
    assert "broken" in str(exc_info.value)
    book = repo.get_book(seeded_book.book_id, include_hidden=True)
    assert book.status == "failed"
    sources = repo.list_sources(seeded_book.book_id)
    assert sources and all(source.ok is False for source in sources)


def test_fetch_no_downloadable_candidates(repo, seeded_book, tmp_path):
    """只有 metadata_only 候选 → failed + 人工链接指引。"""
    provider = FakeProvider("libgen_li", [make_candidate("libgen_li", "测试书", downloadable=False)])
    service = build_service(repo, [provider], static_handler(b""), data_root=tmp_path)
    with pytest.raises(BookFetchError) as exc_info:
        service.fetch(seeded_book.book_id)
    assert "libgen.example" in str(exc_info.value)
    book = repo.get_book(seeded_book.book_id, include_hidden=True)
    assert book.status == "failed"


def test_fetch_rejects_stuck_downloading_book(repo, seeded_book, tmp_path):
    """downloading 卡住的书不可直接 fetch（需先 cancel 复位到 decided）。"""
    repo.decide_book(seeded_book.book_id)
    repo.start_download(seeded_book.book_id)
    service = build_service(repo, [FakeProvider("fake", [])], static_handler(b""), data_root=tmp_path)
    with pytest.raises(ValueError, match="candidate/decided/failed"):
        service.fetch(seeded_book.book_id)


def test_fetch_candidate_flow_decides_and_starts(repo, seeded_book, pdf_bytes, tmp_path):
    """candidate 状态直接 fetch：自动 decide → start → downloaded。"""
    provider = FakeProvider("fake", [make_candidate("fake", "测试书")])
    service = build_service(repo, [provider], static_handler(pdf_bytes), data_root=tmp_path)
    outcome = service.fetch(seeded_book.book_id)
    assert outcome["ok"] is True
    book = repo.get_book(seeded_book.book_id, include_hidden=True)
    assert book.decided_at is not None
    assert book.downloaded_at is not None


def test_cancel_download_resets_to_decided(repo, seeded_book):
    """cancel_download：downloading → decided，留痕 review_note。"""
    repo.decide_book(seeded_book.book_id)
    repo.start_download(seeded_book.book_id)
    book = repo.cancel_download(seeded_book.book_id, note="失联复位", by="web")
    assert book.status == "decided"
    assert book.review_note == "失联复位"
    # 复位后可重新 start（decided → downloading）
    assert repo.start_download(seeded_book.book_id).status == "downloading"
