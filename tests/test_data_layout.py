"""数据布局契约（ARCH-019 统一数据根）：
- 共享树 <QED_DATA_ROOT>/：raw/<domain>/<course>/ 原始区、tmp/qed-tracker/downloads/ 下载临时区；
- `<slug>_<sha256前8>.pdf` 文件名规则与 md5 内容校验回归；
- QED-071 B 轮全局反岛守护：下载/清扫全链路不得生成 `<data_root>/qed-tracker/`
  顶层目录（资源 JSON 岛与 Axiom 传输留痕均已退役，根仓 ADR 0018）。

kind=BOOK 链路需 qt_books（M4）——DB 去重与登记语义见 tests/test_services.py，
真实 repo 的取书落盘见 tests/test_book_fetch.py；本文件用 exercise/paper 通道
验证与 DB 无关的文件名/落盘/staging 契约。
"""

import hashlib
import os
import time
from pathlib import Path

import httpx
import pytest

from qed_tracker.application import ResourceService
from qed_tracker.application.papers import PaperService
from qed_tracker.downloader import DownloadError, DownloadManager
from qed_tracker.inventory import downloads_tmp_dir, raw_course_dir, raw_general_dir, sweep_downloads
from qed_tracker.models import Candidate, ResourceKind

REPO_ROOT = Path(__file__).resolve().parents[1]


def _manager_with(pdf_bytes: bytes) -> DownloadManager:
    manager = DownloadManager(retries=1)
    manager.client.close()
    manager.client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=pdf_bytes, request=request))
    )
    return manager


def _candidate(title: str = "Topology 2nd Edition", identifiers: dict | None = None) -> Candidate:
    return Candidate(
        "fake", "munkres", title, ("James Munkres",), "English",
        identifiers=identifiers or {}, download_url="https://example.test/topology.pdf",
    )


def _download(pdf: bytes, destination: Path, *, data_root: Path, candidate: Candidate | None = None,
              kind: ResourceKind = ResourceKind.EXERCISE, staging_tag: str = ""):
    service = ResourceService(data_root, _manager_with(pdf))
    try:
        return service.download_candidate(
            candidate or _candidate(), kind=kind, destination_dir=destination, staging_tag=staging_tag
        )
    finally:
        service.close()


def test_layout_helpers_follow_shared_tree(tmp_path):
    """ARCH-019 派生路径表：raw 课程桶 / 领域通用桶 / QED-Tracker 下载临时区。"""
    assert raw_course_dir(tmp_path, "01_math_analysis") == tmp_path / "raw" / "math" / "01_math_analysis"
    assert raw_general_dir(tmp_path) == tmp_path / "raw" / "math" / "_general"
    assert downloads_tmp_dir(tmp_path) == tmp_path / "tmp" / "qed-tracker" / "downloads"


def test_downloaded_file_uses_sha256_filename_rule(tmp_path, pdf_bytes):
    manager = _manager_with(pdf_bytes)
    service = ResourceService(tmp_path, manager)
    try:
        record = service.download_candidate(
            _candidate(), kind=ResourceKind.EXERCISE, destination_dir=raw_general_dir(tmp_path)
        )
    finally:
        service.close()
    expected = raw_general_dir(tmp_path) / f"Topology_2nd_Edition_{record.sha256[:8]}.pdf"
    assert expected.exists()
    assert record.file["relative_path"] == expected.relative_to(tmp_path).as_posix()


def test_staging_and_part_files_live_in_shared_tmp_zone(tmp_path, pdf_bytes):
    """"tmp 先写后原子落盘 raw"：.download/.part 中间态只在 tmp/qed-tracker/downloads/，
    成品直接原子替换进 raw；完成后临时区无残留、不生成岛目录。"""

    manager = _manager_with(pdf_bytes)
    service = ResourceService(tmp_path, manager)
    try:
        record = service.download_candidate(
            _candidate(), kind=ResourceKind.EXERCISE, destination_dir=raw_general_dir(tmp_path)
        )
    finally:
        service.close()
    tmp_zone = downloads_tmp_dir(tmp_path)
    assert record.file["sha256"]
    assert not list(tmp_zone.glob("*")), "下载完成后临时区应无残留"
    assert not list(raw_general_dir(tmp_path).glob("*.download")), "raw 区不得有中间态文件"
    # QED-071 B 轮全局反岛守护（D12/ADR 0018）：下载链路不得生成 <data_root>/qed-tracker/
    assert not (tmp_path / "qed-tracker").exists()


def test_download_rejects_mismatched_declared_md5(tmp_path, pdf_bytes):
    """2026-08-09：archive resolve 声明的 md5 与实际下载内容不一致时拒绝登记并清理 staging。"""

    manager = _manager_with(pdf_bytes)
    candidate = _candidate(identifiers={"md5": "0" * 32})
    service = ResourceService(tmp_path, manager)
    try:
        with pytest.raises(DownloadError, match="内容完整性校验失败"):
            service.download_candidate(candidate, kind=ResourceKind.EXERCISE, destination_dir=raw_general_dir(tmp_path))
    finally:
        service.close()
    assert not list(downloads_tmp_dir(tmp_path).glob("*.download")), "staging 文件应被清理"


