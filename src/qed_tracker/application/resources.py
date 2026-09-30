"""共享下载与资源登记用例。

QED-071 B 轮（拆岛收口）：本模块不再读写 `<data_root>/qed-tracker/meta/resources/`
资源 JSON 岛——书侧内容身份只存 `qt_books` 三列（sha256/size_bytes/page_count），
去重经 `ix_qt_books_sha256` 索引（D17：同内容多书 N:1 共用）；`ResourceRecord` 退化为内存 DTO（D12）。
kind=book 路径必须有 `KnowledgeRepository`（M4：DB 不可用显式报错，绝不回落岛读）；
paper/exercise 只落盘 + 内存 DTO，不进 qt_books（D2/D14）。
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from qed_tracker.downloader import DownloadedFile, DownloadError, DownloadManager, safe_filename
from qed_tracker.inventory import downloads_tmp_dir
from qed_tracker.models import Candidate, ResourceKind, ResourceRecord

if TYPE_CHECKING:
    from qed_tracker.db.knowledge_repository import KnowledgeRepository
    from qed_tracker.db.models import QtBook


class ResourceService:
    def __init__(
        self,
        data_root: Path,
        downloader: DownloadManager,
        *,
        books: KnowledgeRepository | None = None,
    ):
        self.data_root = Path(data_root).resolve()
        self.downloader = downloader
        self.books = books

    def close(self) -> None:
        self.downloader.close()

    def download_candidate(
        self,
        candidate: Candidate,
        *,
        kind: ResourceKind,
        destination_dir: Path,
        staging_tag: str = "",
        on_start: Callable[[], None] | None = None,
    ) -> ResourceRecord:
        if not isinstance(kind, ResourceKind):
            kind = ResourceKind(kind)
        if kind == ResourceKind.BOOK and self.books is None:
            raise ValueError("数据库未配置：教材下载需 qt_books 内容身份列（QED-071 B 轮）")
        if not candidate.download_url:
            raise ValueError("候选没有可下载 URL")
        staged = self.stage_download(candidate, staging_tag=staging_tag, on_start=on_start)
        return self.promote_staged(staged, candidate, kind=kind, destination_dir=destination_dir)

    @staticmethod
    def _candidate_slug(candidate: Candidate) -> str:
        """文件名规则：教材/习题为标题 slug、论文为 arXiv ID；内容指纹保证同名同内容必然同路径。

        D11（2026-09-26）：catalog_target 前缀随冻结目录 run 链路退役——并发同名冲突
        已由 staging_tag（stage_download 中间名唯一）覆盖，成品名保持内容指纹确定性。
        """
        if candidate.identifiers.get("arxiv"):
            return candidate.identifiers["arxiv"]
        return Path(safe_filename(candidate.title)).stem

    def stage_download(
        self,
        candidate: Candidate,
        *,
        staging_tag: str = "",
        on_start: Callable[[], None] | None = None,
    ) -> DownloadedFile:
        """下载到共享下载临时区（tmp，先写后原子落盘 raw），执行来源声明 md5 校验。

        staging_tag 使每次尝试的中间文件名唯一（2026-08-28）：超时放弃的孤儿下载线程
        不会与后续候选写同名 .download/.part 文件。on_start 见 DownloadManager.download。
        """
        if not candidate.download_url:
            raise ValueError("候选没有可下载 URL")
        slug = self._candidate_slug(candidate)
        if staging_tag:
            slug = f"{slug}_{staging_tag}"
        # ARCH-019：staging 中间态统一放共享下载临时区（tmp 先写后原子落盘 raw）。
        staging_dir = downloads_tmp_dir(self.data_root)
        staging = staging_dir / f"{slug}.download"
        downloaded = self.downloader.download(candidate.download_url, staging, on_start=on_start)
        # 2026-08-09：来源声明 md5 的内容完整性校验（archive metadata 提供）。
        # resolve 已把所选文件的 md5 记入 identifiers["md5"]；不一致说明下载内容
        # 与来源文件不符（并发污染/CDN 错配），拒绝登记并清理。
        expected_md5 = (candidate.identifiers or {}).get("md5") or ""
        if expected_md5:
            digest = hashlib.md5()
            with downloaded.path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected_md5:
                downloaded.path.unlink(missing_ok=True)
                raise DownloadError(f"内容完整性校验失败：来源声明 md5={expected_md5}，实际 {digest.hexdigest()}")
        return downloaded

    def promote_staged(
        self,
        staged: DownloadedFile,
        candidate: Candidate,
        *,
        kind: ResourceKind,
        destination_dir: Path,
    ) -> ResourceRecord:
        """staging 成品原子落盘 raw/，返回内存 ResourceRecord DTO（不再写资源 JSON 岛）。

        书侧去重 = `qt_books` sha256 命中 owned 行且文件在位 → 复用既有记录、删除本次
        staging；paper/exercise 不落 DB（D2/D14），同内容由调用方按各自语义处置。
        final 名不含 staging_tag（内容指纹确定性：同内容必同路径）；机器验收门
        （book_fetch.py 阶段4）应在调用本方法前于 staged.path 上执行。
        """
        if not isinstance(kind, ResourceKind):
            kind = ResourceKind(kind)
        if kind == ResourceKind.BOOK:
            if self.books is None:
                raise ValueError("数据库未配置：教材登记需 qt_books 内容身份列（QED-071 B 轮）")
            hit = self.books.find_owned_by_sha256(staged.sha256)
            if hit is not None:
                existing = self.record_from_book(hit)
                if existing.absolute_path(self.data_root).exists():
                    staged.path.unlink(missing_ok=True)
                    return existing
        slug = self._candidate_slug(candidate)
        final = destination_dir / f"{slug}_{staged.sha256[:8]}.pdf"
        # ARCH-019：staging 移入共享临时区后，成品目录需在此显式创建（原由 .part 同目录 mkdir 顺带完成）。
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged.path, final)
        return self._build_record(
            candidate, kind,
            relative_path=final.relative_to(self.data_root).as_posix(),
            sha256=staged.sha256, size_bytes=staged.size_bytes, page_count=staged.page_count,
        )

    @staticmethod
    def record_from_book(row: QtBook) -> ResourceRecord:
        """qt_books 行 → 内存 ResourceRecord DTO（D12：岛退役后唯一的记录物化路径）。"""
        return ResourceRecord(
            resource_id=f"sha256:{row.sha256}" if row.sha256 else f"book:{row.book_id}",
            kind=ResourceKind.BOOK.value,
            title=row.title,
            authors=[str(entry.get("name", "")) for entry in (row.authors or []) if isinstance(entry, dict)],
            language=row.language or "",
            year=str(row.year) if row.year else "",
            identifiers={},
            source={"provider": "qt_books", "book_id": row.book_id},
            file={
                "relative_path": row.file_path or "",
                "sha256": row.sha256 or "",
                "size_bytes": row.size_bytes,
                "mime_type": "application/pdf",
                "page_count": row.page_count,
            },
            roles=list(row.roles or []),
        )

    def _build_record(
        self,
        candidate: Candidate,
        kind: ResourceKind,
        *,
        relative_path: str,
        sha256: str,
        size_bytes: int,
        page_count: int,
    ) -> ResourceRecord:
        return ResourceRecord(
            resource_id=f"sha256:{sha256}",
            kind=kind.value,
            title=candidate.title,
            authors=list(candidate.authors),
            language=candidate.language,
            year=candidate.year,
            identifiers=dict(candidate.identifiers or {}),
            source={
                "provider": candidate.provider,
                "provider_id": candidate.provider_id,
                "page_url": candidate.page_url,
                "download_url": candidate.download_url,
                "retrieved_at": datetime.now(UTC).isoformat(),
            },
            file={
                "relative_path": relative_path,
                "sha256": sha256,
                "size_bytes": size_bytes,
                "mime_type": "application/pdf",
                "page_count": page_count,
            },
        )
