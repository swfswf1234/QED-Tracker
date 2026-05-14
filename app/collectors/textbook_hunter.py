"""TextbookHunter — 教材 PDF 检索

用法:
    from app.collectors.textbook_hunter import TextbookHunter
    hunter = TextbookHunter()
    hunter.interactive_search("Munkres Topology")  # 交互式搜索
"""

import re
import time
import ssl as ssl_mod
import httpx
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from bs4 import BeautifulSoup
from loguru import logger

from app.collectors import BaseCollector, ResourceInfo
from app.core.config import settings


TEXTBOOK_TARGETS = {
    "03_topology":           {"en": "Munkres Topology",                           "zh": "点集拓扑 熊金城",              "zh_exercise": "点集拓扑习题集"},
    "04_real_analysis":      {"en": "Stein Real Analysis; Folland Real Analysis", "zh": "实变函数论 周民强",            "zh_exercise": "实变函数解题指南 周民强"},
    "05_complex_analysis":   {"en": "Stein Complex Analysis; Ahlfors Complex Analysis", "zh": "复分析 Ahlfors",     "zh_exercise": "复变函数习题集 方企勤"},
    "06_functional_analysis":{"en": "Stein Functional Analysis; Lax Functional Analysis", "zh": "泛函分析 张恭庆",  "zh_exercise": "泛函分析学习指导"},
    "07_ode":                {"en": "Tenenbaum Ordinary Differential Equations",  "zh": "常微分方程 丁同仁",            "zh_exercise": "常微分方程习题解"},
    "08_pde":                {"en": "Evans Partial Differential Equations",        "zh": "偏微分方程 Evans",            "zh_exercise": ""},
    "09_abstract_algebra":   {"en": "Dummit Abstract Algebra; Aluffi Algebra Chapter 0", "zh": "抽象代数 冯克勤",  "zh_exercise": ""},
    "10_qe_prep":            {"en": "Berkeley Problems in Mathematics",            "zh": "伯克利数学问题集",            "zh_exercise": ""},
}


