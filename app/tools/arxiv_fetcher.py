"""arXiv 论文搜索服务 — 从 app/services/arxiv_client.py 迁入"""

import time
import arxiv
from loguru import logger


def search_papers(query: str, max_results: int = 20, delay: float = 5.0, max_retries: int = 5) -> list[dict]:
    """
    从 arXiv 搜索论文

    Args:
        query: 搜索关键词
        max_results: 最大返回数量
        delay: 请求间隔 (秒), 避免触发 429 限制
        max_retries: 最大重试次数

    Returns:
        论文元数据列表
    """
    logger.info(f"搜索 arXiv: query='{query}', max_results={max_results}")

    for attempt in range(max_retries):
        try:
            client = arxiv.Client(
                page_size=max_results,
                delay_seconds=delay,
                num_retries=3,
            )
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending,
            )

            results = []
            for paper in client.results(search):
                arxiv_id = paper.entry_id.split("/abs/")[-1]
                results.append(
                    {
                        "arxiv_id": arxiv_id,
                        "title": paper.title,
                        "abstract": paper.summary,
                        "authors": [a.name for a in paper.authors],
                        "categories": paper.categories,
                        "pdf_url": paper.pdf_url,
                        "source_url": paper.entry_id,
                        "published_date": paper.published.date(),
                    }
                )
            logger.info(f"搜索完成: {len(results)} 篇")
            return results

        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                wait_time = (attempt + 1) * 10
                logger.warning(f"arXiv 请求过于频繁，{wait_time}秒后重试 ({attempt + 1}/{max_retries})")
                time.sleep(wait_time)
            else:
                logger.error(f"arXiv 搜索失败: {e}")
                return []


def search_by_keywords(keywords: list[str], max_per_keyword: int = 20) -> list[dict]:
    """
    按多个关键词搜索并合并去重

    Args:
        keywords: 关键词列表
        max_per_keyword: 每个关键词最大返回数量

    Returns:
        去重后的论文列表
    """
    all_papers = []
    seen_titles = set()

    for i, keyword in enumerate(keywords):
        if i > 0:
            time.sleep(5)

        papers = search_papers(keyword, max_per_keyword)
        new_count = 0
        for p in papers:
            if p["title"] not in seen_titles:
                seen_titles.add(p["title"])
                all_papers.append(p)
                new_count += 1
        logger.info(f"关键词 '{keyword}': 搜索 {len(papers)} 篇, 新增 {new_count} 篇")

    logger.info(f"总计: {len(all_papers)} 篇去重后论文")
    return all_papers
