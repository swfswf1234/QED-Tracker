import httpx
import pytest

from qed_tracker.models import Availability
from qed_tracker.providers.books import (
    GoogleBooksProvider,
    InternetArchiveProvider,
    OpenLibraryProvider,
    create_book_providers,
)


def _replace_client(provider, handler):
    provider.client.close()
    provider.client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_open_library_marks_records_without_archive_id_as_metadata_only():
    payload = {"docs": [{"title": "Book", "author_name": ["Author"], "ia": []}]}
    provider = OpenLibraryProvider()
    _replace_client(provider, lambda request: httpx.Response(200, json=payload, request=request))
    try:
        result = provider.search("Book", 5)[0]
    finally:
        provider.close()
    assert result.availability == Availability.METADATA_ONLY


def test_google_books_exposes_only_real_pdf_download_links():
    payload = {"items": [
        {"id": "a", "volumeInfo": {"title": "Downloadable", "authors": ["A"]}, "accessInfo": {"pdf": {"downloadLink": "https://example.test/a.pdf"}}},
        {"id": "b", "volumeInfo": {"title": "Preview"}, "accessInfo": {"pdf": {}}},
    ]}
    provider = GoogleBooksProvider()
    _replace_client(provider, lambda request: httpx.Response(200, json=payload, request=request))
    try:
        results = provider.search("Book", 5)
    finally:
        provider.close()
    assert results[0].availability == Availability.DOWNLOADABLE
    assert results[1].availability == Availability.METADATA_ONLY


def test_internet_archive_resolves_largest_public_pdf():
    def handler(request):
        if request.url.path.startswith("/advancedsearch"):
            return httpx.Response(200, json={"response": {"docs": [{"identifier": "book-1", "title": "Book"}]}}, request=request)
        return httpx.Response(200, json={"files": [
            {"name": "small.pdf", "size": "10"},
            {"name": "large file.pdf", "size": "20"},
            {"name": "private.pdf", "size": "30", "private": True},
        ]}, request=request)

    provider = InternetArchiveProvider()
    _replace_client(provider, handler)
    try:
        resolved = provider.resolve(provider.search("Book", 5)[0])
    finally:
        provider.close()
    assert resolved.download_url.endswith("large%20file.pdf")
    assert resolved.size_bytes == 20


def test_internet_archive_multiword_query_searches_all_fields():
    """archive.org Solr 的 `title:(a b c)` 对多词查询返回 0；必须全字段 AND 连接。"""

    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"response": {"docs": []}}, request=request)

    provider = InternetArchiveProvider()
    _replace_client(provider, handler)
    try:
        provider.search("Munkres Topology 2nd", 8)
    finally:
        provider.close()
    q = httpx.URL(captured["url"]).params["q"]
    assert "mediatype:texts" in q
    assert not q.startswith("title:("), f"多词查询不得用 title:(...) 限定：{q}"
    assert "Munkres" in q and "Topology" in q


def test_retired_provider_has_actionable_migration_error():
    with pytest.raises(ValueError, match=r"0\.5.*core.*sources"):
        create_book_providers(("libgen",))
