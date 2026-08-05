"""数据布局契约：meta/ 状态目录、raw/ 成品目录与 `<slug>_<sha256前8>.pdf` 文件名规则。"""

import httpx

from qed_tracker.application import BookService, ResourceService
from qed_tracker.catalog import Catalog, load_catalog
from qed_tracker.downloader import DownloadManager
from qed_tracker.inventory import Inventory
from qed_tracker.models import Candidate, ResourceKind


def _manager_with(pdf_bytes: bytes) -> DownloadManager:
    manager = DownloadManager(retries=1)
    manager.client.close()
    manager.client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=pdf_bytes, request=request))
    )
    return manager


class FakeProvider:
    name = "fake"

    def __init__(self, candidate):
        self.candidate = candidate

    def search(self, query, limit=10):
        return [self.candidate]

    def resolve(self, candidate):
        return candidate

    def close(self):
        return None


def _candidate(title: str = "Topology 2nd Edition") -> Candidate:
    return Candidate("fake", "munkres", title, ("James Munkres",), "English", download_url="https://example.test/topology.pdf")


def test_inventory_state_lives_under_meta(tmp_path, pdf_bytes):
    path = tmp_path / "book.pdf"
    path.write_bytes(pdf_bytes)
    inventory = Inventory(tmp_path)
    record = inventory.register(path, kind=ResourceKind.BOOK, title="Book")
    assert (tmp_path / "meta" / "resources" / f"{record.sha256}.json").exists()
    assert not (tmp_path / ".qed-tracker").exists()


def test_downloaded_book_uses_sha256_filename_rule(tmp_path, pdf_bytes):
    manager = _manager_with(pdf_bytes)
    service = ResourceService(Inventory(tmp_path), manager)
    try:
        record = service.download_candidate(
            _candidate(), kind=ResourceKind.BOOK, destination_dir=tmp_path / "raw" / "books" / "inbox"
        )
    finally:
        service.close()
    expected = tmp_path / "raw" / "books" / "inbox" / f"Topology_2nd_Edition_{record.sha256[:8]}.pdf"
    assert expected.exists()
    assert record.file["relative_path"] == expected.relative_to(tmp_path).as_posix()


def test_paper_download_uses_arxiv_id_filename_rule(tmp_path, pdf_bytes):
    candidate = Candidate(
        "arxiv", "2401.00001", "A Paper", (), "en", identifiers={"arxiv": "2401.00001"},
        download_url="https://example.test/paper.pdf",
    )
    manager = _manager_with(pdf_bytes)
    service = ResourceService(Inventory(tmp_path), manager)
    try:
        record = service.download_candidate(candidate, kind=ResourceKind.PAPER, destination_dir=tmp_path / "raw" / "papers" / "2024")
    finally:
        service.close()
    expected = tmp_path / "raw" / "papers" / "2024" / f"2401.00001_{record.sha256[:8]}.pdf"
    assert expected.exists()


def test_catalog_book_lands_in_raw_books_math_qe(tmp_path, pdf_bytes):
    target = next(target for target in load_catalog("math-qe").targets if target.id == "03-munkres")
    catalog = Catalog("math-qe", "Math", "", "frozen", (target,))
    manager = _manager_with(pdf_bytes)
    candidate = _candidate()
    service = BookService([FakeProvider(candidate)], ResourceService(Inventory(tmp_path), manager))
    try:
        attempt = service.run_catalog(catalog, download=True)[0]
    finally:
        service.close()
    assert attempt.status == "DOWNLOADED"
    assert (tmp_path / "raw" / "books" / "math-qe" / "03_topology").exists()


def test_exercise_download_lands_in_raw_exercises_inbox(tmp_path, pdf_bytes):
    target = next(target for target in load_catalog("math-qe").targets if target.id == "01-demidovich")
    catalog = Catalog("math-qe", "Math", "", "frozen", (target,))
    manager = _manager_with(pdf_bytes)
    candidate = Candidate("fake", "demidovich", "吉米多维奇数学分析习题集", ("吉米多维奇",), "zh", download_url="https://example.test/book.pdf")
    service = BookService([FakeProvider(candidate)], ResourceService(Inventory(tmp_path), manager))
    try:
        attempt = service.run_catalog(catalog, download=True)[0]
    finally:
        service.close()
    assert attempt.status == "DOWNLOADED"
    assert (tmp_path / "raw" / "exercises" / "inbox").exists()
