
import httpx
import pytest

from qed_tracker.downloader import DownloadError, DownloadManager
from qed_tracker.inventory import staging_max_age_seconds, sweep_downloads


def manager_with(handler, *, retries=1, max_bytes: int | None = None) -> DownloadManager:
    """假传输下载器：重定向交由 DownloadManager 手动逐跳处理，故客户端不再自动跟随。"""
    manager = DownloadManager(retries=retries) if max_bytes is None else DownloadManager(
        retries=retries, max_bytes=max_bytes
    )
    manager.client.close()
    manager.client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
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


def test_download_retry_restarts_and_ignores_existing_partial_file(tmp_path, pdf_bytes):
    destination = tmp_path / "book.pdf"
    partial = tmp_path / "book.pdf.part"
    partial.write_bytes(b"stale partial")
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        assert "range" not in request.headers
        if calls == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(200, content=pdf_bytes, request=request)

    manager = manager_with(handler, retries=2)
    try:
        manager.download("https://example.test/book.pdf", destination)
    finally:
        manager.close()
    assert destination.read_bytes() == pdf_bytes
    assert calls == 2


def test_invalid_content_never_becomes_final_file(tmp_path):
    manager = manager_with(lambda request: httpx.Response(200, content=b"<html>blocked</html>", request=request))
    destination = tmp_path / "bad.pdf"
    with pytest.raises(DownloadError, match="不是 PDF"):
        manager.download("https://example.test/bad.pdf", destination)
    manager.close()
    assert not destination.exists()
    assert not destination.with_suffix(".pdf.part").exists()


# QED-071 B 轮：Inventory 类（资源 JSON 岛）已退役——register/verify/scan 岛测试随之删除；
# 内容身份读路径切 qt_books（见 test_data_layout.py 反岛守护与 test_reconcile.py）。


# ---- QED-071 R2：staging 年龄清扫（四项边界 + 阈值计算） ----


def _aged(path, age_seconds: float):
    import os
    import time

    stamp = time.time() - age_seconds
    os.utime(path, (stamp, stamp))


def test_sweep_downloads_keeps_files_within_age_threshold(tmp_path):
    """阈值内保留：mtime 年龄未超 max_age_seconds 的 staging 文件不动。"""
    staging = tmp_path / "tmp" / "qed-tracker" / "downloads"
    staging.mkdir(parents=True)
    fresh = staging / "Topology_abc123_tag.download"
    fresh.write_bytes(b"in flight")
    _aged(fresh, 60)
    assert sweep_downloads(staging, max_age_seconds=3600) == []
    assert fresh.exists()


def test_sweep_downloads_removes_stale_staging_files(tmp_path):
    """阈值外删除：超龄的 *.download 与 *.download.part 被清扫并列入返回值。"""
    staging = tmp_path / "tmp" / "qed-tracker" / "downloads"
    staging.mkdir(parents=True)
    stale = staging / "Apostol_Calculus_dead0001_orphan.download"
    stale.write_bytes(b"x" * 1024)
    stale_part = staging / "Other_ffffffff_2.download.part"
    stale_part.write_bytes(b"y")
    _aged(stale, 7200)
    _aged(stale_part, 7200)
    removed = sweep_downloads(staging, max_age_seconds=3600)
    assert sorted(path.name for path in removed) == sorted([stale.name, stale_part.name])
    assert not stale.exists()
    assert not stale_part.exists()


def test_sweep_downloads_ignores_non_staging_patterns(tmp_path):
    """非本仓命名模式不删：*.download/.download.part 之外的文件（含成品 PDF、其他前缀）不动。"""
    staging = tmp_path / "tmp" / "qed-tracker" / "downloads"
    staging.mkdir(parents=True)
    pdf = staging / "reference_book.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    foreign = staging / "someone_else.tmp"
    foreign.write_bytes(b"data")
    _aged(pdf, 7200 * 24)
    _aged(foreign, 7200 * 24)
    assert sweep_downloads(staging, max_age_seconds=3600) == []
    assert pdf.exists()
    assert foreign.exists()


def test_sweep_downloads_stays_inside_given_directory(tmp_path):
    """不越出给定目录：非递归——子目录与目录外文件都不碰，目录本身保留。"""
    staging = tmp_path / "tmp" / "qed-tracker" / "downloads"
    nested = staging / "nested"
    nested.mkdir(parents=True)
    in_sub = nested / "orphan.download"
    in_sub.write_bytes(b"x")
    _aged(in_sub, 7200 * 24)
    outside = tmp_path / "tmp" / "exploration" / "keep.download"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(b"x")
    _aged(outside, 7200 * 24)
    assert sweep_downloads(staging, max_age_seconds=3600) == []
    assert staging.is_dir()
    assert in_sub.exists()
    assert outside.exists()


def test_sweep_downloads_missing_directory_is_noop(tmp_path):
    """目录不存在时安全空返回（服务启动先于任何下载的常态）。"""
    assert sweep_downloads(tmp_path / "absent", max_age_seconds=3600) == []


def test_staging_max_age_threshold_follows_formula_with_floor():
    """QED-071 D7：阈值 = timeout × retries × 4 且绝对下限 6 小时，
    严格大于单次下载最长寿命（httpx timeout 兜底卡死），无需 in-flight 注册表。"""
    assert staging_max_age_seconds(30.0, 3) == 6 * 3600  # 30×3×4=360s < 下限 → 6h
    assert staging_max_age_seconds(600.0, 4) == 6 * 3600  # 600×4×4=9600s < 下限 → 6h
    assert staging_max_age_seconds(3000.0, 4) == 3000 * 4 * 4  # 48000s > 下限 → 公式值
    assert staging_max_age_seconds(30.0, 3) > 30.0 * 3  # 严格大于单次下载最长寿命


