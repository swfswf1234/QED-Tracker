"""教材与习题集来源适配器及统一候选结构。"""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol
from urllib.parse import quote

import httpx

from qed_tracker.models import Availability, Candidate


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
            params={"q": f"{self._build_solr_query(query)} AND mediatype:texts", "fl[]": ["identifier", "title", "creator", "year", "language"], "rows": limit, "output": "json"},
            headers={"User-Agent": "QED-Tracker/0.5"},
        )
        response.raise_for_status()
        return [_archive_candidate(self.name, item) for item in response.json().get("response", {}).get("docs", [])]

    def resolve(self, candidate: Candidate) -> Candidate:
        response = self.client.get(f"https://archive.org/metadata/{candidate.provider_id}")
        response.raise_for_status()
        files = response.json().get("files", [])
        pdfs = [item for item in files if str(item.get("name", "")).lower().endswith(".pdf") and item.get("private") not in (True, "true")]
        if not pdfs:
            raise ProviderError("Internet Archive 条目没有可公开下载的 PDF")
        pdfs.sort(key=lambda item: int(item.get("size") or 0), reverse=True)
        url = f"https://archive.org/download/{candidate.provider_id}/{quote(pdfs[0]['name'])}"
        return replace(candidate, download_url=url, size_bytes=int(pdfs[0].get("size") or 0) or None)


class OpenLibraryProvider(InternetArchiveProvider):
    name = "open_library"

    def search(self, query: str, limit: int = 10) -> list[Candidate]:
        response = self.client.get(
            "https://openlibrary.org/search.json",
            params={"q": query, "limit": limit, "fields": "title,author_name,ia,first_publish_year,language"},
            headers={"User-Agent": "QED-Tracker/0.5"},
        )
        response.raise_for_status()
        results = []
        for item in response.json().get("docs", []):
            archive_ids = item.get("ia") or []
            archive_id = archive_ids[0] if archive_ids else ""
            mapped = {
                "identifier": archive_id,
                "title": item.get("title", ""),
                "author_name": item.get("author_name", []),
                "year": item.get("first_publish_year", ""),
                "language": (item.get("language") or [""])[0],
            }
            results.append(_archive_candidate(self.name, mapped))
        return results


class GoogleBooksProvider(HttpProvider):
    name = "google_books"

    def search(self, query: str, limit: int = 10) -> list[Candidate]:
        response = self.client.get("https://www.googleapis.com/books/v1/volumes", params={"q": query, "maxResults": min(limit, 40)})
        response.raise_for_status()
        results = []
        for item in response.json().get("items", []):
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
                page_url=info.get("infoLink", ""),
                download_url=link,
                availability=Availability.DOWNLOADABLE if link else Availability.METADATA_ONLY,
                identifiers=identifiers,
            ))
        return results


PROVIDER_TYPES = {
    "internet_archive": InternetArchiveProvider,
    "open_library": OpenLibraryProvider,
    "google_books": GoogleBooksProvider,
}

RETIRED_PROVIDERS = {"libgen", "annas_archive", "zlib"}


def create_book_providers(names: tuple[str, ...], **kwargs) -> list[BookProvider]:
    retired = sorted(set(names) & RETIRED_PROVIDERS)
    if retired:
        raise ValueError(
            f"教材来源已在 0.5 移除：{', '.join(retired)}；"
            "请从 [core].sources 或 QED_TRACKER_SOURCES 中删除"
        )
    unknown = sorted(set(names) - PROVIDER_TYPES.keys())
    if unknown:
        raise ValueError(f"未知教材来源：{', '.join(unknown)}")
    return [PROVIDER_TYPES[name](**kwargs) for name in names]
