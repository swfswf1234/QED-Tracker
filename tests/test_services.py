"""QED-071 B 轮：ResourceService 登记语义（岛退役后 M4 门 + DB 去重 + 内存 DTO）。

原 `run_catalog` 冻结目录批处理测试（test_catalog_preview_and_strict_download /
test_catalog_does_not_auto_download_incomplete_metadata）随 D11 链路退役删除；
自动取书正源的回归覆盖在 tests/test_book_fetch.py。
"""

from types import SimpleNamespace

import httpx
import pytest

from qed_tracker.application import ResourceService
from qed_tracker.downloader import DownloadManager, inspect_pdf
from qed_tracker.models import Candidate, ResourceKind


def _manager(pdf: bytes) -> DownloadManager:
    manager = DownloadManager(retries=1)
    manager.client.close()
    manager.client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=pdf, request=request))
    )
    return manager


def _candidate(title: str = "Topology") -> Candidate:
    return Candidate("fake", "x-1", title, ("A Author",), "en", download_url="https://example.test/t.pdf")


class _StubRepo:
    """只实现 promote_staged 用到的查询面；避免默认测试触真实 DB（隔离铁律）。"""

    def __init__(self, hit=None):
        self.hit = hit
        self.calls: list[str] = []

    def find_owned_by_sha256(self, sha256: str):
        self.calls.append(sha256)
        return self.hit


def test_book_download_without_db_raises_explicitly(tmp_path, pdf_bytes):
    """M4：kind=BOOK 且未配置 KnowledgeRepository → 显式报错，绝不回落岛读。"""
    service = ResourceService(tmp_path, _manager(pdf_bytes))
    with pytest.raises(ValueError, match="qt_books"):
        service.download_candidate(_candidate(), kind=ResourceKind.BOOK,
                                   destination_dir=tmp_path / "raw" / "math" / "c1")
    assert not (tmp_path / "qed-tracker").exists()


def test_exercise_download_needs_no_db_and_lands_in_raw(tmp_path, pdf_bytes):
    """D2/D14：exercise 不进 qt_books——落 raw/ + 内存 DTO，全程不生成岛目录。"""
    from qed_tracker.inventory import raw_general_dir

    service = ResourceService(tmp_path, _manager(pdf_bytes))
    record = service.download_candidate(_candidate("习题集"), kind=ResourceKind.EXERCISE,
                                        destination_dir=raw_general_dir(service.data_root))
    assert record.kind == "exercise"
    assert record.file["relative_path"].startswith("raw/math/_general/")
    assert record.file["sha256"]
    assert (tmp_path / record.file["relative_path"]).is_file()
    # staging 中间态终态不保留
    staging = tmp_path / "tmp" / "qed-tracker" / "downloads"
    assert not any(staging.glob("*.download*")) if staging.exists() else True
    assert not (tmp_path / "qed-tracker").exists()


def test_book_promote_dedups_via_db_owned_row(tmp_path, pdf_bytes):
    """书侧去重新语义：qt_books sha256 命中 owned 且文件在位 → 复用既有记录、删本次 staging。"""
    from qed_tracker.inventory import raw_course_dir

    destination = raw_course_dir(tmp_path, "topology")
    sha256, size, pages = inspect_pdf(_write_existing(tmp_path, pdf_bytes))
    hit = SimpleNamespace(
        book_id="math-b01", title="Topology", authors=[{"name": "A Author"}], language="en", year="",
        file_path="raw/math/topology/Topology_deadbeef.pdf", sha256=sha256, size_bytes=size, page_count=pages,
        roles=["textbook"],
    )
    service = ResourceService(tmp_path, _manager(pdf_bytes), books=_StubRepo(hit))
    record = service.download_candidate(_candidate(), kind=ResourceKind.BOOK, destination_dir=destination)
    assert record.resource_id == f"sha256:{sha256}"
    assert record.source["book_id"] == "math-b01"
    assert record.absolute_path(tmp_path).is_file()
    # 复用命中：不再落第二份文件（destination 里只有既有的那一份）
    assert [p.name for p in destination.glob("*.pdf")] == ["Topology_deadbeef.pdf"]
    assert service.books.calls == [sha256]


def test_book_promote_falls_through_when_hit_file_missing(tmp_path, pdf_bytes):
    """DB 命中但记录文件不在位 → 不复用（避免指向死路径），照常落盘新文件。"""
    from qed_tracker.inventory import raw_course_dir

    destination = raw_course_dir(tmp_path, "topology")
    sha256, size, pages = inspect_pdf(_write_existing(tmp_path, pdf_bytes))
    hit = SimpleNamespace(
        book_id="math-b01", title="Topology", authors=[], language="", year="",
        file_path="raw/math/topology/Ghost_missing.pdf", sha256=sha256, size_bytes=size, page_count=pages,
        roles=[],
    )
    service = ResourceService(tmp_path, _manager(pdf_bytes), books=_StubRepo(hit))
    record = service.download_candidate(_candidate(), kind=ResourceKind.BOOK, destination_dir=destination)
    assert record.source["provider"] == "fake"
    assert (tmp_path / record.file["relative_path"]).is_file()


def _write_existing(tmp_path, pdf_bytes):
    existing = tmp_path / "raw" / "math" / "topology" / "Topology_deadbeef.pdf"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(pdf_bytes)
    return existing
