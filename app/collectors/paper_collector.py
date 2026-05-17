"""PaperCollector — arXiv paper search orchestration

Usage:
    from app.collectors.paper_collector import PaperCollector
    collector = PaperCollector()
    papers = collector.search_by_domain("math.CA", max_results=10)
"""

import re
import httpx
from pathlib import Path
from datetime import date
from typing import Optional

from loguru import logger

from app.collectors import BaseCollector
from app.tools.arxiv_fetcher import search_papers as arxiv_search
from app.core.config import settings


class PaperCollector(BaseCollector):
    source = "arxiv"

    def search_by_domain(self, domain: str, max_results: int = 20) -> list[dict]:
        query = f"cat:{domain}"
        logger.info(f"arXiv 检索: {query}, 最多 {max_results} 篇")
        return arxiv_search(query, max_results, delay=3.0)

    def download_paper(self, paper: dict, save_dir: Path) -> Optional[Path]:
        pdf_url = paper.get("pdf_url")
        arxiv_id = paper.get("arxiv_id", "")
        if not pdf_url or not arxiv_id:
            return None

        safe_id = arxiv_id.replace("/", "_")
        title = paper.get("title", "untitled")
        safe_title = re.sub(r'[<>:"/\\|?*]', "", title).strip()[:80]
        safe_title = re.sub(r'\s+', "_", safe_title) or "untitled"
        filename = f"{safe_id}_{safe_title}.pdf"
        filepath = save_dir / filename

        if filepath.exists():
            logger.info(f"已存在: {filename}")
            return filepath

        try:
            resp = httpx.get(pdf_url, follow_redirects=True, timeout=120.0)
            resp.raise_for_status()
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_bytes(resp.content)
            logger.info(f"下载完成: {filename} ({len(resp.content) / 1024:.0f} KB)")
            return filepath
        except Exception as e:
            logger.error(f"下载失败 {arxiv_id}: {e}")
            return None

    def interactive_search(self, domain: str, max_results: int = 20) -> list[dict]:
        papers = self.search_by_domain(domain, max_results)
        if not papers:
            print(f"  [无结果] {domain}")
            return []

        year = str(date.today().year)
        save_dir = settings.dataset_path / "papers" / year
        downloaded = []

        print(f"\narXiv 检索: {domain}, 最新 {len(papers)} 篇")
        print("─" * 60)
        for i, p in enumerate(papers, 1):
            title = p.get("title", "N/A")
            authors = ", ".join(p.get("authors", [])[:3])
            abstract = (p.get("abstract", "") or "")[:200].replace("\n", " ")
            arxiv_id = p.get("arxiv_id", "")

            print(f"\n[{i}/{len(papers)}] {title[:80]}")
            print(f"    作者: {authors}")
            print(f"    ID: {arxiv_id} | {p.get('published_date', '')}")
            print(f"    摘要: {abstract}...")

            try:
                choice = input("    下载? [Y/n] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = "n"

            if choice in ("", "y", "yes"):
                path = self.download_paper(p, save_dir)
                if path:
                    rel_path = path.relative_to(settings.dataset_path)
                    p["local_path"] = str(rel_path.as_posix())
                    p["is_downloaded"] = True
                    downloaded.append(p)
                    print(f"    ✓ 已下载: {rel_path}")
                else:
                    print(f"    ✗ 下载失败")
            else:
                print(f"    - 跳过")

        print(f"\n结果: 下载 {len(downloaded)}/{len(papers)} 篇")
        return downloaded
