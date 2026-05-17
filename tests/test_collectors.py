"""测试：使用模拟外部 API 的收集器"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.collectors.paper_collector import PaperCollector
from app.tools.libgen_downloader import LibGenDownloader
from app.tools.annas_downloader import AnnaDownloader
from app.collectors.doc_scraper import DocScraper, DOC_SOURCES


class TestPaperCollector:
    def test_search_by_domain_calls_arxiv(self, mocker):
        mock_search = mocker.patch("app.collectors.paper_collector.arxiv_search")
        mock_search.return_value = [
            {"arxiv_id": "2601.00001", "title": "Test Paper", "authors": ["A"], "pdf_url": "https://arxiv.org/pdf/2601.00001"}
        ]
        pc = PaperCollector()
        results = pc.search_by_domain("math.CA", max_results=5)
        mock_search.assert_called_once()
        assert len(results) == 1
        assert results[0]["arxiv_id"] == "2601.00001"

    def test_download_paper_creates_file(self, mocker, tmp_path):
        mock_get = mocker.patch("app.collectors.paper_collector.httpx.get")
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.content = b"%PDF-1.4 mock pdf content"
        mock_get.return_value = mock_response

        pc = PaperCollector()
        paper = {"arxiv_id": "2601.00001", "title": "Test_Paper", "pdf_url": "https://arxiv.org/pdf/2601.00001"}
        path = pc.download_paper(paper, tmp_path)
        assert path is not None
        assert path.exists()
        assert path.read_bytes() == b"%PDF-1.4 mock pdf content"

    def test_download_no_pdf_url(self, tmp_path):
        pc = PaperCollector()
        paper = {"arxiv_id": "2601.00001", "title": "No URL"}
        path = pc.download_paper(paper, tmp_path)
        assert path is None


class TestLibGenDownloader:
    def test_parse_results_empty(self):
        dl = LibGenDownloader()
        results = dl._parse_results("<html></html>")
        assert results == []

    def test_parse_results_with_table(self):
        html = """
        <html><body>
        <table class="c">
        <tr><th>ID</th><th>Author</th><th>Title</th><th>Pub</th><th>Year</th><th>Pages</th><th>Lang</th><th>Size</th><th>Ext</th><th>DL</th></tr>
        <tr><td>1</td><td>Book Author</td><td><a href="book/1">Test Book</a></td>
            <td>Publisher</td><td>2020</td><td>300</td><td>English</td><td>10MB</td>
            <td>PDF</td><td><a href="http://dl.example.com/book.pdf">libgen</a></td></tr>
        </table>
        </body></html>
        """
        dl = LibGenDownloader()
        results = dl._parse_results(html)
        assert len(results) == 1
        assert results[0]["title"] == "Test Book"
        assert results[0]["author"] == "Book Author"
        assert results[0]["language"] == "English"

    def test_parse_skips_non_pdf(self):
        html = """
        <html><body>
        <table class="c">
        <tr><th>ID</th><th>Author</th><th>Title</th><th>Pub</th><th>Year</th><th>Pages</th><th>Lang</th><th>Size</th><th>Ext</th><th>DL</th></tr>
        <tr><td>1</td><td>A</td><td>Book</td><td>P</td><td>2020</td><td>10</td><td>EN</td><td>10MB</td><td>DJVU</td><td><a href="http://dl.com/b.djv">dl</a></td></tr>
        </table>
        </body></html>
        """
        dl = LibGenDownloader()
        results = dl._parse_results(html)
        assert len(results) == 0


class TestAnnaDownloader:
    def test_extract_author(self):
        ad = AnnaDownloader()
        assert ad._extract_author("Book Title by John Smith | some other", "Book Title") == "John Smith"
        assert ad._extract_author("No Match", "Other") == ""


class TestDocScraper:
    def test_doc_sources_defined(self):
        assert "pytorch" in DOC_SOURCES
        assert "scikit_learn" in DOC_SOURCES
        assert "yolo" in DOC_SOURCES

    def test_scraper_initialization(self):
        s = DocScraper()
        assert s.source == "official_docs"
