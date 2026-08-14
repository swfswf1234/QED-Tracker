"""教材搜索、选择和冻结目录批处理用例。"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from contextlib import ExitStack
from dataclasses import dataclass

from qed_tracker.application.resources import ResourceService
from qed_tracker.catalog import Catalog
from qed_tracker.matching import match_candidate
from qed_tracker.models import Candidate, CatalogTarget, MatchResult, ResourceKind, ResourceRecord
from qed_tracker.providers.books import BookProvider, ProviderError

logger = logging.getLogger("qed_tracker.books")


def _set_no_of_note(note: str) -> str:
    """catalog target note 里的「套一/套二/套三」→ "1"/"2"/"3"（无则空串）。"""
    digits = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5"}
    for key, value in digits.items():
        if f"套{key}" in note:
            return value
    return ""


def _vol_suffix_of_target(target_id: str) -> str:
    """target_id 尾部卷标记（-v1/-answers/-上 等）→ 卷后缀；无卷返回空串。"""
    tail = target_id.rsplit("-", 1)[-1]
    if tail.startswith("v") or tail in ("answers", "上册", "下册", "上", "下", "missing"):
        return tail
    return ""


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
    def __init__(self, providers: Iterable[BookProvider], resources: ResourceService, three_table=None):
        self.providers = list(providers)
        self.resources = resources
        # QED-030：CLI 下载流登记（可选注入；无 DB 时仅文件 + 本地清单，行为不变）
        self.three_table = three_table
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
        if kind == ResourceKind.EXERCISE:
            destination = root / "raw" / "exercises" / "inbox"
        elif catalog_target:
            destination = root / "raw" / "books" / catalog_id / catalog_target.course_id
        else:
            destination = root / "raw" / "books" / "inbox"
        record = self.resources.download_candidate(
            resolved, kind=kind, destination_dir=destination, catalog_target=catalog_target
        )
        # QED-030：三表登记（定位失败静默——文件已落盘，仅缺登记；例外吞掉不阻断下载结果）
        if self.three_table is not None and catalog_target is not None:
            try:
                self.three_table.record_book_download(
                    course_id=catalog_target.course_id,
                    set_no=_set_no_of_note(catalog_target.note),
                    title_hint=catalog_target.title,
                    vol_suffix=_vol_suffix_of_target(catalog_target.id),
                    sha256=record.sha256,
                    relative_path=record.file["relative_path"],
                    page_count=record.file.get("page_count", 0),
                    channel=resolved.provider,
                    provider_id=resolved.provider_id,
                    download_url=resolved.download_url or "",
                )
            except Exception as exc:  # noqa: BLE001 - 登记失败不影响下载结果，记日志
                logger.warning("三表登记失败（target=%s）：%s", catalog_target.id, exc)
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
