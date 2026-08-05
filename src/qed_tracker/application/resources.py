"""共享下载与资源登记用例。"""

from __future__ import annotations

import os
from pathlib import Path

from qed_tracker.downloader import DownloadedFile, DownloadManager, safe_filename
from qed_tracker.inventory import Inventory
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
        staging = destination_dir / f"{slug}.download"
        downloaded = self.downloader.download(candidate.download_url, staging)
        existing = self.inventory.get(downloaded.sha256)
        final = destination_dir / f"{slug}_{downloaded.sha256[:8]}.pdf"
        if (
            existing
            and existing.absolute_path(self.inventory.data_root).exists()
            and existing.absolute_path(self.inventory.data_root) != final
        ):
            downloaded.path.unlink(missing_ok=True)
            return existing
        os.replace(downloaded.path, final)
        final_downloaded = DownloadedFile(final, downloaded.sha256, downloaded.size_bytes, downloaded.page_count)
        return self.inventory.register_candidate(final_downloaded, candidate, kind, catalog_target)
