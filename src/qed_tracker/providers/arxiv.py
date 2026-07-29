"""arXiv 官方 API 来源适配器。"""

from __future__ import annotations

import re

import arxiv

from qed_tracker.models import Candidate


class ArxivProvider:
    name = "arxiv"

    def __init__(self, delay_seconds: float = 3.0, retries: int = 3):
        self.client = arxiv.Client(page_size=100, delay_seconds=delay_seconds, num_retries=retries)

    def search(
        self,
        query: str = "",
        *,
        category: str = "",
        author: str = "",
        limit: int = 10,
    ) -> list[Candidate]:
        terms = []
        if query:
            terms.append(f'all:"{query}"')
        if category:
            terms.append(f"cat:{category}")
        if author:
            terms.append(f'au:"{author}"')
        if not terms:
            raise ValueError("至少需要关键词、分类或作者之一")
        search = arxiv.Search(
            query=" AND ".join(terms),
            max_results=limit,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )
        return [self._candidate(item) for item in self.client.results(search)]

    def get(self, identifier: str) -> Candidate:
        arxiv_id = re.sub(r"^https?://arxiv\.org/(abs|pdf)/", "", identifier).removesuffix(".pdf")
        results = list(self.client.results(arxiv.Search(id_list=[arxiv_id], max_results=1)))
        if not results:
            raise ValueError(f"未找到 arXiv 论文：{arxiv_id}")
        return self._candidate(results[0])

    @staticmethod
    def _candidate(item) -> Candidate:
        arxiv_id = item.entry_id.rsplit("/", 1)[-1]
        return Candidate(
            provider="arxiv",
            provider_id=arxiv_id,
            title=" ".join(item.title.split()),
            authors=tuple(author.name for author in item.authors),
            language="en",
            year=str(item.published.year),
            page_url=item.entry_id,
            download_url=item.pdf_url,
            identifiers={"arxiv": arxiv_id},
            abstract=" ".join(item.summary.split()),
        )

    def close(self) -> None:
        return None