def test_download_accepts_matching_declared_md5(tmp_path, pdf_bytes):
    """md5 与下载内容一致时正常登记。"""

    declared = hashlib.md5(pdf_bytes).hexdigest()
    manager = _manager_with(pdf_bytes)
    service = ResourceService(tmp_path, manager)
    try:
        record = service.download_candidate(
            _candidate(identifiers={"md5": declared}), kind=ResourceKind.EXERCISE,
            destination_dir=raw_general_dir(tmp_path),
        )
    finally:
        service.close()
    assert record.file["sha256"]


def test_paper_service_lands_in_general_papers_by_year(tmp_path, pdf_bytes):
    """论文经 PaperService.download 落领域通用桶 papers/<year>/（迁移映射 raw/math/_general/papers/）。"""

    from qed_tracker.providers.books import BookProvider  # noqa: F401 - 仅确保包导入面稳定

    class FakeArxiv:
        name = "arxiv"

        def close(self):
            return None

    candidate = Candidate(
        "arxiv", "2401.00001", "A Paper", (), "en", year="2024",
        identifiers={"arxiv": "2401.00001"}, download_url="https://example.test/paper.pdf",
    )
    manager = _manager_with(pdf_bytes)
    service = PaperService(FakeArxiv(), ResourceService(tmp_path, manager))
    try:
        record = service.download(candidate)
    finally:
        service.close()
    expected = raw_general_dir(tmp_path) / "papers" / "2024" / f"2401.00001_{record.sha256[:8]}.pdf"
    assert expected.exists()
    assert not (tmp_path / "qed-tracker").exists()


def test_paper_download_uses_arxiv_id_filename_rule(tmp_path, pdf_bytes):
    candidate = Candidate(
        "arxiv", "2401.00001", "A Paper", (), "en", identifiers={"arxiv": "2401.00001"},
        download_url="https://example.test/paper.pdf",
    )
    manager = _manager_with(pdf_bytes)
    service = ResourceService(tmp_path, manager)
    try:
        record = service.download_candidate(
            candidate, kind=ResourceKind.PAPER,
            destination_dir=raw_general_dir(tmp_path) / "papers" / "2024",
        )
    finally:
        service.close()
    expected = raw_general_dir(tmp_path) / "papers" / "2024" / f"2401.00001_{record.sha256[:8]}.pdf"
    assert expected.exists()


def test_same_title_different_content_get_distinct_filenames(tmp_path, pdf_bytes):
    """2026-08-09 回归（B 轮改写）：同标题不同内容 → 文件名以 sha8 区分（原
    catalog_target 前缀随 D11 退役）；并发同名冲突由 staging_tag 覆盖，
    成品名保持内容指纹确定性。"""

    from io import BytesIO

    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=200)
    stream = BytesIO()
    writer.write(stream)
    other_pdf = stream.getvalue()

    destination = raw_course_dir(tmp_path, "01_math_analysis")
    title = "数学分析 陈纪修 第三版 课本及答案"
    first = _download(pdf_bytes, destination, candidate=_candidate(title=title), staging_tag="t1", data_root=tmp_path)
    second = _download(other_pdf, destination, candidate=_candidate(title=title), staging_tag="t2", data_root=tmp_path)
    names = sorted(p.name for p in destination.glob("*.pdf"))
    assert len(names) == 2
    assert names == sorted(
        [Path(first.file["relative_path"]).name, Path(second.file["relative_path"]).name]
    )
    assert names[0] != names[1]
    assert all(name.startswith("数学分析_陈纪修_第三版_课本及答案_") for name in names)
    assert not (tmp_path / "qed-tracker").exists()


# ---- QED-071 反岛守护（A-W4 局部 + B 轮全局） ----


def test_source_never_writes_axiom_transfer_island():
    """① src/ 全仓不出现 meta/transfers 字符串——Axiom 传输留痕已判废（D3），
    任何新增写入路径都会重建野生区，违反根仓 ADR 0018。"""
    offenders = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in sorted((REPO_ROOT / "src").rglob("*.py"))
        if "meta/transfers" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_source_never_writes_resources_island():
    """①′ src/ 全仓不出现岛目录路径字面量（`"qed-tracker" / "meta" / "resources"` 的
    带引号构件）——资源 JSON 岛已退役（QED-071 B 轮），内容身份只存 qt_books 三列；
    docstring 里的历史说明不带引号，不会误伤。"""
    offenders = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in sorted((REPO_ROOT / "src").rglob("*.py"))
        if '"resources"' in path.read_text(encoding="utf-8") or '"meta"' in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_sweep_and_download_never_create_island_dir(tmp_path, pdf_bytes):
    """② 跑完整下载 + A-W2 清扫：`<data_root>/qed-tracker/` 顶层目录不生成，
    tmp/qed-tracker/downloads/ 终态符合预期（超龄清掉、新鲜保留）。"""
    _download(pdf_bytes, raw_general_dir(tmp_path), data_root=tmp_path)

    staging = downloads_tmp_dir(tmp_path)
    staging.mkdir(parents=True, exist_ok=True)
    stale = staging / "Orphan_deadbeef.download"
    stale.write_bytes(b"stale")
    stamp = time.time() - 24 * 3600
    os.utime(stale, (stamp, stamp))
    fresh = staging / "InFlight_01234567.download"
    fresh.write_bytes(b"fresh")

    removed = sweep_downloads(staging, max_age_seconds=6 * 3600)

    assert not (tmp_path / "qed-tracker").exists()
    assert removed == [stale]
    assert not stale.exists()
    assert fresh.exists()
