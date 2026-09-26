"""教材搜索和选择用例。

D11（QED-071 B 轮，2026-09-26）：冻结目录批处理链（`run_catalog`/`CatalogAttempt`/
`catalog_target` 路由/`find_by_catalog_target` 岛读）随资源 JSON 岛一并退役——
它只服务已归档的 math-qe 人工盘点流程；自动取书唯一正源是 `book_fetch` 五阶段编排
（qt_books 驱动）。`catalog.py`/`matching.py` 本体保留（历史资料仍可查目录）。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from contextlib import ExitStack
from dataclasses import dataclass

from qed_tracker.application.resources import ResourceService
from qed_tracker.inventory import raw_general_dir
from qed_tracker.matching import match_candidate
from qed_tracker.models import Candidate, CatalogTarget, MatchResult, ResourceKind, ResourceRecord
from qed_tracker.providers.books import BookProvider, ProviderError

logger = logging.getLogger("qed_tracker.books")


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    candidate: Candidate
    match: MatchResult | None = None


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
        staging_tag: str = "",
    ) -> ResourceRecord:
        """手动选书落盘：解析直链后经通用服务下载登记（课程桶由取书编排决定）。

        D11：catalog_target 课程桶路由随冻结目录链退役——交互式下载一律落领域通用桶
        `raw/<domain>/_general/`（与 fetch-url 同构）；主链路自动取书仍按 refs 反查
        课程桶（book_fetch._destination_dir）。
        """
        resolved = self.resolve(candidate)
        destination = raw_general_dir(self.resources.data_root)
        return self.resources.download_candidate(
            resolved, kind=kind, destination_dir=destination, staging_tag=staging_tag
        )
