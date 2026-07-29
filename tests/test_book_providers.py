import httpx

from qed_tracker.models import Availability
from qed_tracker.providers.books import (
    AnnasArchiveProvider,
    GoogleBooksProvider,
    InternetArchiveProvider,
    LibgenProvider,
    OpenLibraryProvider,
    ZLibraryProvider,
)


def _replace_client(provider, handler):
    provider.client.close()
    provider.client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_libgen_normalizes_pdf_results():
    cells = ["Topology", "Munkres", "Publisher", "2000", "English", "x", "10 MB", "pdf", '<a href="/ads.php?md5=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa">GET</a>']
    html = '<table class="c"><tr>' + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr></table>"
    provider = LibgenProvider()
    _replace_client(provider, lambda request: httpx.Response(200, text=html, request=request))
    try:
        results = provider.search("Topology", 5)
    finally:
        provider.close()
    assert len(results) == 1
    assert results[0].title == "Topology"
    assert results[0].authors == ("Munkres",)
    assert results[0].size_bytes == 10 * 1024 * 1024


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


def test_annas_archive_search_and_resolve():
    search_html = '<a href="/md5/abc123">Analysis Book</a>'
    detail_html = '<a href="https://files.example.test/book.pdf">Download</a>'

    def handler(request):
        return httpx.Response(200, text=search_html if request.url.path == "/search" else detail_html, request=request)

    provider = AnnasArchiveProvider()
    _replace_client(provider, handler)
    try:
        resolved = provider.resolve(provider.search("Analysis", 5)[0])
    finally:
        provider.close()
    assert resolved.download_url == "https://files.example.test/book.pdf"


def test_zlibrary_search_and_resolve():
    search_html = '<a href="/book/42">Algebra Book</a>'
    detail_html = '<a href="/download/42.pdf">Download</a>'

    def handler(request):
        return httpx.Response(200, text=search_html if request.url.path == "/s/" else detail_html, request=request)

    provider = ZLibraryProvider()
    _replace_client(provider, handler)
    try:
        resolved = provider.resolve(provider.search("Algebra", 5)[0])
    finally:
        provider.close()
    assert resolved.download_url == "https://singlelogin.re/download/42.pdf"
