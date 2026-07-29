
import httpx
import pytest

from qed_tracker.downloader import DownloadError, DownloadManager, inspect_pdf
from qed_tracker.inventory import Inventory
from qed_tracker.models import ResourceKind


def manager_with(handler) -> DownloadManager:
    manager = DownloadManager(retries=1)
    manager.client.close()
    manager.client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return manager


def test_download_validates_and_atomically_saves_pdf(tmp_path, pdf_bytes):
    manager = manager_with(lambda request: httpx.Response(200, content=pdf_bytes, request=request))
    destination = tmp_path / "paper.pdf"
    try:
        result = manager.download("https://example.test/paper.pdf", destination)
    finally:
        manager.close()

    assert destination.read_bytes() == pdf_bytes
    assert result.page_count == 1
    assert result.size_bytes == len(pdf_bytes)
    assert not (tmp_path / "paper.pdf.part").exists()


def test_download_resumes_existing_partial_file(tmp_path, pdf_bytes):
    destination = tmp_path / "book.pdf"
    partial = tmp_path / "book.pdf.part"
    split = len(pdf_bytes) // 2
    partial.write_bytes(pdf_bytes[:split])

    def handler(request):
        assert request.headers["range"] == f"bytes={split}-"
        return httpx.Response(206, content=pdf_bytes[split:], request=request)

    manager = manager_with(handler)
    try:
        manager.download("https://example.test/book.pdf", destination)
    finally:
        manager.close()
    assert destination.read_bytes() == pdf_bytes


def test_complete_partial_is_promoted_without_network(tmp_path, pdf_bytes):
    destination = tmp_path / "complete.pdf"
    destination.with_suffix(".pdf.part").write_bytes(pdf_bytes)

    def handler(request):
        raise AssertionError("complete partial must not use network")

    manager = manager_with(handler)
    try:
        result = manager.download("https://example.test/complete.pdf", destination)
    finally:
        manager.close()
    assert result.page_count == 1
    assert destination.read_bytes() == pdf_bytes


def test_invalid_content_never_becomes_final_file(tmp_path):
    manager = manager_with(lambda request: httpx.Response(200, content=b"<html>blocked</html>", request=request))
    destination = tmp_path / "bad.pdf"
    with pytest.raises(DownloadError, match="不是 PDF"):
        manager.download("https://example.test/bad.pdf", destination)
    manager.close()
    assert not destination.exists()
    assert not destination.with_suffix(".pdf.part").exists()


def test_inventory_register_export_verify_and_scan(tmp_path, pdf_bytes):
    first = tmp_path / "books" / "first.pdf"
    second = tmp_path / "legacy" / "second.pdf"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_bytes(pdf_bytes)
    second.write_bytes(pdf_bytes)
    inventory = Inventory(tmp_path)

    record = inventory.register(first, kind=ResourceKind.BOOK, title="First")
    assert inventory.get(record.resource_id).file["relative_path"] == "books/first.pdf"
    assert inventory.verify()[0][1] == "ok"
    manifest = inventory.export_jsonl()
    assert record.resource_id in manifest.read_text(encoding="utf-8")

    records, errors = inventory.scan([tmp_path / "legacy"])
    assert not errors
    assert records[0].sha256 == inspect_pdf(second)[0]
    assert len(inventory.list()) == 1
    assert inventory.list()[0].file["relative_path"] == "books/first.pdf"


def test_inventory_rejects_paths_outside_data_root(tmp_path, pdf_bytes):
    outside = tmp_path.parent / "outside.pdf"
    outside.write_bytes(pdf_bytes)
    try:
        with pytest.raises(ValueError, match="数据根目录"):
            Inventory(tmp_path).register(outside, kind=ResourceKind.BOOK, title="Outside")
    finally:
        outside.unlink(missing_ok=True)
