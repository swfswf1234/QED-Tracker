"""Anna's Archive — LibGen 无结果时的 fallback 搜索下载"""

import time
import httpx
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup
from loguru import logger

from app.tools._http import make_http_client


class AnnaDownloader:
    """Anna's Archive 搜索器 (LibGen 无结果时的 fallback)"""

    BASE = "https://annas-archive.gl"

    def __init__(self, timeout: float = 30.0, proxy: str = ""):
        self.client = make_http_client(timeout, proxy)

    def search(self, query: str, max_results: int = 8) -> list[dict]:
        try:
            resp = self.client.get(
                f"{self.BASE}/search",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            resp.raise_for_status()
            return self._parse_results(resp.text, max_results)
        except Exception as e:
            logger.warning(f"Anna's Archive 搜索失败 '{query}': {e}")
            return []

    def _parse_results(self, html: str, max_results: int) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results = []
        for item in soup.select("[class*='result'], [class*='item'], h2, h3"):
            parent = item.find_parent(["li", "div", "tr"]) or item
            links = parent.find_all("a", href=True)
            if not links:
                continue
            text = parent.get_text(" ", strip=True)
            title_link = parent.find("a", href=lambda h: h and "/md5/" in h)
            if not title_link:
                title_link = links[0]
            title = title_link.get_text(strip=True) or links[0].get_text(strip=True)
            if not title or len(title) < 5 or title in [r.get("title", "") for r in results]:
                continue
            detail_url = title_link["href"]
            if not detail_url.startswith("http"):
                detail_url = f"{self.BASE}{detail_url}"
            results.append({
                "title": title[:120],
                "author": self._extract_author(text, title),
                "year": "",
                "language": "",
                "size": "",
                "download_url": detail_url,
                "_source": "annas-archive",
            })
            if len(results) >= max_results:
                break
        return results

    @staticmethod
    def _extract_author(text: str, title: str) -> str:
        text = text.replace(title, "", 1).strip()
        for sep in ["by ", " — ", " – ", " | "]:
            if sep in text:
                parts = text.split(sep, 1)
                return parts[1].split(",")[0].split("|")[0].strip()[:50]
        return ""

    def download(self, url: str, save_path: Path) -> bool:
        try:
            resp = self.client.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30.0)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "libgen" in href.lower() or href.endswith(".pdf"):
                    dl_resp = self.client.get(href, follow_redirects=True, timeout=120.0)
                    if dl_resp.status_code == 200 and b"%PDF" in dl_resp.content[:100]:
                        save_path.parent.mkdir(parents=True, exist_ok=True)
                        save_path.write_bytes(dl_resp.content)
                        return True
            return False
        except Exception as e:
            logger.error(f"Anna's Archive 下载失败: {e}")
            return False

    def close(self):
        self.client.close()