# ---- QED-068 C 步（068-4）：手动逐跳重定向复检 + 字节硬顶 ----


def test_redirect_to_private_host_blocks_before_connect(tmp_path, stub_dns):
    """SSRF 逐跳复检：302 指向解析到内网的主机 → 连接前拒绝，该主机一次请求都不发出。"""
    stub_dns["internal.test"] = ("10.0.0.5",)
    requested: list[str] = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://internal.test/a.pdf"}, request=request)

    manager = manager_with(handler)
    destination = tmp_path / "paper.pdf"
    try:
        with pytest.raises(DownloadError, match="非公网"):
            manager.download("https://origin.test/a.pdf", destination)
    finally:
        manager.close()
    assert requested == ["https://origin.test/a.pdf"]
    assert not destination.exists()
    assert not (tmp_path / "paper.pdf.part").exists()


def test_redirect_chain_within_limit_saves_pdf(tmp_path, pdf_bytes, stub_dns):
    """≤5 跳合法重定向逐跳放行；相对 Location 按当前 URL 拼接，末跳 200 正常落盘。"""
    requested: list[str] = []

    def handler(request):
        requested.append(str(request.url))
        path = request.url.path
        if path == "/a.pdf":
            return httpx.Response(302, headers={"location": "https://b.test/1.pdf"}, request=request)
        if path == "/1.pdf":
            return httpx.Response(301, headers={"location": "/2.pdf"}, request=request)
        if path == "/2.pdf":
            return httpx.Response(200, content=pdf_bytes, request=request)
        raise AssertionError(f"未预期的请求：{request.url}")

    manager = manager_with(handler)
    destination = tmp_path / "paper.pdf"
    try:
        result = manager.download("https://a.test/a.pdf", destination)
    finally:
        manager.close()
    assert result.page_count == 1
    assert destination.read_bytes() == pdf_bytes
    assert requested == ["https://a.test/a.pdf", "https://b.test/1.pdf", "https://b.test/2.pdf"]


def test_redirect_chain_over_hop_limit_blocked(tmp_path, stub_dns):
    """第 6 跳（超过 5 跳上限）拒绝：错误文案含跳数要素，半成品不落成品区。"""
    requested: list[str] = []

    def handler(request):
        requested.append(str(request.url))
        hop = int(request.url.path.lstrip("/"))
        return httpx.Response(302, headers={"location": f"https://r.test/{hop + 1}"}, request=request)

    manager = manager_with(handler)
    destination = tmp_path / "paper.pdf"
    try:
        with pytest.raises(DownloadError, match="跳"):
            manager.download("https://r.test/0", destination)
    finally:
        manager.close()
    assert len(requested) == 6
    assert not destination.exists()


def test_non_http_scheme_redirect_blocked(tmp_path, stub_dns):
    """异 scheme（file:// 等）重定向拒绝，不交给 httpx 处理。"""

    def handler(request):
        return httpx.Response(302, headers={"location": "file:///etc/passwd"}, request=request)

    manager = manager_with(handler)
    destination = tmp_path / "paper.pdf"
    try:
        with pytest.raises(DownloadError, match="scheme"):
            manager.download("https://origin.test/a.pdf", destination)
    finally:
        manager.close()
    assert not destination.exists()


def test_dns_failure_blocks_download(tmp_path, monkeypatch):
    """解析失败按 fail-closed 拒绝：不存在「解析不了就放行」的回落。"""
    from qed_tracker import downloader

    def raise_gaierror(host: str) -> list[str]:
        raise OSError(-2, "Name or service not known")

    monkeypatch.setattr(downloader, "_resolve_host_ips", raise_gaierror)
    manager = manager_with(lambda request: httpx.Response(200, content=b"", request=request))
    destination = tmp_path / "paper.pdf"
    try:
        with pytest.raises(DownloadError, match="解析失败"):
            manager.download("https://nowhere.test/a.pdf", destination)
    finally:
        manager.close()
    assert not destination.exists()


def test_security_rejection_is_terminal_not_retried(tmp_path, stub_dns):
    """安全拒绝是终止性失败：不进重试循环（重试只会重复连接风险面）。"""
    stub_dns["internal.test"] = ("127.0.0.1",)
    requested: list[str] = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://internal.test/a.pdf"}, request=request)

    manager = manager_with(handler, retries=3)
    destination = tmp_path / "paper.pdf"
    try:
        with pytest.raises(DownloadError, match="非公网"):
            manager.download("https://origin.test/a.pdf", destination)
    finally:
        manager.close()
    assert len(requested) == 1
    assert not destination.exists()


def test_max_bytes_aborts_and_cleans_partial(tmp_path, stub_dns):
    """流式写盘超 max_bytes 立即中断并删 partial，成品文件永不出现。"""
    body = b"%PDF-1.4\n" + b"x" * 4096

    def handler(request):
        return httpx.Response(200, content=body, request=request)

    manager = manager_with(handler, max_bytes=1024)
    destination = tmp_path / "big.pdf"
    try:
        with pytest.raises(DownloadError, match="上限"):
            manager.download("https://example.test/big.pdf", destination)
    finally:
        manager.close()
    assert not destination.exists()
    assert not (tmp_path / "big.pdf.part").exists()


def test_max_bytes_defaults_above_registered_book_pdfs():
    """默认硬顶不得误伤合法成品：高于现库最大书体量级（实测 121.5 MiB → 默认 512 MiB）。"""
    manager = DownloadManager()
    try:
        assert manager.max_bytes >= 512 * 1024 * 1024
    finally:
        manager.close()
