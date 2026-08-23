"""教材搜索、选择和冻结目录批处理用例。"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from contextlib import ExitStack
from dataclasses import dataclass

from qed_tracker.application.resources import ResourceService
from qed_tracker.catalog import Catalog
from qed_tracker.inventory import raw_course_dir, raw_general_dir
from qed_tracker.matching import match_candidate
from qed_tracker.models import Candidate, CatalogTarget, MatchResult, ResourceKind, ResourceRecord
from qed_tracker.providers.books import BookProvider, ProviderError

logger = logging.getLogger("qed_tracker.books")


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


class BookService:
    def __init__(self, providers: Iterable[BookProvider], resources: ResourceService):
        self.providers = list(providers)
        self.resources = resources
        self.failures: list[tuple[str, str]] = []

    def close(self) -> None:
        with ExitStack() as stack:
            stack.callback(self.resources.close)
            for provider in self.providers:
                stack.callback(provider.close)

    def search(self, query: str, *, limit: int = 10, target: CatalogTarget | None = None) -> list[RankedCandidate]:
        self.failures = []
        results: list[RankedCandidate] = []
        seen: set[tuple[str, str, str]] = set()
        for provider in self.providers:
            try:
                candidates = provider.search(query, limit)
            except Exception as exc:
                self.failures.append((provider.name, str(exc)))
                logger.warning("来源搜索失败：provider=%s query=%r error=%s", provider.name, query, exc)
                continue
            for candidate in candidates:
                key = (candidate.provider, candidate.provider_id, candidate.title.casefold())
                if key in seen:
                    continue
                seen.add(key)
                results.append(RankedCandidate(candidate, match_candidate(candidate, target) if target else None))
        if target:

            def _rank(item: RankedCandidate) -> tuple:
                strict = bool(item.match and item.match.strict)
                score = -(item.match.score if item.match else 0)
                if target.file_hint:
                    # QED-019/021 file_hint 语义依赖 archive 条目真实文件名选文件；
                    # 2026-08-09：libgen 等 metadata_only 命中同样 strict，但 resolve 只有
                    # links 无 download_url、也无法按 file_hint 选文件（下载必然失败），
                    # 故 strict 组内优先 internet_archive。
                    return (
                        not strict,
                        strict and item.candidate.provider != "internet_archive",
                        score,
                        item.candidate.title.casefold(),
                    )
                return (not strict, score, item.candidate.title.casefold())

            results.sort(key=_rank)
        else:
            results.sort(
                key=lambda item: (item.candidate.availability != "downloadable", item.candidate.title.casefold())
            )
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
        root = self.resources.inventory.data_root
        # ARCH-019 共享布局：课程桶 raw/<domain>/<course>/；inbox/习题入领域通用桶 _general/。
        if kind == ResourceKind.EXERCISE:
            destination = raw_general_dir(root)
        elif catalog_target:
            destination = raw_course_dir(root, catalog_target.course_id)
        else:
            destination = raw_general_dir(root)
        record = self.resources.download_candidate(
            resolved, kind=kind, destination_dir=destination, catalog_target=catalog_target
        )
        return record

    def run_catalog(
        self, catalog: Catalog, *, course: str = "", download: bool = False, limit: int = 8
    ) -> list[CatalogAttempt]:
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
                attempts.append(
                    CatalogAttempt(target, "READY", f"{strict.candidate.provider}: {strict.candidate.title}")
                )
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
        lines.append(
            f"| {attempt.target.title} | {attempt.target.course_id} | {attempt.target.kind.value} | {attempt.status} | {reason} | {resource_id} |"
        )
    return "\n".join(lines) + "\n"
