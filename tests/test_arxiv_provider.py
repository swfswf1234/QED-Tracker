from datetime import UTC, datetime
from types import SimpleNamespace

import arxiv

from qed_tracker.providers.arxiv import ArxivProvider


class _FakeClient:
    def __init__(self, results):
        self._results = list(results)
        self.searches = []

    def results(self, search):
        self.searches.append(search)
        return iter(self._results)


def _item(index: int):
    return SimpleNamespace(
        entry_id=f"https://arxiv.org/abs/2401.0000{index}",
        title=f"Paper {index}",
        authors=[SimpleNamespace(name="Ada")],
        published=datetime(2024, 1, 2, tzinfo=UTC),
        updated=datetime(2024, 1, 3, tzinfo=UTC),
        categories=["cs.CL"],
        pdf_url=f"https://arxiv.org/pdf/2401.0000{index}",
        summary="abstract",
    )


def _provider_with(count: int) -> tuple[ArxivProvider, _FakeClient]:
    provider = ArxivProvider()
    client = _FakeClient([_item(index) for index in range(1, count + 1)])
    provider.client = client
    return provider, client


def test_search_terms_defaults_to_date_sort():
    provider, client = _provider_with(3)
    provider.search_terms(("spectral gap",), category="math.SP", limit=3)
    search = client.searches[0]
    assert search.sort_by == arxiv.SortCriterion.SubmittedDate
    assert search.max_results == 3


def test_search_terms_sort_by_relevance():
    provider, client = _provider_with(3)
    provider.search_terms(("spectral gap",), category="math.SP", limit=3, sort_by="relevance")
    search = client.searches[0]
    assert search.sort_by == arxiv.SortCriterion.Relevance
    assert search.sort_order == arxiv.SortOrder.Descending


def test_search_sort_by_relevance():
    provider, client = _provider_with(2)
    provider.search("transformers", limit=2, sort_by="relevance")
    assert client.searches[0].sort_by == arxiv.SortCriterion.Relevance


def test_overfetch_doubles_requested_count():
    provider, client = _provider_with(20)
    results = provider.search_terms(("spectral gap",), category="math.SP", limit=10, overfetch=True)
    assert client.searches[0].max_results == 20
    # 过量抓取返回整池，截断由调用方在年份过滤后执行（QED-068-1）。
    assert len(results) == 20


def test_relevance_sort_without_overfetch_keeps_limit():
    provider, client = _provider_with(5)
    provider.search_terms(("spectral gap",), category="math.SP", limit=5, sort_by="relevance")
    assert client.searches[0].max_results == 5


def test_overfetch_caps_at_30():
    provider, client = _provider_with(30)
    provider.search_terms(("spectral gap",), category="math.SP", limit=25, overfetch=True)
    assert client.searches[0].max_results == 30


def test_overfetch_disabled_keeps_limit():
    provider, client = _provider_with(10)
    results = provider.search_terms(("spectral gap",), category="math.SP", limit=10)
    assert client.searches[0].max_results == 10
    assert len(results) == 10


def test_arxiv_result_is_normalized_to_candidate():
    item = SimpleNamespace(
        entry_id="https://arxiv.org/abs/2401.00001",
        title="  A   Paper\nTitle ",
        authors=[SimpleNamespace(name="Ada"), SimpleNamespace(name="Emmy")],
        published=datetime(2024, 1, 2, tzinfo=UTC),
        updated=datetime(2024, 1, 3, tzinfo=UTC),
        categories=["cs.CL", "cs.LG"],
        pdf_url="https://arxiv.org/pdf/2401.00001",
        summary="An\nabstract",
    )
    candidate = ArxivProvider._candidate(item)
    assert candidate.provider_id == "2401.00001"
    assert candidate.title == "A Paper Title"
    assert candidate.authors == ("Ada", "Emmy")
    assert candidate.identifiers == {"arxiv": "2401.00001"}
    assert candidate.subjects == ("cs.CL", "cs.LG")
    assert candidate.updated_at.startswith("2024-01-03")
