"""数据布局契约（ARCH-019 统一数据根）：
- 共享树 <QED_DATA_ROOT>/：raw/<domain>/<course>/ 原始区、tmp/qed-tracker/downloads/ 下载临时区；
- 私有状态区 <QED_DATA_ROOT>/qed-tracker/meta/（resources JSON / selections / tasks）;
- `<slug>_<sha256前8>.pdf` 文件名规则与 md5 内容校验回归。
- QED-071 A-W4 局部反岛守护：Axiom 传输留痕全仓零写入 + staging 年龄清扫挂载。
"""

import hashlib
import os
import time
from pathlib import Path

import httpx
import pytest

from qed_tracker.application import BookService, ResourceService
from qed_tracker.application.papers import PaperService
from qed_tracker.catalog import Catalog, load_catalog
from qed_tracker.downloader import DownloadError, DownloadManager
from qed_tracker.inventory import Inventory, downloads_tmp_dir, raw_course_dir, raw_general_dir, sweep_downloads
from qed_tracker.models import Candidate, ResourceKind

REPO_ROOT = Path(__file__).resolve().parents[1]


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


def _candidate(title: str = "Topology 2nd Edition", identifiers: dict | None = None) -> Candidate:
    return Candidate(
        "fake", "munkres", title, ("James Munkres",), "English",
        identifiers=identifiers or {}, download_url="https://example.test/topology.pdf",
    )


def test_layout_helpers_follow_shared_tree(tmp_path):
    """ARCH-019 派生路径表：raw 课程桶 / 领域通用桶 / QED-Tracker 下载临时区。"""
    assert raw_course_dir(tmp_path, "01_math_analysis") == tmp_path / "raw" / "math" / "01_math_analysis"
    assert raw_general_dir(tmp_path) == tmp_path / "raw" / "math" / "_general"
    assert downloads_tmp_dir(tmp_path) == tmp_path / "tmp" / "qed-tracker" / "downloads"


def test_inventory_state_lives_under_private_meta(tmp_path, pdf_bytes):
    path = tmp_path / "book.pdf"
    path.write_bytes(pdf_bytes)
    inventory = Inventory(tmp_path)
    record = inventory.register(path, kind=ResourceKind.BOOK, title="Book")
    assert (tmp_path / "qed-tracker" / "meta" / "resources" / f"{record.sha256}.json").exists()
    assert not (tmp_path / "meta").exists()


def test_downloaded_book_uses_sha256_filename_rule(tmp_path, pdf_bytes):
    manager = _manager_with(pdf_bytes)
    service = ResourceService(Inventory(tmp_path), manager)
    try:
        record = service.download_candidate(
            _candidate(), kind=ResourceKind.BOOK, destination_dir=raw_general_dir(tmp_path)
        )
    finally:
        service.close()
    expected = raw_general_dir(tmp_path) / f"Topology_2nd_Edition_{record.sha256[:8]}.pdf"
    assert expected.exists()
    assert record.file["relative_path"] == expected.relative_to(tmp_path).as_posix()


def test_staging_and_part_files_live_in_shared_tmp_zone(tmp_path, pdf_bytes):
    """"tmp 先写后原子落盘 raw"：.download/.part 中间态只在 tmp/qed-tracker/downloads/，
    成品直接原子替换进 raw；完成后临时区无残留。"""

    manager = _manager_with(pdf_bytes)
    service = ResourceService(Inventory(tmp_path), manager)
    try:
        record = service.download_candidate(
            _candidate(), kind=ResourceKind.BOOK, destination_dir=raw_general_dir(tmp_path)
        )
    finally:
        service.close()
    tmp_zone = downloads_tmp_dir(tmp_path)
    assert record.file["sha256"]
    assert not list(tmp_zone.glob("*")), "下载完成后临时区应无残留"
    assert not list(raw_general_dir(tmp_path).glob("*.download")), "raw 区不得有中间态文件"


def test_download_rejects_mismatched_declared_md5(tmp_path, pdf_bytes):
    """2026-08-09：archive resolve 声明的 md5 与实际下载内容不一致时拒绝登记并清理 staging。"""

    manager = _manager_with(pdf_bytes)
    candidate = _candidate(identifiers={"md5": "0" * 32})
    service = ResourceService(Inventory(tmp_path), manager)
    try:
        with pytest.raises(DownloadError, match="内容完整性校验失败"):
            service.download_candidate(candidate, kind=ResourceKind.BOOK, destination_dir=raw_general_dir(tmp_path))
    finally:
        service.close()
    assert not list(downloads_tmp_dir(tmp_path).glob("*.download")), "staging 文件应被清理"


def test_download_accepts_matching_declared_md5(tmp_path, pdf_bytes):
    """md5 与下载内容一致时正常登记。"""

    declared = hashlib.md5(pdf_bytes).hexdigest()
    manager = _manager_with(pdf_bytes)
    service = ResourceService(Inventory(tmp_path), manager)
    try:
        record = service.download_candidate(
            _candidate(identifiers={"md5": declared}), kind=ResourceKind.BOOK, destination_dir=raw_general_dir(tmp_path)
        )
    finally:
        service.close()
    assert record.file["sha256"]


