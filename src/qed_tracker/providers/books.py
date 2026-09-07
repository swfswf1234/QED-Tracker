"""教材与习题集来源适配器及统一候选结构。"""

from __future__ import annotations

import html
import json
import re
from dataclasses import replace
from typing import Protocol
from urllib.parse import quote

import httpx

from qed_tracker.models import Availability, Candidate, DownloadLink


class ProviderError(RuntimeError):
    pass


class BookProvider(Protocol):
    name: str

    def search(self, query: str, limit: int = 10) -> list[Candidate]: ...
    def resolve(self, candidate: Candidate) -> Candidate: ...
    def close(self) -> None: ...


class HttpProvider:
    name = "http"

    def __init__(self, *, proxy: str = "", timeout: float = 30.0, tls_verify: bool = True):
        kwargs: dict = {"timeout": timeout, "follow_redirects": True, "verify": tls_verify}
        if proxy:
            kwargs["proxy"] = proxy
        self.client = httpx.Client(**kwargs)

    def close(self) -> None:
        self.client.close()

    def resolve(self, candidate: Candidate) -> Candidate:
        return candidate


def _decode_text(content: bytes) -> str:
    """HTTP 响应体严格按 UTF-8 解码（禁止平台 locale 或响应头 charset 隐式解码）。"""
    return content.decode("utf-8")


def _decode_json(content: bytes) -> dict:
    """HTTP JSON 响应体严格按 UTF-8 解码后解析（禁止响应头 charset 隐式解码）。"""
    return json.loads(_decode_text(content))


def _solr_text(value: object) -> str:
    """IA solr 字段可能是 str 或 list（多值字段），归一为单条字符串。"""
    if isinstance(value, list):
        return " ".join(str(part) for part in value).strip()
    return str(value or "").strip()


def _ol_text(value: object) -> str:
    """OL search 字段值可能是 str / list / {"type": "/type/text", "value": ...}，归一为单条字符串。"""
    if isinstance(value, dict):
        value = value.get("value", "")
    if isinstance(value, list):
        return " ".join(_ol_text(part) for part in value).strip()
    return str(value or "").strip()


def _to_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _archive_candidate(provider: str, item: dict) -> Candidate:
    identifier = str(item.get("identifier", ""))
    creator = item.get("creator") or item.get("author_name") or []
    if isinstance(creator, str):
        creators = (creator,)
    else:
        creators = tuple(str(value) for value in creator[:3])
    return Candidate(
        provider=provider,
        provider_id=identifier,
        title=str(item.get("title", "")),
        authors=creators,
        language=str(item.get("language", "")),
        year=str(item.get("year", "")),
        publisher=_solr_text(item.get("publisher")),
        description=_solr_text(item.get("description")),
        page_count=_to_int(item.get("page_count")),
        page_url=f"https://archive.org/details/{identifier}" if identifier else "",
        availability=Availability.DOWNLOADABLE if identifier else Availability.METADATA_ONLY,
        identifiers={"internet_archive": identifier} if identifier else {},
    )


class InternetArchiveProvider(HttpProvider):
    name = "internet_archive"

    @staticmethod
    def _build_solr_query(query: str) -> str:
        # 中文（CJK）query：首词做 title 精确短语 + 其余词 AND（QED-018 实测：
        # 全字段 OR 拆词对中文只返回 ChinaXiv 预印本噪音，`title:"数学分析" AND 陈纪修`
        # 才能命中真实中文教材）。非 CJK 保持全字段（title:(a b c) 多词返回 0）。
        if any("\u4e00" <= char <= "\u9fff" for char in query):
            terms = query.split()
            if len(terms) > 1:
                return f'title:"{terms[0]}" AND ' + " AND ".join(terms[1:])
            return f'title:"{query}"'
        return query

    def search(self, query: str, limit: int = 10) -> list[Candidate]:
        response = self.client.get(
            "https://archive.org/advancedsearch.php",
            params={"q": f"{self._build_solr_query(query)} AND mediatype:texts", "fl[]": ["identifier", "title", "creator", "year", "language", "description", "publisher"], "rows": limit, "output": "json"},
            headers={"User-Agent": "QED-Tracker/0.5"},
        )
        response.raise_for_status()
        return [_archive_candidate(self.name, item) for item in _decode_json(response.content).get("response", {}).get("docs", [])]

    def resolve(self, candidate: Candidate) -> Candidate:
        response = self.client.get(f"https://archive.org/metadata/{candidate.provider_id}")
        response.raise_for_status()
        data = _decode_json(response.content)
        files = data.get("files", [])
        pdfs = [item for item in files if str(item.get("name", "")).lower().endswith(".pdf") and item.get("private") not in (True, "true")]
        if not pdfs:
            raise ProviderError("Internet Archive 条目没有可公开下载的 PDF")
        if candidate.file_keywords:
            matched = [
                item for item in pdfs
                if any(keyword and keyword in str(item.get("name", "")) for keyword in candidate.file_keywords)
            ]
            if matched:
                pdfs = matched
        pdfs.sort(key=lambda item: int(item.get("size") or 0), reverse=True)
        url = f"https://archive.org/download/{candidate.provider_id}/{quote(pdfs[0]['name'])}"
        # 2026-08-09：记录 archive 声明的 md5（metadata files 均带 md5/sha1），
        # 供下载后内容完整性校验，杜绝并发/错配产生的混合文件登记入库。
        identifiers = dict(candidate.identifiers)
        file_md5 = str(pdfs[0].get("md5") or "")
        if file_md5:
            identifiers["md5"] = file_md5
        # QED-050 enrich：resolve 本就为选文件而取 metadata，顺带读 description/publisher/date
        # （零新增 HTTP）；只回填 search 缺失的字段，不覆盖已有值。
        meta = data.get("metadata") or {}
        updates: dict = {}
        if not candidate.description:
            description = _solr_text(meta.get("description"))
            if description:
                updates["description"] = description
        if not candidate.publisher:
            publisher = _solr_text(meta.get("publisher"))
            if publisher:
                updates["publisher"] = publisher
        if not candidate.year:
            year_match = re.search(r"\d{4}", str(meta.get("year") or meta.get("date") or ""))
            if year_match:
                updates["year"] = year_match.group(0)
        if updates:
            candidate = replace(candidate, **updates)
        return replace(candidate, identifiers=identifiers, download_url=url, size_bytes=int(pdfs[0].get("size") or 0) or None)


