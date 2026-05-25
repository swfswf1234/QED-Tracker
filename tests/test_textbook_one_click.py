"""Tests for strict one-click textbook collection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.collectors.textbook_hunter import DownloadStatus, TextbookHunter, _strict_match
from app.curricula.base import Confidence, Course, TextbookTarget


class FakeSource:
    def __init__(self, name, results=None, downloads=None, reachable=True):
        self.name = name
        self.results = results or []
        self.downloads = downloads or {}
        self.reachable = reachable
        self.searches = []

    def check_reachable(self):
        return self.reachable

    def search(self, query, max_results=8):
        self.searches.append(query)
        return [dict(r) for r in self.results]

    def download(self, url, save_path):
        ok = self.downloads.get(url, False)
        if ok:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(b"%PDF-1.4 fake")
        return ok

    def close(self):
        pass


def test_strict_match_rejects_same_title_wrong_author():
    target = TextbookTarget(
        title="Complex Analysis",
        author="Stein",
        lang="en",
        confidence=Confidence.B,
        edition="2nd",
    )
    result = {
        "title": "Complex Analysis",
        "author": "Ahlfors",
        "language": "English",
        "year": "1979",
    }

    assert _strict_match(result, target) is None


def test_one_click_skips_existing_target_without_search(tmp_path, monkeypatch):
    monkeypatch.setattr("app.collectors.textbook_hunter.settings.textbook_dir", str(tmp_path))
    existing = tmp_path / "textbooks" / "03_topology" / "Munkres_Topology.pdf"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"%PDF-1.4 existing")

    target = TextbookTarget(title="Topology", author="Munkres", lang="en", query="Munkres Topology")
    course = Course(id="03_topology", name="Topology", textbooks=[target])
    source = FakeSource("libgen")
    hunter = TextbookHunter(proxy="", sources=[("libgen", source)])

    attempts = hunter.one_click_course(course, missing_only=True)

    assert attempts[0].status == DownloadStatus.SKIP_EXISTS
    assert source.searches == []


def test_one_click_passes_no_exact_match_and_continues(tmp_path, monkeypatch):
    monkeypatch.setattr("app.collectors.textbook_hunter.settings.textbook_dir", str(tmp_path))
    wrong_author = {
        "title": "Complex Analysis",
        "author": "Ahlfors",
        "language": "English",
        "size": "10MB",
        "download_url": "https://example.test/ahlfors.pdf",
    }
    target1 = TextbookTarget(title="Complex Analysis", author="Stein", lang="en", query="Stein Complex Analysis")
    target2 = TextbookTarget(title="Topology", author="Munkres", lang="en", query="Munkres Topology")
    course = Course(id="05_complex_analysis", name="Complex Analysis", textbooks=[target1, target2])
    source = FakeSource("libgen", results=[wrong_author])
    hunter = TextbookHunter(proxy="", sources=[("libgen", source)])

    attempts = hunter.one_click_course(course, missing_only=True)

    assert [a.status for a in attempts] == [
        DownloadStatus.PASS_NO_EXACT_MATCH,
        DownloadStatus.PASS_NO_EXACT_MATCH,
    ]
    assert source.searches == ["Stein Complex Analysis", "Munkres Topology"]


def test_one_click_downloads_matching_candidate_and_records_source(tmp_path, monkeypatch):
    monkeypatch.setattr("app.collectors.textbook_hunter.settings.textbook_dir", str(tmp_path))
    result = {
        "title": "Topology",
        "author": "Munkres",
        "language": "English",
        "size": "10MB",
        "download_url": "https://example.test/munkres.pdf",
    }
    target = TextbookTarget(title="Topology", author="Munkres", lang="en", query="Munkres Topology")
    course = Course(id="03_topology", name="Topology", textbooks=[target])
    source = FakeSource("libgen", results=[result], downloads={"https://example.test/munkres.pdf": True})
    hunter = TextbookHunter(proxy="", sources=[("libgen", source)])

    attempts = hunter.one_click_course(course, missing_only=True)

    assert attempts[0].status == DownloadStatus.SUCCESS
    assert attempts[0].source == "libgen"
    assert attempts[0].target_kind == "textbook"
    assert attempts[0].local_path == "textbooks/03_topology/Munkres_Topology.pdf"
    assert (tmp_path / attempts[0].local_path).exists()