def test_run_catalog_course_filter_matches_semantic_course_id(tmp_path, pdf_bytes):
    """QED-062：catalog run 的 course 过滤按语义 course_id 精确匹配（不再用编号前缀）。"""
    catalog = load_catalog("math-qe")
    manager = _manager_with(pdf_bytes)
    service = BookService([FakeProvider(_candidate())], ResourceService(Inventory(tmp_path), manager))
    try:
        attempts = service.run_catalog(catalog, course="math_analysis")
    finally:
        service.close()
    assert len(attempts) == 13
    assert {attempt.target.course_id for attempt in attempts} == {"math_analysis"}

    manager = _manager_with(pdf_bytes)
    service = BookService([FakeProvider(_candidate())], ResourceService(Inventory(tmp_path), manager))
    try:
        none_attempts = service.run_catalog(catalog, course="math")
    finally:
        service.close()
    assert none_attempts == []


def test_catalog_book_lands_in_raw_domain_course_bucket(tmp_path, pdf_bytes):
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
    assert raw_course_dir(tmp_path, "topology").exists()


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
    service = PaperService(FakeArxiv(), ResourceService(Inventory(tmp_path), manager))
    try:
        record = service.download(candidate)
    finally:
        service.close()
    expected = raw_general_dir(tmp_path) / "papers" / "2024" / f"2401.00001_{record.sha256[:8]}.pdf"
    assert expected.exists()


def test_paper_download_uses_arxiv_id_filename_rule(tmp_path, pdf_bytes):
    candidate = Candidate(
        "arxiv", "2401.00001", "A Paper", (), "en", identifiers={"arxiv": "2401.00001"},
        download_url="https://example.test/paper.pdf",
    )
    manager = _manager_with(pdf_bytes)
    service = ResourceService(Inventory(tmp_path), manager)
    try:
        record = service.download_candidate(
            candidate, kind=ResourceKind.PAPER,
            destination_dir=raw_general_dir(tmp_path) / "papers" / "2024",
        )
    finally:
        service.close()
    expected = raw_general_dir(tmp_path) / "papers" / "2024" / f"2401.00001_{record.sha256[:8]}.pdf"
    assert expected.exists()


def test_same_title_different_targets_get_distinct_filenames(tmp_path, pdf_bytes):
    """2026-08-09 回归：同条目多目标 title 相同（陈纪修上/下/答案），
    catalog_target.id 前缀保证 staging/final 不互相冲突（原并发写同名 WinError 32）。"""

    from io import BytesIO

    from pypdf import PdfWriter

    from qed_tracker.models import CatalogTarget

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=200)
    stream = BytesIO()
    writer.write(stream)
    other_pdf = stream.getvalue()

    targets = [
        CatalogTarget("01-chenjixiu-v1", "01_math_analysis", "数学分析", ResourceKind.BOOK, "数学分析", ("陈纪修",), "zh", file_hint="第三版 上"),
        CatalogTarget("01-chenjixiu-v2", "01_math_analysis", "数学分析", ResourceKind.BOOK, "数学分析", ("陈纪修",), "zh", file_hint="第三版 下"),
    ]
    destination = raw_course_dir(tmp_path, "01_math_analysis")
    service = ResourceService(Inventory(tmp_path), _manager_with(pdf_bytes))
    try:
        service.download_candidate(
            _candidate(title="数学分析 陈纪修 第三版 课本及答案"),
            kind=ResourceKind.BOOK,
            destination_dir=destination,
            catalog_target=targets[0],
        )
    finally:
        service.close()
    service = ResourceService(Inventory(tmp_path), _manager_with(other_pdf))
    try:
        service.download_candidate(
            _candidate(title="数学分析 陈纪修 第三版 课本及答案"),
            kind=ResourceKind.BOOK,
            destination_dir=destination,
            catalog_target=targets[1],
        )
    finally:
        service.close()
    names = sorted(p.name for p in destination.glob("*.pdf"))
    assert names[0].startswith("01-chenjixiu-v1_")
    assert names[1].startswith("01-chenjixiu-v2_")
    assert names[0] != names[1]


def test_exercise_download_lands_in_general_bucket(tmp_path, pdf_bytes):
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
    assert raw_general_dir(tmp_path).exists()


# ---- QED-071 A-W4：局部反岛守护（全局 qed-tracker/ 断言留 B 轮） ----


def test_source_never_writes_axiom_transfer_island():
    """① src/ 全仓不出现 meta/transfers 字符串——Axiom 传输留痕已判废（D3），
    任何新增写入路径都会重建野生区，违反根仓 ADR 0018。"""
    offenders = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in sorted((REPO_ROOT / "src").rglob("*.py"))
        if "meta/transfers" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_inventory_and_sweep_never_create_axiom_trace_dir(tmp_path, pdf_bytes):
    """② 构造 Inventory + 登记 + 跑完 A-W2 清扫：Axiom 传输留痕目录不生成，
    tmp/qed-tracker/downloads/ 终态符合预期（超龄清掉、新鲜保留）。"""
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(pdf_bytes)
    inventory = Inventory(tmp_path)
    inventory.register(pdf, kind=ResourceKind.BOOK, title="Book")

    staging = downloads_tmp_dir(tmp_path)
    staging.mkdir(parents=True)
    stale = staging / "Orphan_deadbeef.download"
    stale.write_bytes(b"stale")
    stamp = time.time() - 24 * 3600
    os.utime(stale, (stamp, stamp))
    fresh = staging / "InFlight_01234567.download"
    fresh.write_bytes(b"fresh")

    removed = sweep_downloads(staging, max_age_seconds=6 * 3600)

    assert not (tmp_path / "qed-tracker" / "meta" / "transfers").exists()
    assert removed == [stale]
    assert not stale.exists()
    assert fresh.exists()