class OpenLibraryProvider(InternetArchiveProvider):
    name = "open_library"

    def search(self, query: str, limit: int = 10) -> list[Candidate]:
        response = self.client.get(
            "https://openlibrary.org/search.json",
            params={"q": query, "limit": limit, "fields": "title,author_name,ia,first_publish_year,language,publisher,subtitle,first_sentence,number_of_pages_median"},
            headers={"User-Agent": "QED-Tracker/0.5"},
        )
        response.raise_for_status()
        results = []
        for item in _decode_json(response.content).get("docs", []):
            archive_ids = item.get("ia") or []
            archive_id = archive_ids[0] if archive_ids else ""
            # QED-050 enrich：介绍字段随同一次搜索响应带回（零新增 HTTP）；
            # description 由副题 + 首句拼接（first_sentence 可能是 {"type": "/type/text"} 形状）。
            mapped = {
                "identifier": archive_id,
                "title": item.get("title", ""),
                "author_name": item.get("author_name", []),
                "year": item.get("first_publish_year", ""),
                "language": (item.get("language") or [""])[0],
                "publisher": _ol_text(item.get("publisher")),
                "description": "；".join(part for part in (_ol_text(item.get("subtitle")), _ol_text(item.get("first_sentence"))) if part),
                "page_count": _to_int(item.get("number_of_pages_median")),
            }
            results.append(_archive_candidate(self.name, mapped))
        return results


class GoogleBooksProvider(HttpProvider):
    name = "google_books"

    def search(self, query: str, limit: int = 10) -> list[Candidate]:
        response = self.client.get("https://www.googleapis.com/books/v1/volumes", params={"q": query, "maxResults": min(limit, 40)})
        response.raise_for_status()
        results = []
        for item in _decode_json(response.content).get("items", []):
            info, access = item.get("volumeInfo", {}), item.get("accessInfo", {})
            link = access.get("pdf", {}).get("downloadLink", "")
            identifiers = {entry["type"].lower(): entry["identifier"] for entry in info.get("industryIdentifiers", [])}
            results.append(Candidate(
                provider=self.name,
                provider_id=item.get("id", ""),
                title=info.get("title", ""),
                authors=tuple(info.get("authors", [])),
                language=info.get("language", ""),
                year=str(info.get("publishedDate", ""))[:4],
                publisher=str(info.get("publisher", "")).strip(),
                description=str(info.get("description", "")).strip(),
                page_count=_to_int(info.get("pageCount")),
                page_url=info.get("infoLink", ""),
                download_url=link,
                availability=Availability.DOWNLOADABLE if link else Availability.METADATA_ONLY,
                identifiers=identifiers,
            ))
        return results


