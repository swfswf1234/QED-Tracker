"""内容身份磁盘重算回填与对账用例（QED-071 B-W2，`inventory reconcile` 后端）。

输入为 `qt_books` holding=owned 书目行：逐本对数据根内 PDF 重算
sha256/size_bytes/page_count 并回填三列（唯一写点 `set_content_identity`）。
与已回填列或 `qt_sources.note` 记录的 sha8 不符时**不覆盖**，报 mismatch 人工裁；
磁盘库约束拒绝（如生产未放宽旧唯一键，D17）报 conflict。无法归属书目的 PDF（论文/`_general/` 杂件）只统计
不回填（裁决 D2/D14：论文承载面另行裁定）。

真实数据根执行属 D 类操作；默认测试只用 tmp_path。
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any

from qed_tracker.db.knowledge_repository import KnowledgeRepository
from qed_tracker.downloader import inspect_pdf

# qt_sources.note 留痕两种形态：`sha256:<64hex>`（resource_id）与 `sha256 <8hex>`（人工登记）。
_SHA_TOKEN = re.compile(r"sha256[:\s]+([0-9a-fA-F]{8,64})")

# 需要人工介入/未回填成功的状态；CLI 存在任一项时非 0 退出。
UNRECONCILED_STATUSES = frozenset({"missing", "invalid", "mismatch", "conflict"})


def _recorded_sha8s(repo: KnowledgeRepository, book_id: str) -> list[str]:
    values: list[str] = []
    for source in repo.list_sources(book_id):
        for token in _SHA_TOKEN.findall(source.note or ""):
            values.append(token.lower()[:8])
    return values


def _resolve_in_root(root: Path, relative: str) -> Path | None:
    """数据根相对路径解析；越出数据根（含符号链接逃逸）视为不可用。"""
    try:
        path = (root / relative).resolve()
        path.relative_to(root)
    except ValueError:
        return None
    return path


def reconcile_content_identity(repo: KnowledgeRepository, data_root: Path) -> dict[str, Any]:
    root = data_root.resolve()
    items: list[dict[str, Any]] = []
    counters = {"total": 0, "filled": 0, "ok": 0, "missing": 0, "invalid": 0, "mismatch": 0, "conflict": 0}
    referenced: set[str] = set()
    for book in repo.owned_books_with_files():
        counters["total"] += 1
        rel = (book.file_path or "").strip()
        referenced.add(PurePosixPath(rel.replace("\\", "/")).as_posix())
        item: dict[str, Any] = {"book_id": book.book_id, "file_path": rel, "status": ""}
        path = _resolve_in_root(root, rel)
        if path is None or not path.is_file():
            item["status"] = "missing"
        else:
            try:
                digest, size, pages = inspect_pdf(path)
            except Exception as exc:  # noqa: BLE001 - 单本不可读不阻断整批对账
                item["status"] = "invalid"
                item["detail"] = str(exc)[:300]
            else:
                item.update({"sha256": digest, "size_bytes": size, "page_count": pages})
                item["status"] = _reconcile_book(repo, book, item)
        counters[item["status"]] += 1
        items.append(item)

    unattributed_files = _unattributed_pdfs(root, referenced)
    return {
        "summary": {**counters, "unattributed": len(unattributed_files)},
        "items": items,
        "unattributed": {"count": len(unattributed_files), "files": unattributed_files},
    }


def _reconcile_book(repo: KnowledgeRepository, book: Any, item: dict[str, Any]) -> str:
    digest, size, pages = item["sha256"], item["size_bytes"], item["page_count"]
    if book.sha256:
        if book.sha256 == digest and book.size_bytes == size and book.page_count == pages:
            return "ok"
        item["recorded_sha8"] = book.sha256[:8]
        return "mismatch"
    recorded = _recorded_sha8s(repo, book.book_id)
    if recorded and digest[:8] not in recorded:
        item["recorded_sha8"] = recorded[0]
        return "mismatch"
    try:
        repo.set_content_identity(book.book_id, sha256=digest, size_bytes=size, page_count=pages)
    except ValueError:
        return "conflict"
    return "filled"


def _unattributed_pdfs(root: Path, referenced: set[str]) -> list[str]:
    """raw/ 成品区未被任何 owned 书目引用的 PDF：只统计清单，不登记（D2）。"""
    raw = root / "raw"
    if not raw.is_dir():
        return []
    found: list[str] = []
    for path in sorted(raw.rglob("*.pdf")):
        relative = path.resolve().relative_to(root).as_posix()
        if relative not in referenced:
            found.append(relative)
    return found
