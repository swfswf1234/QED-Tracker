"""QED-068 B 步 B-6/B-7：`kind=paper` 书行的取书分叉。

论文标识是 arXiv ID，不走「按书名在图书渠道检索」的五阶段编排；分叉后仍复用同一条
预算下载 → staging 机器验收 → promote → 五层态迁移与内容身份登记链。
默认测试零公网：arXiv 来源与下载器都是注入的假实现（MockTransport）。
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.application.book_fetch import BookFetchError, BookFetchService
from qed_tracker.application.books import BookService
from qed_tracker.application.resources import ResourceService
from qed_tracker.db.knowledge_repository import KnowledgeRepository
from qed_tracker.db.models import Base, QedDomain
from qed_tracker.downloader import DownloadManager
from qed_tracker.models import Availability, Candidate

DOMAIN_ID = "math-advanced"
ARXIV_ID = "2601.00001"
PDF_URL = f"https://arxiv.org/pdf/{ARXIV_ID}"


class FakeBookProvider:
    """图书渠道假提供者：论文分叉**不得**调用它的 search。"""

    def __init__(self):
        self.name = "fake_library"
        self.queries: list[str] = []

    def search(self, query, limit=10):
        self.queries.append(query)
        return []

    def resolve(self, candidate):
        return candidate

    def close(self):
        return None


class FakeArxivSource:
    def __init__(self, candidate: Candidate | None = None, error: Exception | None = None):
        self.candidate = candidate
        self.error = error
        self.requested: list[str] = []

    def get(self, identifier: str) -> Candidate:
        self.requested.append(identifier)
        if self.error is not None:
            raise self.error
        assert self.candidate is not None
        return self.candidate

    def close(self):
        return None


def paper_candidate() -> Candidate:
    return Candidate(
        "arxiv", ARXIV_ID, "Series Convergence Criteria", ("Ada",), "en", "2026",
        page_url=f"https://arxiv.org/abs/{ARXIV_ID}", download_url=PDF_URL,
        identifiers={"arxiv": ARXIV_ID}, availability=Availability.DOWNLOADABLE,
    )


@pytest.fixture
def repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paperfetch.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    from qed_tracker.db.engine import utc_now

    now = utc_now()
    with factory() as session:
        session.add(QedDomain(domain_id=DOMAIN_ID, name="高等数学", description="级数",
                              stages=["本科基础"], exploration_stage="已完成", created_at=now, updated_at=now))
        session.commit()
    yield KnowledgeRepository(lambda: factory())
    engine.dispose()


def build_service(repo, *, paper_provider, data_root, handler=None, book_providers=()):
    def factory():
        manager = DownloadManager(retries=1)
        manager.client.close()
        manager.client = httpx.Client(
            transport=httpx.MockTransport(handler or (lambda request: httpx.Response(200, content=b"", request=request)))
        )
        return BookService(list(book_providers), ResourceService(data_root, manager, books=repo))

    return BookFetchService(
        repo, factory, data_root=data_root, candidate_budget=5.0, min_pages=1, min_size_bytes=1,
        llm_query=False, llm_confirm=False, paper_provider=paper_provider,
    )


def adopted_book(repo, **overrides):
    params = {
        "domain_id": DOMAIN_ID, "arxiv_id": ARXIV_ID, "title": "Series Convergence Criteria",
        "authors": ["Ada"], "year": 2026, "page_url": f"https://arxiv.org/abs/{ARXIV_ID}",
        "download_url": PDF_URL,
    }
    params.update(overrides)
    return repo.adopt_paper(**params)["book_id"]


# ---------------- 黄金路径 ----------------


def test_paper_fetch_lands_in_domain_papers_year_bucket_and_skips_book_search(repo, pdf_bytes, tmp_path):
    """分叉判据：只按 arXiv ID 取文件、落 `raw/<domain>/_general/papers/<year>/`、书名检索零调用。"""
    book_provider = FakeBookProvider()
    source = FakeArxivSource(paper_candidate())
    service = build_service(
        repo, paper_provider=source, data_root=tmp_path, book_providers=[book_provider],
        handler=lambda request: httpx.Response(200, content=pdf_bytes, request=request),
    )
    book_id = adopted_book(repo)
    outcome = service.fetch(book_id)

    assert outcome["ok"] is True and outcome["skipped"] is False
    assert source.requested == [ARXIV_ID]
    assert book_provider.queries == []
    relative = outcome["file_path"]
    assert relative.startswith(f"raw/{DOMAIN_ID}/_general/papers/2026/{ARXIV_ID}_")
    assert relative.endswith(".pdf")
    assert (tmp_path / relative).exists()

    book = repo.get_book(book_id)
    assert book.status == "downloaded" and book.holding == "owned"
    assert book.sha256 and book.size_bytes and book.page_count
    channels = [(item.channel, item.ok) for item in repo.list_sources(book_id)]
    assert ("arxiv", True) in channels


def test_owned_paper_fetch_is_noop(repo, pdf_bytes, tmp_path):
    source = FakeArxivSource(paper_candidate())
    service = build_service(
        repo, paper_provider=source, data_root=tmp_path,
        handler=lambda request: httpx.Response(200, content=pdf_bytes, request=request),
    )
    book_id = adopted_book(repo)
    service.fetch(book_id)
    again = service.fetch(book_id)
    assert again["skipped"] is True
    assert source.requested == [ARXIV_ID]


# ---------------- 缺件与失败 ----------------


def test_paper_fetch_without_arxiv_source_fails_before_state_change(repo, tmp_path):
    service = build_service(repo, paper_provider=None, data_root=tmp_path)
    book_id = adopted_book(repo)
    with pytest.raises(BookFetchError, match="arXiv"):
        service.fetch(book_id)
    assert repo.get_book(book_id).status == "decided"


def test_paper_fetch_without_arxiv_identity_reports_error(repo, tmp_path):
    """书行没有 channel=arxiv 的内容身份 → 明确报错，不拿标题去图书渠道碰运气。"""
    book_provider = FakeBookProvider()
    service = build_service(
        repo, paper_provider=FakeArxivSource(paper_candidate()), data_root=tmp_path,
        book_providers=[book_provider],
    )
    book = repo.create_book("mathadvanced-b90", title="无身份论文", authors=[{"name": "Ada", "role": "author"}],
                            language="en", domain_id=DOMAIN_ID, kind="paper", year=2026)
    with pytest.raises(BookFetchError, match="身份"):
        service.fetch(book.book_id)
    assert book_provider.queries == []
    assert repo.get_book(book.book_id).status != "downloading"


def test_paper_fetch_without_domain_is_rejected(repo, tmp_path, pdf_bytes):
    """B-7/⑤′：论文没有默认桶——领域缺失的书行拒绝落盘，不落 raw/math/。"""
    book = repo.create_book("mathadvanced-b91", title="无领域论文", authors=[], language="en",
                            domain_id="", kind="paper", year=2026)
    repo.add_source(book.book_id, channel="arxiv", provider_id=ARXIV_ID, download_url=PDF_URL, ok=False)
    service = build_service(
        repo, paper_provider=FakeArxivSource(paper_candidate()), data_root=tmp_path,
        handler=lambda request: httpx.Response(200, content=pdf_bytes, request=request),
    )
    with pytest.raises(BookFetchError, match="领域"):
        service.fetch(book.book_id)
    assert not (tmp_path / "raw" / "math").exists()


def test_paper_download_failure_marks_book_failed_and_leaves_trace(repo, tmp_path):
    service = build_service(
        repo, paper_provider=FakeArxivSource(paper_candidate()), data_root=tmp_path,
        handler=lambda request: httpx.Response(500, request=request),
    )
    book_id = adopted_book(repo)
    with pytest.raises(BookFetchError, match="论文取书失败"):
        service.fetch(book_id)
    assert repo.get_book(book_id).status == "failed"
    assert [item.ok for item in repo.list_sources(book_id) if item.channel == "arxiv"] == [False, False]


def test_paper_source_resolution_error_is_wrapped(repo, tmp_path):
    service = build_service(
        repo, paper_provider=FakeArxivSource(error=RuntimeError("arXiv 接口不可达")), data_root=tmp_path,
    )
    book_id = adopted_book(repo)
    with pytest.raises(BookFetchError):
        service.fetch(book_id)
    assert repo.get_book(book_id).status != "downloading"


# ---------------- 查重双报（QED-068 C 步 / 068-4） ----------------


SECOND_ID = "2601.00002"
SAME_TITLE = "Series Convergence Criteria"


def second_candidate() -> Candidate:
    return Candidate(
        "arxiv", SECOND_ID, SAME_TITLE, ("Ada",), "en", "2026",
        page_url=f"https://arxiv.org/abs/{SECOND_ID}", download_url=f"https://arxiv.org/pdf/{SECOND_ID}",
        identifiers={"arxiv": SECOND_ID}, availability=Availability.DOWNLOADABLE,
    )


def test_same_name_conflict_reported_and_existing_row_untouched(repo, tmp_path, pdf_bytes, text_pdf_bytes):
    """计划命名用例：同标题不同 arXiv ID 且内容不同 → 只出冲突清单，不自动覆盖既有行与文件。"""
    first_id = adopted_book(repo)
    service = build_service(
        repo, paper_provider=FakeArxivSource(paper_candidate()), data_root=tmp_path,
        handler=lambda request: httpx.Response(200, content=pdf_bytes, request=request),
    )
    first = service.fetch(first_id)

    second_id = adopted_book(repo, arxiv_id=SECOND_ID, title=SAME_TITLE)
    service2 = build_service(
        repo, paper_provider=FakeArxivSource(second_candidate()), data_root=tmp_path,
        handler=lambda request: httpx.Response(200, content=text_pdf_bytes("Second paper body"), request=request),
    )
    second = service2.fetch(second_id)

    assert second["ok"] is True
    names = second["duplicates"]["same_name"]
    assert [item["book_id"] for item in names] == [first_id]
    assert names[0]["sha256"] == first["resource_id"].removeprefix("sha256:")
    assert second["duplicates"]["same_content"] == []
    # 既有行与既有文件一律不动，本次成品独立落盘（内容指纹命名）
    assert repo.get_book(first_id).sha256 == first["resource_id"].removeprefix("sha256:")
    assert (tmp_path / first["file_path"]).is_file()
    assert (tmp_path / second["file_path"]).is_file()
    assert second["file_path"] != first["file_path"]
    assert first["duplicates"] == {"same_content": [], "same_name": []}


def test_same_content_paper_hit_is_reported_without_reuse(repo, tmp_path, pdf_bytes):
    """论文面 same_content 只报不复用：登记原语的跨行复用条件＝kind=book（D2/D14）。"""
    first_id = adopted_book(repo)
    service = build_service(
        repo, paper_provider=FakeArxivSource(paper_candidate()), data_root=tmp_path,
        handler=lambda request: httpx.Response(200, content=pdf_bytes, request=request),
    )
    first = service.fetch(first_id)

    second_id = adopted_book(repo, arxiv_id=SECOND_ID, title="Unrelated Title")
    service2 = build_service(
        repo, paper_provider=FakeArxivSource(second_candidate()), data_root=tmp_path,
        handler=lambda request: httpx.Response(200, content=pdf_bytes, request=request),
    )
    second = service2.fetch(second_id)

    assert [item["book_id"] for item in second["duplicates"]["same_content"]] == [first_id]
    assert second["duplicates"]["same_name"] == []
    assert second["file_path"] != first["file_path"]
    assert (tmp_path / second["file_path"]).is_file() and (tmp_path / first["file_path"]).is_file()