class LibgenLiProvider(HttpProvider):
    """libgen.li 发现专用来源（QED-021）。

    2026-08-07 实测：libgen.li 无 HTTP 直链，仅提供 torrent/IPFS/ed2k/TOR 下载方案；
    中文检索词直接全字段命中（无需 archive 的 CJK 短语特判）。
    本适配器只搜索与解析书目和下载方案（availability=metadata_only），
    永不自动写文件；下载由人工按 links 方案完成后再登记（register 端点）。
    """

    name = "libgen_li"

    _ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
    _TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
    _EDITION_RE = re.compile(r'href="edition\.php\?id=(\d+)"[^>]*>(.*?)</a>', re.S | re.I)
    _LINK_RE = re.compile(r'<a[^>]+href="([^"]+)"', re.I)
    _SIZE_RE = re.compile(r"([\d.,]+\s*(?:MB|GB))", re.I)

    def _cell(self, raw: str) -> str:
        return html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()

    def search(self, query: str, limit: int = 10) -> list[Candidate]:
        response = self.client.get(
            "https://libgen.li/index.php",
            params={"req": query},
            headers={"User-Agent": "Mozilla/5.0 (QED-Tracker/0.6)"},
        )
        response.raise_for_status()
        results: list[Candidate] = []
        text = _decode_text(response.content)
        for row in self._ROW_RE.findall(text):
            cells = [self._cell(td) for td in self._TD_RE.findall(row)]
            match = self._EDITION_RE.search(row)
            if match is None or not cells:
                continue  # 表头/无 edition 链接的行跳过
            edition_id, title_html = match.groups()
            title = self._cell(title_html)
            # 2026-08-09 实测：数据行 9 列 [Series+Title, Author(s), Publisher,
            # Year, Language, Pages, Size, Ext, 镜像/分页]；早前 13 列布局已不存在，
            # 全部按 9 列索引取（fixture 与真实页面同步）。
            size = ""
            size_match = self._SIZE_RE.search(cells[6] if len(cells) > 6 else "")
            if size_match:
                size = size_match.group(1)
            # QED-050 enrich：Publisher 列此前解析后丢弃，现回填进候选（零新增 HTTP）；
            # Pages 列形如「1780 / 1780」，取首个数字。
            pages_match = re.search(r"\d+", cells[5]) if len(cells) > 5 else None
            results.append(Candidate(
                provider=self.name,
                provider_id=edition_id,
                title=title,
                authors=tuple(part.strip() for part in cells[1].split(";")) if len(cells) > 1 else (),
                year=cells[3] if len(cells) > 3 else "",
                language=cells[4] if len(cells) > 4 else "",
                publisher=cells[2] if len(cells) > 2 else "",
                page_count=int(pages_match.group(0)) if pages_match else None,
                format=cells[7].casefold() if len(cells) > 7 else "pdf",
                size_bytes=_parse_size(size),
                page_url=f"https://libgen.li/edition.php?id={edition_id}",
                availability=Availability.METADATA_ONLY,
            ))
            if len(results) >= limit:
                break
        return results

    def resolve(self, candidate: Candidate) -> Candidate:
        response = self.client.get(
            f"https://libgen.li/edition.php?id={candidate.provider_id}",
            headers={"User-Agent": "Mozilla/5.0 (QED-Tracker/0.6)"},
        )
        response.raise_for_status()
        text = _decode_text(response.content)
        identifiers = dict(candidate.identifiers)
        md5_match = re.search(r'md5:([0-9a-f]{32})', text, re.I)
        if md5_match:
            identifiers["md5"] = md5_match.group(1)
        links: list[DownloadLink] = []
        for url in self._LINK_RE.findall(text):
            href = html.unescape(url)
            if href.startswith("magnet:"):
                links.append(DownloadLink("Torrent", href, "torrent"))
            elif href.startswith("ed2k://"):
                links.append(DownloadLink("ed2k", href, "ed2k"))
            elif "ipfs" in href.casefold():
                links.append(DownloadLink("IPFS", href, "ipfs"))
        return replace(candidate, identifiers=identifiers, links=tuple(links))


def _parse_size(value: str) -> int | None:
    match = re.match(r"([\d.]+)\s*(MB|GB)", value, re.I)
    if not match:
        return None
    number = float(match.group(1))
    return int(number * (1024**3 if match.group(2).upper() == "GB" else 1024**2))


PROVIDER_TYPES = {
    "internet_archive": InternetArchiveProvider,
    "open_library": OpenLibraryProvider,
    "google_books": GoogleBooksProvider,
    "libgen_li": LibgenLiProvider,
}

RETIRED_PROVIDERS = {"annas_archive", "zlib"}


def create_book_providers(names: tuple[str, ...], **kwargs) -> list[BookProvider]:
    retired = sorted(set(names) & RETIRED_PROVIDERS)
    if retired:
        raise ValueError(
            f"教材来源已退役：{', '.join(retired)}；"
            "请从根 .env 的 QED_SOURCES 中删除，或改用内置来源（internet_archive/open_library/google_books/libgen_li）"
        )
    unknown = sorted(set(names) - PROVIDER_TYPES.keys())
    if unknown:
        raise ValueError(f"未知教材来源：{', '.join(unknown)}")
    return [PROVIDER_TYPES[name](**kwargs) for name in names]
