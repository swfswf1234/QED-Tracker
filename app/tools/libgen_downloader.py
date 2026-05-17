"""LibGen 搜索与下载工具 — 7 镜像轮询 + Range 分块续传"""

import re
import time
import httpx
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup
from loguru import logger

from app.core.config import settings
from app.tools._http import make_http_client


class LibGenDownloader:
    """Library Genesis 搜索器（支持多镜像 + Range 分块续传）"""

    MIRRORS = [
        "https://libgen.li",
        "https://libgen.vg",
        "https://libgen.la",
        "https://libgen.bz",
        "https://libgen.gl",
        "https://libgen.gs",
        "https://libgen.lc",
    ]
    BASE_URL = MIRRORS[0]

    def __init__(self, timeout: float = 30.0, proxy: str = ""):
        self.timeout = timeout
        self.proxy = proxy
        self.client = make_http_client(timeout, proxy)

    # ── 搜索 ──────────────────────────────────────────────

    def search(self, query: str, max_results: int = 10) -> list[dict]:
        """轮询所有镜像，返回第一个有结果的响应"""
        errors = []
        for mirror in self.MIRRORS:
            url = f"{mirror}/index.php"
            params = {
                "req": query,
                "topics[]": "l",
                "columns[]": ["t", "a"],
                "objects[]": "f",
                "res": max_results,
            }
            try:
                resp = self.client.get(url, params=params)
                if resp.status_code == 404:
                    errors.append(f"{mirror}: 404")
                    continue
                resp.raise_for_status()
                results = self._parse_results(resp.text)
                if results:
                    self.BASE_URL = mirror
                    return results
            except Exception as e:
                errors.append(f"{mirror}: {e}")
                continue
        logger.warning(f"LibGen 搜索失败 '{query}': {'; '.join(errors)}")
        return []

    # ── 结果解析 ──────────────────────────────────────────

    def _parse_results(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", class_="c") or soup.find("table", id="tablelibgen")
        if not table:
            return []

        results = []
        tbody = table.find("tbody") or table
        for row in tbody.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) < 9:
                continue
            try:
                entry = self._parse_row(cols)
                if entry and entry.get("ext", "").lower() == "pdf":
                    results.append(entry)
            except Exception:
                continue
        return results

    @staticmethod
    def _parse_row(cols: list) -> Optional[dict]:
        """解析单行表格，兼容 9 列和 10 列两种格式"""
        n = len(cols)
        if n == 9:
            return LibGenDownloader._parse_9col(cols)
        return LibGenDownloader._parse_10col(cols)

    @staticmethod
    def _parse_9col(cols: list) -> dict:
        title_cell = cols[0]
        title_link = title_cell.find("a")
        title = title_link.get_text(strip=True) if title_link else title_cell.get_text(strip=True)

        dl_links = cols[8].find_all("a")
        download_url = ""
        for a in dl_links:
            href = a.get("href", "")
            if href.startswith("http"):
                download_url = href
                break

        return {
            "title": title,
            "author": cols[1].get_text(strip=True),
            "year": cols[3].get_text(strip=True),
            "language": cols[4].get_text(strip=True),
            "size": cols[6].get_text(strip=True),
            "ext": cols[7].get_text(strip=True),
            "download_url": download_url,
        }

    @staticmethod
    def _parse_10col(cols: list) -> dict:
        title_cell = cols[2]
        title_link = title_cell.find("a")
        title = title_link.get_text(strip=True) if title_link else title_cell.get_text(strip=True)
        author = cols[1].get_text(strip=True)

        dl_links = cols[9].find_all("a")
        download_url = ""
        for a in dl_links:
            href = a.get("href", "")
            if href.startswith("http"):
                download_url = href
                break
        if not download_url and dl_links:
            download_url = dl_links[0].get("href", "")

        return {
            "title": title,
            "author": author,
            "year": cols[4].get_text(strip=True),
            "language": cols[6].get_text(strip=True),
            "size": cols[7].get_text(strip=True),
            "ext": cols[8].get_text(strip=True),
            "download_url": download_url,
        }

    # ── URL 解析 ──────────────────────────────────────────

    @staticmethod
    def _to_abs(href: str, base: str) -> str:
        if href.startswith("http"):
            return href
        sep = "/" if not href.startswith("/") and not base.endswith("/") else ""
        return f"{base}{sep}{href}"

    def _resolve_get_url(self, url: str) -> str | None:
        """从 file.php/ads.php 页面提取真实下载链接"""
        try:
            resp = self.client.get(url, follow_redirects=True, timeout=30.0)
            resp.raise_for_status()
            html = resp.text
        except Exception:
            return None

        soup = BeautifulSoup(html, "html.parser")

        for a in soup.find_all("a", href=True):
            h = a["href"]
            if "get.php" in h and "md5=" in h:
                return self._to_abs(h, self.BASE_URL)

        for a in soup.find_all("a", href=True):
            h = a["href"]
            if any(d in h for d in [".lol/", ".gs/", ".lc/", "download"]) and ("md5" in h or h.endswith(".pdf")):
                return h if h.startswith("http") else self._to_abs(h, self.BASE_URL)

        for a in soup.find_all("a", href=True):
            h = a["href"]
            if "ads.php" in h and "md5=" in h:
                return self._resolve_get_url(self._to_abs(h, self.BASE_URL))

        for a in soup.find_all("a", href=True):
            h = a["href"]
            if h.startswith("http") and ("libgen" in h.lower() or "library" in h.lower()):
                return h

        return None

    # ── HTTP 请求 ─────────────────────────────────────────

    def _fresh_client(self) -> httpx.Client:
        return make_http_client(self.timeout, self.proxy)

    def _do_get(self, url: str, headers: dict | None = None, timeout: float = 120.0) -> httpx.Response | None:
        """带重试的 GET 请求，最多 3 次"""
        for attempt in range(3):
            try:
                with self._fresh_client() as c:
                    return c.get(url, headers=headers or {},
                                 follow_redirects=True, timeout=timeout)
            except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadTimeout, httpx.TimeoutException) as e:
                if attempt < 2:
                    time.sleep(5 * (attempt + 1))
                else:
                    logger.warning(f"GET 失败（{url[:60]}）: {e}")
                    return None
        return None

    # ── 下载核心 ──────────────────────────────────────────

    def _try_complete_download(self, url: str) -> Optional[bytearray]:
        """尝试完整下载，返回内容或 None"""
        CHUNK = 3 * 1024 * 1024
        resp = self._do_get(url, timeout=300.0)
        if resp and resp.content[:5] == b"%PDF-":
            total = int(resp.headers.get("content-length", 0)) or len(resp.content)
            if len(resp.content) >= total:
                return bytearray(resp.content)
            logger.info(f"部分下载 {len(resp.content)}/{total}，续传中...")
            return bytearray(resp.content)
        return None

    def _get_total_size(self, url: str, resp2: Optional[httpx.Response]) -> tuple[Optional[bytearray], int, int]:
        """获取文件总大小，返回值：(已有缓冲, 已下载位置, 总大小)"""
        if resp2 and resp2.content[:5] == b"%PDF-":
            return bytearray(resp2.content), len(resp2.content), 0

        resp = self._do_get(url, headers={"Range": "bytes=0-0"})
        if resp and resp.status_code == 206:
            cr = resp.headers.get("content-range", "")
            total = int(cr.split("/")[1]) if "/" in cr else 0
            if total > 0:
                buf = bytearray(resp.content) if resp.content[:5] == b"%PDF-" else bytearray()
                return buf, len(buf), total
        return None, 0, 0

    def _download_chunks(self, url: str, buf: bytearray, start_pos: int, total: int) -> tuple[bytearray, bool]:
        """分块下载：从 start_pos 开始下载到 total"""
        CHUNK = 3 * 1024 * 1024
        pos = start_pos
        stall = 0

        while pos < total:
            end = min(pos + CHUNK, total) - 1
            if pos >= end:
                break
            resp = self._do_get(url, headers={"Range": f"bytes={pos}-{end}"}, timeout=120.0)
            if resp is None or resp.status_code not in (206, 200) or not resp.content:
                stall += 1
                if stall > 3:
                    break
                time.sleep(10)
                continue
            buf.extend(resp.content)
            pos += len(resp.content)
            stall = 0
            pct = pos / total * 100
            logger.info(f"下载进度: {pos}/{total}（{pct:.0f}%）")
            if pct < 100:
                time.sleep(3)

        return buf, pos >= total

    def _save_result(self, buf: bytearray, save_path: Path, pos: int, total: int) -> bool:
        """保存下载结果（完整或部分 PDF）"""
        if pos >= total or (len(buf) > 10000 and buf[:5] == b"%PDF-"):
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(bytes(buf))
            if pos < total:
                logger.warning(f"保存部分 PDF（{pos}/{total}）")
            return True
        return False

    def _download_file(self, url: str, save_path: Path) -> bool:
        """下载文件主流程：尝试完整下载 → Range 分块续传 → 部分保存"""
        complete = self._try_complete_download(url)
        if complete is not None:
            if not save_path.parent.exists():
                save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(bytes(complete))
            return True

        resolved = self._resolve_get_url(url)
        if resolved and resolved != url:
            return self._download_file(resolved, save_path)

        buf, pos, total = self._get_total_size(url, None)
        if total <= 0:
            return False
        if buf:
            buf, ok = self._download_chunks(url, buf, pos, total)
        else:
            buf = bytearray()
            buf, ok = self._download_chunks(url, buf, 0, total)
        return self._save_result(buf, save_path, len(buf), total)

    # ── 对外接口 ──────────────────────────────────────────

    def download(self, url: str, save_path: Path) -> bool:
        """下载文件入口：URL 解析 → 下载 → 保存"""
        resolved = url
        try:
            if any(k in url for k in ["get.php", ".lol/", ".gs/", ".pdf"]):
                resolved = url
            elif "file.php" in url or "ads.php" in url:
                resolved = self._resolve_get_url(url)
            if not resolved:
                logger.error(f"无法解析下载链接: {url}")
                return False
            return self._download_file(resolved, save_path)
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return False

    def close(self):
        self.client.close()
