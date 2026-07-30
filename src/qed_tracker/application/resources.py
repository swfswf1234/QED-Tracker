"""共享下载与资源登记用例。"""

from __future__ import annotations

from pathlib import Path

from qed_tracker.downloader import DownloadManager, safe_filename
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
        if not candidate.download_url:
            raise ValueError("候选没有可下载 URL")
        prefix = candidate.identifiers.get("arxiv", "")
        basename = f"{prefix}_{candidate.title}" if prefix else candidate.title
        destination = destination_dir / safe_filename(basename)
        suffix = 2
        while destination.exists():
            destination = destination_dir / f"{Path(safe_filename(basename)).stem}-{suffix}.pdf"
            suffix += 1
        downloaded = self.downloader.download(candidate.download_url, destination)
        existing = self.inventory.get(downloaded.sha256)
        if (
            existing
            and existing.absolute_path(self.inventory.data_root).exists()
            and existing.absolute_path(self.inventory.data_root) != downloaded.path.resolve()
        ):
            downloaded.path.unlink(missing_ok=True)
            return existing
        return self.inventory.register_candidate(downloaded, candidate, kind, catalog_target)
