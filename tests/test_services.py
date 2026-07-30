import httpx

from qed_tracker.application import BookService, ResourceService
from qed_tracker.catalog import Catalog, load_catalog
from qed_tracker.downloader import DownloadManager
from qed_tracker.inventory import Inventory
from qed_tracker.models import Candidate


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


def test_catalog_preview_and_strict_download(tmp_path, pdf_bytes, monkeypatch):
    target = next(target for target in load_catalog("math-qe").targets if target.id == "03-munkres")
    catalog = Catalog("math-qe", "Math", "", "frozen", (target,))
    candidate = Candidate(
        "fake", "munkres", "Topology 2nd Edition", ("James Munkres",), "English",
        edition="2nd", download_url="https://example.test/topology.pdf",
    )
    manager = DownloadManager(retries=1)
    manager.client.close()
    manager.client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=pdf_bytes, request=request)))
    service = BookService([FakeProvider(candidate)], ResourceService(Inventory(tmp_path), manager))
    try:
        assert service.run_catalog(catalog)[0].status == "READY"
        monkeypatch.setattr(
            "qed_tracker.inventory.inspect_pdf",
            lambda path: (_ for _ in ()).throw(AssertionError("downloaded PDF must not be inspected twice")),
        )
        attempt = service.run_catalog(catalog, download=True)[0]
    finally:
        service.close()
    assert attempt.status == "DOWNLOADED"
    assert attempt.record.catalog_ref["target_id"] == "03-munkres"
    assert manager.client.is_closed


def test_catalog_does_not_auto_download_incomplete_metadata(tmp_path):
    target = next(target for target in load_catalog("math-qe").targets if target.id == "03-munkres")
    catalog = Catalog("math-qe", "Math", "", "frozen", (target,))
    candidate = Candidate("fake", "munkres", "Topology 2nd Edition", (), "", edition="2nd", download_url="https://example.test/topology.pdf")
    manager = DownloadManager(retries=1)
    service = BookService([FakeProvider(candidate)], ResourceService(Inventory(tmp_path), manager))
    try:
        attempt = service.run_catalog(catalog, download=True)[0]
    finally:
        service.close()
    assert attempt.status == "REVIEW"
