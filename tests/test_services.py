"""QED-071 B 轮：ResourceService 登记语义（岛退役后 M4 门 + DB 去重 + 内存 DTO）。

原 `run_catalog` 冻结目录批处理测试（test_catalog_preview_and_strict_download /
test_catalog_does_not_auto_download_incomplete_metadata）随 D11 链路退役删除；
自动取书正源的回归覆盖在 tests/test_book_fetch.py。
"""

import hashlib
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
    """只实现 promote_staged 与 duplicate_check 用到的查询面；避免默认测试触真实 DB（隔离铁律）。"""

    def __init__(self, hit=None, title_hits=()):
        self.hit = hit
        self.title_hits = list(title_hits)
        self.calls: list[str] = []
        self.title_calls: list[tuple[tuple[str, ...], tuple[str, ...]]] = []

    def find_owned_by_sha256(self, sha256: str):
        self.calls.append(sha256)
        return self.hit

    def find_owned_by_titles(self, titles, *, exclude_book_ids=()):
        self.title_calls.append((tuple(titles), tuple(exclude_book_ids)))
        return list(self.title_hits)

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


# ---------------- 查重双报原语（QED-068 C 步 / 068-4） ----------------


def _held_row(book_id: str, title: str, sha256: str, *, kind: str = "book"):
    """qt_books owned 行摘要替身（duplicate_check 只读这几列）。"""
    return SimpleNamespace(
        book_id=book_id, title=title, kind=kind, status="downloaded",
        file_path=f"raw/math/topology/{book_id}.pdf", sha256=sha256, size_bytes=2048, page_count=3,
    )


def test_duplicate_check_returns_both_buckets(tmp_path, pdf_bytes):
    """C-3 双报：same_content＝sha256 命中行，same_name＝标题命中而哈希不同的他行。"""
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    content_hit = _held_row("math-b01", "Topology", sha)
    name_hit = _held_row("math-b02", "Topology", "e" * 64)
    repo = _StubRepo(hit=content_hit, title_hits=[name_hit])
    service = ResourceService(tmp_path, _manager(pdf_bytes), books=repo)

    report = service.duplicate_check(sha256=sha, title="Topology", exclude_book_id="math-b09")

    assert [item["book_id"] for item in report["same_content"]] == ["math-b01"]
    assert [item["book_id"] for item in report["same_name"]] == ["math-b02"]
    entry = report["same_content"][0]
    assert set(entry) == {
        "book_id", "title", "kind", "status", "file_path", "sha256", "size_bytes", "page_count",
    }
    assert entry["sha256"] == sha and entry["page_count"] == 3
    assert repo.title_calls == [(("Topology",), ("math-b09",))]


def test_duplicate_check_excludes_own_row_from_both_buckets(tmp_path, pdf_bytes):
    """重放同一本书：命中行就是自己时两桶都空——不自报冲突（exclude_book_id）。"""
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    own = _held_row("math-b09", "Topology", sha)
    service = ResourceService(tmp_path, _manager(pdf_bytes), books=_StubRepo(hit=own, title_hits=[own]))

    report = service.duplicate_check(sha256=sha, title="Topology", exclude_book_id="math-b09")

    assert report["same_content"] == [] and report["same_name"] == []


def test_duplicate_check_without_db_returns_empty_buckets(tmp_path, pdf_bytes):
    """DB 未配置：两桶恒空，双报不是落盘前置条件（download-pipeline.md「查重双报」节）。"""
    service = ResourceService(tmp_path, _manager(pdf_bytes))
    assert service.duplicate_check(sha256="a" * 64, title="Topology") == {"same_content": [], "same_name": []}


def test_duplicate_check_skips_queries_when_identity_or_title_missing(tmp_path, pdf_bytes):
    """空 sha256 不查内容、空标题不查标题：避免无条件全表命中。"""
    repo = _StubRepo()
    service = ResourceService(tmp_path, _manager(pdf_bytes), books=repo)

    assert service.duplicate_check(sha256="", title="Topology")["same_content"] == []
    assert repo.calls == [] and repo.title_calls == [(("Topology",), ())]
    assert service.duplicate_check(sha256="b" * 64, title="  ")["same_name"] == []
    assert repo.calls == ["b" * 64] and len(repo.title_calls) == 1