def _make_ssl_context():
    """创建禁用证书验证和吊销检查的 SSL 上下文 (windows schannel 兼容)"""
    ctx = ssl_mod.SSLContext(ssl_mod.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl_mod.CERT_NONE
    return ctx


def _make_client(timeout: float = 30.0, proxy: str = "") -> httpx.Client:
    kwargs = {"timeout": timeout, "follow_redirects": True, "verify": _make_ssl_context()}
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.Client(**kwargs)


# ============================================================
# Phase 1: LibGenHunter — 镜像 + 直连 IP 多路搜索
# ============================================================

class LibGenHunter:
    """Library Genesis 搜索器 (支持多镜像 + 直连 IP)"""

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
        self.client = _make_client(timeout, proxy)
        self._total_size = 0

    def search(self, query: str, max_results: int = 10) -> list[dict]:
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
                    errors.append(f"{mirror}: 404 (wrong endpoint)")
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

    def _parse_results(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", class_="c") or soup.find("table", id="tablelibgen")
        if not table:
            return []

        results = []
        tbody = table.find("tbody") or table
        rows = tbody.find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 9:
                continue
            try:
                n = len(cols)  # 9 (libgen.li) or 10 (original libgen.is)
                if n == 9:
                    # libgen.li format: 0=ID+Title, 1=Author, 2=Pub, 3=Year, 4=Lang, 5=Pages, 6=Size, 7=Ext, 8=Mirrors
                    title_cell = cols[0]
                    title_link = title_cell.find("a")
                    title = title_link.get_text(strip=True) if title_link else title_cell.get_text(strip=True)
                    author = cols[1].get_text(strip=True)
                    year = cols[3].get_text(strip=True)
                    lang = cols[4].get_text(strip=True)
                    size = cols[6].get_text(strip=True)
                    ext = cols[7].get_text(strip=True)
                    dl_links = cols[6].find_all("a")
                    download_url = ""
                    for a in dl_links:
                        href = a.get("href", "")
                        if href and "file.php" in href:
                            download_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href
                            break
                    if not download_url:
                        for a in cols[8].find_all("a"):
                            href = a.get("href", "")
                            if href and href.startswith("http"):
                                download_url = href
                                break
                else:
                    # Original libgen.is format: 0=ID, 1=Author, 2=Title, 3=Pub, 4=Year, 5=Pages, 6=Lang, 7=Size, 8=Ext, 9=DL
                    title_cell = cols[2]
                    title_link = title_cell.find("a")
                    title = title_link.get_text(strip=True) if title_link else title_cell.get_text(strip=True)
                    author = cols[1].get_text(strip=True)
                    year = cols[4].get_text(strip=True)
                    lang = cols[6].get_text(strip=True)
                    size = cols[7].get_text(strip=True)
                    ext = cols[8].get_text(strip=True)
                    dl_links = cols[9].find_all("a")
                    download_url = ""
                    for a in dl_links:
                        href = a.get("href", "")
                        if href.startswith("http"):
                            download_url = href
                            break
                    if not download_url and dl_links:
                        download_url = dl_links[0].get("href", "")

                if ext.lower() != "pdf":
                    continue

                results.append({
                    "title": title,
                    "author": author,
                    "year": year,
                    "language": lang,
                    "size": size,
                    "download_url": download_url,
                })
            except Exception:
                continue

        return results

    @staticmethod
    def _to_abs(href: str, base: str) -> str:
        if href.startswith("http"):
            return href
        sep = "/" if not href.startswith("/") and not base.endswith("/") else ""
        return f"{base}{sep}{href}"

    def _resolve_get_url(self, url: str) -> str | None:
        """将 file.php 或 ads.php URL 解析为最终的 get.php?md5=...&key=..."""
        try:
            resp = self.client.get(url, follow_redirects=True, timeout=30.0)
            resp.raise_for_status()
            html = resp.text
        except Exception:
            return None

        soup = BeautifulSoup(html, "html.parser")
        # Try direct get.php link first
        for a in soup.find_all("a", href=True):
            h = a["href"]
            if "get.php" in h and "md5=" in h:
                return self._to_abs(h, self.BASE_URL)
        # Fall through: follow ads.php -> get.php
        for a in soup.find_all("a", href=True):
            h = a["href"]
            if "ads.php" in h and "md5=" in h:
                ads_url = self._to_abs(h, self.BASE_URL)
                return self._resolve_get_url(ads_url)
        return None

    def _fresh_client(self) -> httpx.Client:
        return _make_client(self.timeout, self.proxy)

    def _do_get(self, url: str, headers: dict | None = None, timeout: float = 120.0) -> httpx.Response | None:
        """用全新客户端 GET，失败返回 None"""
        for attempt in range(3):
            try:
                with self._fresh_client() as c:
                    return c.get(url, headers=headers or {},
                                 follow_redirects=True, timeout=timeout)
            except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadTimeout, httpx.TimeoutException) as e:
                if attempt < 2:
                    time.sleep(5 * (attempt + 1))
                else:
                    logger.warning(f"GET 失败 ({url[:60]}): {e}")
                    return None
        return None

    def _download_file(self, url: str, save_path: Path) -> bool:
        """分块下载：先试完整 GET，不完整则用 Range 块续传"""
        CHUNK = 8 * 1024 * 1024  # 8MB per chunk

        # Step 1: Full GET
        resp = self._do_get(url, timeout=300.0)
        if resp and resp.content[:5] == b"%PDF-":
            total = int(resp.headers.get("content-length", 0)) or len(resp.content)
            if len(resp.content) >= total:
                save_path.parent.mkdir(parents=True, exist_ok=True)
                save_path.write_bytes(resp.content)
                return True
            # Partial — start from where we got
            logger.info(f"部分下载 {len(resp.content)}/{total}, 续传中...")
            buf = bytearray(resp.content)
            pos = len(resp.content)
        else:
            # Try Range from the start to get total_size
            resp2 = self._do_get(url, headers={"Range": "bytes=0-0"})
            if resp2 and resp2.status_code == 206:
                cr = resp2.headers.get("content-range", "")
                total = int(cr.split("/")[1]) if "/" in cr else 0
            else:
                # Fresh ads -> key approach
                resolved = self._resolve_get_url(url)
                if not resolved or resolved == url:
                    return False
                return self._download_file(resolved, save_path)
            if total <= 0:
                return False
            buf = bytearray()
            pos = 0
            if resp2 and resp2.content[:5] == b"%PDF-":
                buf = bytearray(resp2.content)
                pos = len(resp2.content)

        # Step 2: Range chunks
        stall = 0
        while pos < total:
            end = min(pos + CHUNK, total) - 1
            if pos >= end:
                break
            hdrs = {"Range": f"bytes={pos}-{end}"}
            resp = self._do_get(url, headers=hdrs, timeout=120.0)
            if resp is None:
                stall += 1
                if stall > 3:
                    break
                time.sleep(10)
                continue
            chunk = resp.content
            if not chunk or resp.status_code not in (206, 200):
                stall += 1
                if stall > 3:
                    break
                time.sleep(10)
                continue
            buf.extend(chunk)
            pos += len(chunk)
            stall = 0
            pct = pos / total * 100
            logger.info(f"下载进度: {pos}/{total} ({pct:.0f}%)")
            if pct < 100:
                time.sleep(3)  # Pacing to avoid rate limit

        if pos >= total:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(bytes(buf))
            return True

        # Save partial if useful
        if len(buf) > 10000 and buf[:5] == b"%PDF-":
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(bytes(buf))
            logger.warning(f"保存部分 PDF ({pos}/{total})")
            return True

        return False

    def download(self, url: str, save_path: Path) -> bool:
        resolved = url
        try:
            # Step 1: if this is a file.php URL, resolve to get.php
            if "file.php" in url or "ads.php" in url:
                resolved = self._resolve_get_url(url)
            if not resolved:
                logger.error(f"无法解析下载链接: {url}")
                return False

            # Step 2: try full download, fallback to Range chunked
            return self._download_file(resolved, save_path)
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return False

    def close(self):
        self.client.close()


# ============================================================
# Phase 2: AnnaArchiveHunter — Anna's Archive 备用源
# ============================================================

class AnnaArchiveHunter:
    """Anna's Archive 搜索器 (LibGen 无结果时的 fallback)"""

    BASE = "https://annas-archive.gl"

    def __init__(self, timeout: float = 30.0, proxy: str = ""):
        self.client = _make_client(timeout, proxy)

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
        # Try common separator patterns
        for sep in ["by ", " — ", " – ", " | "]:
            if sep in text:
                parts = text.split(sep, 1)
                return parts[1].split(",")[0].split("|")[0].strip()[:50]
        return ""

    def download(self, url: str, save_path: Path) -> bool:
        """通过 Anna's Archive 详情页查找并下载 PDF"""
        try:
            resp = self.client.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30.0)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            # Find download links (typically LibGen redirects)
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


