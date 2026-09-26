
import httpx
import pytest

from qed_tracker.downloader import DownloadError, DownloadManager
from qed_tracker.inventory import staging_max_age_seconds, sweep_downloads


def manager_with(handler, *, retries=1) -> DownloadManager:
    manager = DownloadManager(retries=retries)
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
