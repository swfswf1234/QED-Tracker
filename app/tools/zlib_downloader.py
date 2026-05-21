"""Z-Library 搜索与下载工具 — singlelogin.re 爬取

接口与 LibGenDownloader / AnnaDownloader 对齐，作为 LibGen 的 fallback 源。
"""

import re
import httpx
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup
from loguru import logger

from app.tools._http import make_http_client


class ZlibDownloader:
    """Z-Library 搜索器 (singlelogin.re 前端爬取)"""

    BASE = "https://singlelogin.re"

    def __init__(self, timeout: float = 30.0, proxy: str = ""):
        self.client = make_http_client(timeout, proxy)

    def check_reachable(self) -> bool:
        """检查 Z-Library 站点是否可达"""
        try:
            resp = self.client.get(self.BASE, timeout=10.0)
            return resp.status_code == 200
        except Exception:
            return False

    def search(self, query: str, max_results: int = 8) -> list[dict]:
        """搜索书籍，返回结果列表"""
        try:
            resp = self.client.get(
                f"{self.BASE}/s/",
                params={"q": query},
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                },
                follow_redirects=True,
            )
            resp.raise_for_status()
            return self._parse_results(resp.text, max_results)
        except Exception as e:
            logger.warning(f"Z-Library 搜索失败 '{query}': {e}")
            return []

    def _parse_results(self, html: str, max_results: int) -> list[dict]:
        """解析搜索结果 HTML"""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        book_cards = soup.select("table tr, div[class*='book'], div[class*='res-item'], .resItem")
        if not book_cards:
            book_cards = soup.find_all("div", class_=re.compile(r"book|item|result"))

        for card in book_cards:
            if len(results) >= max_results:
                break

            title_el = card.find("a", href=re.compile(r"/book/|/b/|/md5/"))
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            if not title or not href:
                continue

            book_url = href if href.startswith("http") else f"{self.BASE}{href}"

            author_el = card.find("div", class_=re.compile(r"author")) or card.find(
                "a", href=re.compile(r"/author/|/a/")
            )
            author = author_el.get_text(strip=True) if author_el else ""

            year = ""
            year_el = card.find(text=re.compile(r"\b(19|20)\d{2}\b"))
            if year_el:
                m = re.search(r"\b(19|20)\d{2}\b", year_el)
                if m:
                    year = m.group()

            size_el = card.find("div", class_=re.compile(r"size")) or card.find(
                "span", class_=re.compile(r"size")
            )
            size = size_el.get_text(strip=True) if size_el else ""

            lang_el = card.find("div", class_=re.compile(r"lang")) or card.find(
                "span", class_=re.compile(r"lang")
            )
            language = lang_el.get_text(strip=True) if lang_el else ""

            ext_el = card.find("div", class_=re.compile(r"format|ext")) or card.find(
                "span", class_=re.compile(r"format|ext")
            )
            ext = ext_el.get_text(strip=True).lower() if ext_el else "pdf"
            if ext and ext not in ("pdf", "djvu", "epub"):
                continue

            results.append({
                "title": title,
                "author": author,
                "year": year,
                "language": language,
                "size": size,
                "ext": ext,
                "download_url": book_url,
                "_source": "zlib",
            })

        return results

    def download(self, url: str, save_path: Path) -> bool:
        """下载书籍 PDF 到本地路径

        Z-Library 的下载流程：
        1. 访问书籍详情页
        2. 找到下载链接（通常需要重定向）
        3. 下载文件
        """
        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)

            resp = self.client.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                },
                follow_redirects=True,
            )
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            dl_link = None

            for a in soup.find_all("a", href=True):
                h = a["href"]
                if "download" in h.lower() or h.endswith(".pdf") or "get" in h:
                    dl_link = h if h.startswith("http") else f"{self.BASE}{h}"
                    break

            if not dl_link:
                logger.warning(f"Z-Library 未找到下载链接: {url}")
                return False

            dl_resp = self.client.get(
                dl_link,
                follow_redirects=True,
                timeout=300.0,
            )
            dl_resp.raise_for_status()

            content = dl_resp.content
            if content[:5] != b"%PDF-":
                logger.warning(f"Z-Library 下载内容非 PDF: {url}")
                return False

            save_path.write_bytes(content)
            logger.info(f"Z-Library 下载成功: {save_path.name}")
            return True

        except Exception as e:
            logger.warning(f"Z-Library 下载失败: {e}")
            return False

    def close(self):
        self.client.close()
