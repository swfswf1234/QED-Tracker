"""共享下载与资源登记用例。"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from qed_tracker.downloader import DownloadedFile, DownloadError, DownloadManager, safe_filename
from qed_tracker.inventory import Inventory, downloads_tmp_dir
from qed_tracker.models import Candidate, CatalogTarget, ResourceKind, ResourceRecord


class ResourceService:
    def __init__(self, inventory: Inventory, downloader: DownloadManager):
        self.inventory = inventory
        self.downloader = downloader

    def close(self) -> None:
        self.downloader.close()

    def download_candidate(
        self,
        candidate: Candidate,
        *,
        kind: ResourceKind,
        destination_dir: Path,
        catalog_target: CatalogTarget | None = None,
        staging_tag: str = "",
    ) -> ResourceRecord:
        if not isinstance(kind, ResourceKind):
            kind = ResourceKind(kind)
        if not candidate.download_url:
            raise ValueError("候选没有可下载 URL")
        # 文件名规则：教材/习题为标题 slug、论文为 arXiv ID；内容指纹保证同名同内容必然同路径。
        if candidate.identifiers.get("arxiv"):
            slug = candidate.identifiers["arxiv"]
        else:
            slug = Path(safe_filename(candidate.title)).stem
            # 2026-08-09：同一条目多目标（如 01-chenjixiu-v1/v2/answers）title 相同，
            # staging/final 名加 catalog_target.id 前缀，避免并发下载同名互斥（WinError 32）。
            if catalog_target:
                slug = f"{catalog_target.id}_{slug}"
        # 2026-08-28（BookFetchService）：staging_tag 使每次尝试的中间文件名唯一，
        # 超时放弃的孤儿下载线程不会与后续候选写同名 .download/.part 文件。
        if staging_tag:
            slug = f"{slug}_{staging_tag}"
        # ARCH-019：staging 中间态统一放共享下载临时区（tmp 先写后原子落盘 raw）。
        staging_dir = downloads_tmp_dir(self.inventory.data_root)
        staging = staging_dir / f"{slug}.download"
        downloaded = self.downloader.download(candidate.download_url, staging)
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
        existing = self.inventory.get(downloaded.sha256)
        final = destination_dir / f"{slug}_{downloaded.sha256[:8]}.pdf"
        if (
            existing
            and existing.absolute_path(self.inventory.data_root).exists()
            and existing.absolute_path(self.inventory.data_root) != final
        ):
            downloaded.path.unlink(missing_ok=True)
            return existing
        # ARCH-019：staging 移入共享临时区后，成品目录需在此显式创建（原由 .part 同目录 mkdir 顺带完成）。
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(downloaded.path, final)
        final_downloaded = DownloadedFile(final, downloaded.sha256, downloaded.size_bytes, downloaded.page_count)
        return self.inventory.register_candidate(final_downloaded, candidate, kind, catalog_target)
