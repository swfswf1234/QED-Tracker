import json

import httpx

from qed_tracker.axiom import AxiomClient, AxiomError
from qed_tracker.downloader import inspect_pdf
from qed_tracker.models import ResourceKind, ResourceRecord


def _record(tmp_path, pdf: bytes, *, kind: ResourceKind = ResourceKind.BOOK, name: str = "book") -> ResourceRecord:
    """QED-071 D12：岛退役后 ResourceRecord 只是内存 DTO——测试手工拼装，
    与 DB 侧 `record_from_book` 物化路径同构。"""
    pdf_path = tmp_path / "raw" / "math" / "course" / f"{name}.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(pdf)
    sha256, size, pages = inspect_pdf(pdf_path)
    return ResourceRecord(
        resource_id=f"sha256:{sha256}",
        kind=kind.value,
        title=name.title(),
        authors=[],
        language="",
        year="",
        identifiers={},
        source={"provider": "test"},
        file={
            "relative_path": pdf_path.relative_to(tmp_path).as_posix(),
            "sha256": sha256,
            "size_bytes": size,
            "mime_type": "application/pdf",
            "page_count": pages,
        },
    )


def _client(handler) -> AxiomClient:
    client = AxiomClient("http://axiom.test")
    client.client.close()
    client.client = httpx.Client(base_url="http://axiom.test", transport=httpx.MockTransport(handler))
    return client


def test_axiom_push_uploads_without_parse_by_default(tmp_path, pdf_bytes):
    resource = _record(tmp_path, pdf_bytes)
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/api/v1/health":
            return httpx.Response(200, json={"status": "ok", "version": "0.3.0"}, request=request)
        return httpx.Response(201, json={"id": "doc-1", "filename": "book.pdf"}, request=request)

    client = _client(handler)
    try:
        result = client.push(resource, tmp_path)
    finally:
        client.close()

    assert result["document_id"] == "doc-1"
    assert [request.url.path for request in requests] == ["/api/v1/health", "/api/v1/documents"]
    # QED-071 D3：传输留痕判废——push 结果只经返回值透出，不再落盘（根仓 ADR 0018 反岛）。
    assert not (tmp_path / "qed-tracker").exists()


def test_axiom_parse_is_explicit_and_preserves_page_range(tmp_path, pdf_bytes):
    resource = _record(tmp_path, pdf_bytes, kind=ResourceKind.PAPER, name="paper")
    parse_payload = {}

    def handler(request):
        if request.url.path == "/api/v1/health":
            return httpx.Response(200, json={"status": "ok"}, request=request)
        if request.url.path == "/api/v1/documents":
            return httpx.Response(201, json={"id": "doc-2"}, request=request)
        parse_payload.update(json.loads(request.content))
        return httpx.Response(202, json={"job": {"id": "job-1"}, "created": True}, request=request)

    client = _client(handler)
    try:
        result = client.push(resource, tmp_path, parse=True, page_start=2, page_end=5)
    finally:
        client.close()
    assert parse_payload == {"page_start": 2, "page_end": 5}
    assert result["parse_command"]["job"]["id"] == "job-1"


def test_axiom_reports_http_error(tmp_path, pdf_bytes):
    resource = _record(tmp_path, pdf_bytes, name="large")

    def handler(request):
        if request.url.path.endswith("health"):
            return httpx.Response(200, json={"status": "ok"}, request=request)
        return httpx.Response(413, json={"error": {"code": "file_too_large"}}, request=request)

    client = _client(handler)
    try:
        try:
            client.push(resource, tmp_path)
        except AxiomError as exc:
            assert "HTTP 413" in str(exc)
        else:
            raise AssertionError("expected AxiomError")
    finally:
        client.close()


def test_axiom_parse_creation_failure_raises_without_transfer_trace(tmp_path, pdf_bytes):
    """QED-071 D3：解析任务创建失败时照常抛 AxiomError，且不留 meta/transfers 磁盘痕
    （原「上传成功留痕」判废——无读取方，审计经 qt_tasks/Axiom-Flow 侧反查）。"""
    resource = _record(tmp_path, pdf_bytes)

    def handler(request):
        if request.url.path.endswith("health"):
            return httpx.Response(200, json={"status": "ok"}, request=request)
        if request.url.path == "/api/v1/documents":
            return httpx.Response(201, json={"id": "doc-saved"}, request=request)
        return httpx.Response(503, json={"error": {"code": "unavailable"}}, request=request)

    client = _client(handler)
    try:
        try:
            client.push(resource, tmp_path, parse=True)
        except AxiomError as exc:
            assert "HTTP 503" in str(exc)
        else:
            raise AssertionError("expected AxiomError")
    finally:
        client.close()
    assert not (tmp_path / "qed-tracker").exists()
