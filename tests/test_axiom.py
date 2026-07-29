import json

import httpx

from qed_tracker.axiom import AxiomClient, AxiomError
from qed_tracker.inventory import Inventory
from qed_tracker.models import ResourceKind


def test_axiom_push_uploads_without_parse_by_default(tmp_path, pdf_bytes):
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(pdf_bytes)
    inventory = Inventory(tmp_path)
    resource = inventory.register(pdf, kind=ResourceKind.BOOK, title="Book")
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/api/v1/health":
            return httpx.Response(200, json={"status": "ok", "version": "0.3.0"}, request=request)
        return httpx.Response(201, json={"id": "doc-1", "filename": "book.pdf"}, request=request)

    client = AxiomClient("http://axiom.test")
    client.client.close()
    client.client = httpx.Client(base_url="http://axiom.test", transport=httpx.MockTransport(handler))
    try:
        result = client.push(resource, inventory)
    finally:
        client.close()

    assert result["document_id"] == "doc-1"
    assert [request.url.path for request in requests] == ["/api/v1/health", "/api/v1/documents"]
    assert (inventory.transfers_dir / f"{resource.sha256}.json").exists()


def test_axiom_parse_is_explicit_and_preserves_page_range(tmp_path, pdf_bytes):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(pdf_bytes)
    inventory = Inventory(tmp_path)
    resource = inventory.register(pdf, kind=ResourceKind.PAPER, title="Paper")
    parse_payload = {}

    def handler(request):
        if request.url.path == "/api/v1/health":
            return httpx.Response(200, json={"status": "ok"}, request=request)
        if request.url.path == "/api/v1/documents":
            return httpx.Response(201, json={"id": "doc-2"}, request=request)
        parse_payload.update(json.loads(request.content))
        return httpx.Response(202, json={"job": {"id": "job-1"}, "created": True}, request=request)

    client = AxiomClient("http://axiom.test")
    client.client.close()
    client.client = httpx.Client(base_url="http://axiom.test", transport=httpx.MockTransport(handler))
    try:
        result = client.push(resource, inventory, parse=True, page_start=2, page_end=5)
    finally:
        client.close()
    assert parse_payload == {"page_start": 2, "page_end": 5}
    assert result["parse_command"]["job"]["id"] == "job-1"


def test_axiom_reports_http_error(tmp_path, pdf_bytes):
    pdf = tmp_path / "large.pdf"
    pdf.write_bytes(pdf_bytes)
    inventory = Inventory(tmp_path)
    resource = inventory.register(pdf, kind=ResourceKind.BOOK, title="Large")

    def handler(request):
        if request.url.path.endswith("health"):
            return httpx.Response(200, json={"status": "ok"}, request=request)
        return httpx.Response(413, json={"error": {"code": "file_too_large"}}, request=request)

    client = AxiomClient("http://axiom.test")
    client.client.close()
    client.client = httpx.Client(base_url="http://axiom.test", transport=httpx.MockTransport(handler))
    try:
        try:
            client.push(resource, inventory)
        except AxiomError as exc:
            assert "HTTP 413" in str(exc)
        else:
            raise AssertionError("expected AxiomError")
    finally:
        client.close()


def test_axiom_records_successful_upload_when_parse_creation_fails(tmp_path, pdf_bytes):
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(pdf_bytes)
    inventory = Inventory(tmp_path)
    resource = inventory.register(pdf, kind=ResourceKind.BOOK, title="Book")

    def handler(request):
        if request.url.path.endswith("health"):
            return httpx.Response(200, json={"status": "ok"}, request=request)
        if request.url.path == "/api/v1/documents":
            return httpx.Response(201, json={"id": "doc-saved"}, request=request)
        return httpx.Response(503, json={"error": {"code": "unavailable"}}, request=request)

    client = AxiomClient("http://axiom.test")
    client.client.close()
    client.client = httpx.Client(base_url="http://axiom.test", transport=httpx.MockTransport(handler))
    try:
        try:
            client.push(resource, inventory, parse=True)
        except AxiomError:
            transfer = json.loads((inventory.transfers_dir / f"{resource.sha256}.json").read_text(encoding="utf-8"))
            assert transfer["document_id"] == "doc-saved"
            assert "parse_error" in transfer
        else:
            raise AssertionError("expected AxiomError")
    finally:
        client.close()