# ============================================================
# TextbookHunter — 优先 LibGen, fallback 到 Anna's Archive
# ============================================================

class TextbookHunter(BaseCollector):
    source = "textbook"

    def __init__(self, proxy: str = ""):
        self.proxy = proxy
        self.libgen = LibGenHunter(proxy=proxy)
        self.anna = AnnaArchiveHunter(proxy=proxy)

    def search_course(self, course: str, query: str, source_hint: str = "") -> list[dict]:
        print(f"\n检索: {course} -> {query}")
        results = self.libgen.search(query, max_results=8)
        if not results:
            print("  LibGen 无结果, 尝试 Anna's Archive...")
            results = self.anna.search(query, max_results=8)
        if not results:
            print("  全部源无结果")
        return results

    def interactive_search(self, course: str, query: str):
        results = self.search_course(course, query)
        save_dir = settings.dataset_path / "textbooks" / course
        downloaded = []

        if not results:
            print("  [无结果]")
            return downloaded

        print(f"  找到 {len(results)} 个结果:")
        for i, r in enumerate(results, 1):
            source_tag = " [Anna's Archive]" if r.get("_source") == "annas-archive" else ""
            print(f"  [{i}]{source_tag} {r['title'][:70]}")
            print(f"      作者: {r['author']} | {r.get('year', '')} | {r.get('size', '')} | {r.get('language', '')}")

        while True:
            try:
                choice = input("  选择下载 [1-{0}/skip]: ".format(len(results))).strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = "skip"
            if choice == "skip":
                break
            if choice.isdigit() and 1 <= int(choice) <= len(results):
                idx = int(choice) - 1
                r = results[idx]
                safe_title = re.sub(r'[<>:"/\\|?*]', "", r["title"]).strip()[:80]
                safe_title = re.sub(r'\s+', "_", safe_title)
                filename = f"{safe_title}.pdf"
                filepath = save_dir / filename

                print(f"    下载中...")
                hunter = self.anna if r.get("_source") == "annas-archive" else self.libgen
                ok = hunter.download(r["download_url"], filepath)
                if ok:
                    rel = filepath.relative_to(settings.dataset_path)
                    print(f"    ✓ 已保存: {rel}")
                    downloaded.append({**r, "local_path": str(rel.as_posix()), "course": course})
                else:
                    print(f"    ✗ 下载失败")
                break

        return downloaded

    def interactive_all(self):
        for course, targets in TEXTBOOK_TARGETS.items():
            zh_query = targets.get("zh", "")
            en_query = targets.get("en", "")
            zh_ex = targets.get("zh_exercise", "")
            all_downloaded = []
            has_target = False

            if zh_query:
                has_target = True
                print(f"\n{'='*60}")
                print(f"课程: {course} (中文教材)")
                print(f"{'='*60}")
                all_downloaded.extend(self.interactive_search(course, zh_query))

            if en_query:
                has_target = True
                for q in en_query.split(";"):
                    q = q.strip()
                    if not q:
                        continue
                    print(f"\n{'='*60}")
                    print(f"课程: {course} (英文教材: {q})")
                    print(f"{'='*60}")
                    all_downloaded.extend(self.interactive_search(course, q))

            if zh_ex:
                has_target = True
                print(f"\n{'='*60}")
                print(f"课程: {course} (习题集)")
                print(f"{'='*60}")
                all_downloaded.extend(self.interactive_search(course, zh_ex))

            if not has_target:
                print(f"\n{'='*60}")
                print(f"课程: {course} (无目标)")
                print(f"{'='*60}")

        self.libgen.close()
        self.anna.close()
