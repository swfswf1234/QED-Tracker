"""QED-071 B-W2 `inventory reconcile`：内容身份磁盘重算回填与对账（SQLite + tmp_path 隔离）。

契约（计划 2026-09-24-storage-json-island-retirement B-W2）：
- 输入 = qt_books `holding=owned` 且 `file_path` 非空的书目行；
- 逐本 `inspect_pdf` 重算三列（sha256/size_bytes/page_count）并回填；
- 分类：filled（本次写入）/ ok（已一致）/ missing（文件缺失）/ invalid（不可读）/
  mismatch（与已回填列或 qt_sources.note 记录的 sha8 不符，人工裁，不写）/
  conflict（唯一键被另一行占用，不写）；
- 无法归属书目的 PDF（`_general/` 等）只统计不回填（D2）；
- CLI `qed-tracker inventory reconcile --json`：exit 0 全绿 / 4 存在非 ok 类 / 2 数据库未配置。
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.application.reconcile import reconcile_content_identity
from qed_tracker.db.engine import utc_now
from qed_tracker.db.knowledge_repository import KnowledgeRepository
from qed_tracker.db.models import Base, QedCourse, QedDomain


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    now = utc_now()
    session.add(QedDomain(domain_id="math", name="数学", description="d",
                          stages=["基础"], created_at=now, updated_at=now))
    session.add(QedCourse(course_id="math_analysis", domain_id="math", sort_order=1, name="数学分析",
                          aliases=[], stage="基础", prerequisites=[], related_targets=[],
                          created_at=now, updated_at=now))
    session.commit()
    yield KnowledgeRepository(factory)
    engine.dispose()


def _seed_owned(repo: KnowledgeRepository, tmp_path, pdf_bytes: bytes, *,
                book_id: str = "mathanalysis-b01",
                rel: str = "raw/math/math_analysis/数学分析原理.pdf"):
    repo.create_book(book_id, title="数学分析原理", part="", roles=["textbook"],
                     authors=[], language="zh", domain_id="math")
    repo.mark_owned(book_id, file_path=rel, status="downloaded")
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(pdf_bytes)
    return book_id, rel


def _digest(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


# ---------------- 核心回填语义 ----------------


def test_reconcile_fills_identity_columns(repo, tmp_path, pdf_bytes):
    book_id, rel = _seed_owned(repo, tmp_path, pdf_bytes)
    report = reconcile_content_identity(repo, tmp_path)
    item = next(i for i in report["items"] if i["book_id"] == book_id)
    assert item["status"] == "filled"
    assert item["sha256"] == _digest(pdf_bytes)
    assert item["size_bytes"] == len(pdf_bytes)
    assert item["page_count"] == 1
    assert report["summary"]["filled"] == 1
    row = repo.get_book(book_id)
    assert row.sha256 == _digest(pdf_bytes)
    assert row.size_bytes == len(pdf_bytes)
    assert row.page_count == 1


def test_reconcile_rerun_is_ok_without_rewrite(repo, tmp_path, pdf_bytes):
    _seed_owned(repo, tmp_path, pdf_bytes)
    reconcile_content_identity(repo, tmp_path)
    report = reconcile_content_identity(repo, tmp_path)
    assert report["items"][0]["status"] == "ok"
    assert report["summary"]["ok"] == 1
    assert report["summary"]["filled"] == 0


def test_reconcile_missing_file_keeps_columns_null(repo, tmp_path, pdf_bytes):
    book_id, _ = _seed_owned(repo, tmp_path, pdf_bytes)
    (tmp_path / "raw/math/math_analysis/数学分析原理.pdf").unlink()
    report = reconcile_content_identity(repo, tmp_path)
    assert report["items"][0]["status"] == "missing"
    assert repo.get_book(book_id).sha256 is None


def test_reconcile_invalid_pdf_is_not_filled(repo, tmp_path):
    repo.create_book("b01", title="坏文件", part="", roles=["textbook"],
                     authors=[], language="zh", domain_id="math")
    repo.mark_owned("b01", file_path="raw/math/math_analysis/坏.pdf", status="downloaded")
    target = tmp_path / "raw/math/math_analysis/坏.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"not a pdf")
    report = reconcile_content_identity(repo, tmp_path)
    assert report["items"][0]["status"] == "invalid"
    assert repo.get_book("b01").sha256 is None


def test_reconcile_path_escape_is_missing_not_outside_read(repo, tmp_path, pdf_bytes):
    repo.create_book("b01", title="越界", part="", roles=["textbook"],
                     authors=[], language="zh", domain_id="math")
    repo.mark_owned("b01", file_path="../外部.pdf", status="downloaded")
    (tmp_path.parent / "外部.pdf").write_bytes(pdf_bytes)
    report = reconcile_content_identity(repo, tmp_path)
    assert report["items"][0]["status"] == "missing"
    assert repo.get_book("b01").sha256 is None


# ---------------- sha8 对账（qt_sources.note 留痕） ----------------


def test_reconcile_note_sha8_conflict_requires_manual(repo, tmp_path, pdf_bytes):
    book_id, _ = _seed_owned(repo, tmp_path, pdf_bytes)
    repo.add_source(book_id, channel="local_import", ok=True, download_url="",
                    note="原地登记（123 bytes，1 页，sha256 deadbeef）")
    report = reconcile_content_identity(repo, tmp_path)
    item = report["items"][0]
    assert item["status"] == "mismatch"
    assert item["recorded_sha8"] == "deadbeef"
    assert item["sha256"] == _digest(pdf_bytes)  # 重算值透出供人工裁
    assert repo.get_book(book_id).sha256 is None


def test_reconcile_note_sha8_full_digest_matches_and_fills(repo, tmp_path, pdf_bytes):
    book_id, _ = _seed_owned(repo, tmp_path, pdf_bytes)
    repo.add_source(book_id, channel="libgen_li", ok=True, download_url="",
                    note=f"sha256:{_digest(pdf_bytes)}；内容校验 score=1.00")
    report = reconcile_content_identity(repo, tmp_path)
    assert report["items"][0]["status"] == "filled"
    assert repo.get_book(book_id).sha256 == _digest(pdf_bytes)


def test_reconcile_filled_column_conflict_is_mismatch(repo, tmp_path, pdf_bytes, text_pdf_bytes):
    book_id, rel = _seed_owned(repo, tmp_path, pdf_bytes)
    repo.set_content_identity(book_id, sha256="0" * 64, size_bytes=1, page_count=1)
    report = reconcile_content_identity(repo, tmp_path)
    item = report["items"][0]
    assert item["status"] == "mismatch"
    assert item["recorded_sha8"] == "00000000"
    # 不覆盖已回填列，也不与 text_pdf_bytes 相关（该夹具仅确保两内容可区分）
    assert repo.get_book(book_id).sha256 == "0" * 64


def test_reconcile_same_content_two_books_both_fill(repo, tmp_path, pdf_bytes):
    """D17（2026-09-26）：sha256 放宽为普通索引后，同内容多书各行独立回填（N:1 共用，
    与资源岛旧语义等价）；原「唯一键冲突 → conflict」口径作废。"""
    _seed_owned(repo, tmp_path, pdf_bytes, book_id="a-b01",
                rel="raw/math/math_analysis/A.pdf")
    _seed_owned(repo, tmp_path, pdf_bytes, book_id="b-b01",
                rel="raw/math/math_analysis/B.pdf")
    report = reconcile_content_identity(repo, tmp_path)
    statuses = {i["book_id"]: i["status"] for i in report["items"]}
    assert statuses == {"a-b01": "filled", "b-b01": "filled"}
    assert repo.get_book("a-b01").sha256 == _digest(pdf_bytes)
    assert repo.get_book("b-b01").sha256 == _digest(pdf_bytes)


# ---------------- 无归属 PDF 只统计（D2） ----------------


def test_reconcile_counts_unattributed_pdfs_only(repo, tmp_path, pdf_bytes):
    _seed_owned(repo, tmp_path, pdf_bytes)
    stray = tmp_path / "raw/math/_general/papers/2024/orphan.pdf"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(pdf_bytes)
    report = reconcile_content_identity(repo, tmp_path)
    assert report["unattributed"]["count"] == 1
    assert "raw/math/_general/papers/2024/orphan.pdf" in report["unattributed"]["files"]
    # 只统计：不落任何登记
    assert report["summary"]["filled"] == 1
    assert repo.get_book("mathanalysis-b01").sha256 is not None


def test_reconcile_non_pdf_files_ignored(tmp_path, repo):
    other = tmp_path / "raw/math/_general/notes.txt"
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text("x", encoding="utf-8")
    report = reconcile_content_identity(repo, tmp_path)
    assert report["unattributed"]["count"] == 0


# ---------------- CLI 契约（exit 码 + --json 输出 book_id） ----------------


def _inventory_args(**overrides):
    base = {"inventory_command": "reconcile", "json": True}
    base.update(overrides)
    return SimpleNamespace(**base)


def _cli_settings(tmp_path):
    from qed_tracker.config import Settings

    return Settings(data_root=tmp_path)


def test_cli_inventory_reconcile_success_json_book_id(monkeypatch, repo, tmp_path, pdf_bytes, capsys):
    import qed_tracker.cli as cli_module

    _seed_owned(repo, tmp_path, pdf_bytes)
    monkeypatch.setattr(cli_module, "_curriculum_repository", lambda settings: repo)
    assert cli_module._inventory(_inventory_args(), _cli_settings(tmp_path)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["items"][0]["book_id"] == "mathanalysis-b01"
    assert "resource_id" not in payload["items"][0]


def test_cli_inventory_reconcile_returns_4_on_mismatch(monkeypatch, repo, tmp_path, pdf_bytes, capsys):
    import qed_tracker.cli as cli_module

    _seed_owned(repo, tmp_path, pdf_bytes)
    (tmp_path / "raw/math/math_analysis/数学分析原理.pdf").unlink()
    monkeypatch.setattr(cli_module, "_curriculum_repository", lambda settings: repo)
    assert cli_module._inventory(_inventory_args(), _cli_settings(tmp_path)) == 4


def test_cli_inventory_reconcile_requires_db(monkeypatch, tmp_path, capsys):
    import qed_tracker.cli as cli_module

    monkeypatch.setattr(cli_module, "_curriculum_repository", lambda settings: None)
    assert cli_module._inventory(_inventory_args(json=False), _cli_settings(tmp_path)) == 2
    assert "数据库未配置" in capsys.readouterr().err
