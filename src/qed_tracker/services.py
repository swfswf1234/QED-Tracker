"""搜索、选择、下载和冻结目录批处理用例。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from qed_tracker.catalog import Catalog
from qed_tracker.downloader import DownloadManager, safe_filename
from qed_tracker.inventory import Inventory
from qed_tracker.matching import match_candidate
from qed_tracker.models import Candidate, CatalogTarget, MatchResult, ResourceKind, ResourceRecord
from qed_tracker.providers.books import BookProvider, ProviderError


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    candidate: Candidate
    match: MatchResult | None = None


@dataclass(frozen=True, slots=True)
class CatalogAttempt:
    target: CatalogTarget
    status: str
    reason: str
    record: ResourceRecord | None = None


class ResourceService:
    def __init__(self, inventory: Inventory, downloader: DownloadManager):
        self.inventory = inventory
        self.downloader = downloader

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
        if existing and existing.absolute_path(self.inventory.data_root) != downloaded.path.resolve():
            downloaded.path.unlink(missing_ok=True)
            return existing
        return self.inventory.register_candidate(downloaded.path, candidate, kind, catalog_target)


class BookService:
    def __init__(self, providers: Iterable[BookProvider], resources: ResourceService):
        self.providers = list(providers)
        self.resources = resources
        self.failures: list[tuple[str, str]] = []

    def close(self) -> None:
        for provider in self.providers:
            provider.close()

    def search(self, query: str, *, limit: int = 10, target: CatalogTarget | None = None) -> list[RankedCandidate]:
        self.failures = []
        results: list[RankedCandidate] = []
        seen: set[tuple[str, str, str]] = set()
        for provider in self.providers:
            try:
                candidates = provider.search(query, limit)
            except Exception as exc:
                self.failures.append((provider.name, str(exc)))
                continue
            for candidate in candidates:
                key = (candidate.provider, candidate.provider_id, candidate.title.casefold())
                if key in seen:
                    continue
                seen.add(key)
                results.append(RankedCandidate(candidate, match_candidate(candidate, target) if target else None))
        if target:
            results.sort(key=lambda item: (not bool(item.match and item.match.strict), -(item.match.score if item.match else 0), item.candidate.title.casefold()))
        else:
            results.sort(key=lambda item: (item.candidate.availability != "downloadable", item.candidate.title.casefold()))
        return results

    def resolve(self, candidate: Candidate) -> Candidate:
        provider = next((item for item in self.providers if item.name == candidate.provider), None)
        if provider is None:
            raise ProviderError(f"来源未启用：{candidate.provider}")
        return provider.resolve(candidate)

    def download(
        self,
        candidate: Candidate,
        *,
        kind: ResourceKind = ResourceKind.BOOK,
        catalog_target: CatalogTarget | None = None,
        catalog_id: str = "",
    ) -> ResourceRecord:
        resolved = self.resolve(candidate)
        if catalog_target:
            destination = self.resources.inventory.data_root / "books" / catalog_id / catalog_target.course_id
        else:
            destination = self.resources.inventory.data_root / "books" / "inbox"
        return self.resources.download_candidate(resolved, kind=kind, destination_dir=destination, catalog_target=catalog_target)

    def run_catalog(self, catalog: Catalog, *, course: str = "", download: bool = False, limit: int = 8) -> list[CatalogAttempt]:
        attempts: list[CatalogAttempt] = []
        targets = [target for target in catalog.targets if not course or target.course_id.startswith(course.zfill(2))]
        for target in targets:
            existing = self.resources.inventory.find_by_catalog_target(catalog.id, target.id)
            if existing:
                attempts.append(CatalogAttempt(target, "EXISTS", "清单中已有该目标", existing))
                continue
            ranked = self.search(target.query or target.title, limit=limit, target=target)
            strict = next((item for item in ranked if item.match and item.match.strict), None)
            if not strict:
                reason = "没有严格匹配候选"
                if self.failures:
                    reason += "; 来源失败: " + ", ".join(name for name, _ in self.failures)
                attempts.append(CatalogAttempt(target, "REVIEW", reason))
                continue
            if not download:
                attempts.append(CatalogAttempt(target, "READY", f"{strict.candidate.provider}: {strict.candidate.title}"))
                continue
            try:
                record = self.download(strict.candidate, kind=target.kind, catalog_target=target, catalog_id=catalog.id)
                attempts.append(CatalogAttempt(target, "DOWNLOADED", strict.candidate.provider, record))
            except Exception as exc:
                attempts.append(CatalogAttempt(target, "FAILED", str(exc)))
        return attempts


def attempts_markdown(catalog: Catalog, attempts: Iterable[CatalogAttempt]) -> str:
    lines = [
        f"# {catalog.name} 下载报告",
        "",
        "| Target | Course | Kind | Status | Reason | Resource |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for attempt in attempts:
        resource_id = attempt.record.resource_id if attempt.record else "-"
        reason = attempt.reason.replace("|", "\\|")
        lines.append(f"| {attempt.target.title} | {attempt.target.course_id} | {attempt.target.kind.value} | {attempt.status} | {reason} | {resource_id} |")
    return "\n".join(lines) + "\n"
