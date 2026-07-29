"""教材与习题集来源适配器及统一候选结构。"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Protocol
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup

from qed_tracker.models import Availability, Candidate


class ProviderError(RuntimeError):
    pass


class BookProvider(Protocol):
    name: str

    def search(self, query: str, limit: int = 10) -> list[Candidate]: ...
    def resolve(self, candidate: Candidate) -> Candidate: ...
    def close(self) -> None: ...


def _size(value: str) -> int | None:
    match = re.search(r"([\d.]+)\s*(KB|MB|GB)", value.upper())
    if not match:
        return None
    multiplier = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}[match.group(2)]
    return int(float(match.group(1)) * multiplier)


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

    def search(self, query: str, limit: int = 10) -> list[Candidate]:
        response = self.client.get(
            "https://archive.org/advancedsearch.php",
            params={"q": f'title:({query}) AND mediatype:texts', "fl[]": ["identifier", "title", "creator", "year", "language"], "rows": limit, "output": "json"},
            headers={"User-Agent": "QED-Tracker/0.3"},
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
            headers={"User-Agent": "QED-Tracker/0.3"},
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


class LibgenProvider(HttpProvider):
    name = "libgen"
    mirrors = ("https://libgen.li", "https://libgen.vg", "https://libgen.la", "https://libgen.bz", "https://libgen.gl")

    def search(self, query: str, limit: int = 10) -> list[Candidate]:
        for mirror in self.mirrors:
            try:
                response = self.client.get(f"{mirror}/index.php", params={"req": query, "topics[]": "l", "res": limit})
                response.raise_for_status()
                candidates = self._parse(response.text, mirror, limit)
                if candidates:
                    return candidates
            except httpx.HTTPError:
                continue
        return []

    def _parse(self, html: str, base: str, limit: int) -> list[Candidate]:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", class_="c") or soup.find("table", id="tablelibgen")
        if not table:
            return []
        results = []
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 9:
                continue
            offset = 0 if len(cells) == 9 else 2
            title_cell = cells[offset]
            title = title_cell.get_text(" ", strip=True)
            author = cells[1].get_text(" ", strip=True)
            year_index, language_index, size_index, ext_index = ((3, 4, 6, 7) if len(cells) == 9 else (4, 6, 7, 8))
            if cells[ext_index].get_text(strip=True).lower() != "pdf":
                continue
            links = cells[-1].find_all("a", href=True)
            href = next((link["href"] for link in links if link["href"]), "")
            page_url = urljoin(base, href)
            provider_id = (re.search(r"[a-fA-F0-9]{32}", href) or [page_url])[0]
            results.append(Candidate(
                provider=self.name, provider_id=provider_id, title=title, authors=(author,) if author else (),
                language=cells[language_index].get_text(strip=True), year=cells[year_index].get_text(strip=True),
                size_bytes=_size(cells[size_index].get_text(strip=True)), page_url=page_url,
            ))
            if len(results) >= limit:
                break
        return results

    def resolve(self, candidate: Candidate) -> Candidate:
        if candidate.download_url:
            return candidate
        response = self.client.get(candidate.page_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "get.php" in href or href.lower().endswith(".pdf"):
                return replace(candidate, download_url=urljoin(str(response.url), href))
        raise ProviderError("LibGen 详情页没有可解析的 PDF 链接")


class AnnasArchiveProvider(HttpProvider):
    name = "annas_archive"
    base = "https://annas-archive.gl"

    def search(self, query: str, limit: int = 10) -> list[Candidate]:
        response = self.client.get(f"{self.base}/search", params={"q": query}, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        for link in soup.find_all("a", href=re.compile(r"/md5/")):
            title = link.get_text(" ", strip=True)
            if len(title) < 5:
                continue
            href = urljoin(self.base, link["href"])
            results.append(Candidate(self.name, link["href"].rstrip("/").split("/")[-1], title, page_url=href))
            if len(results) >= limit:
                break
        return results

    def resolve(self, candidate: Candidate) -> Candidate:
        response = self.client.get(candidate.page_url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.lower().endswith(".pdf") or "libgen" in href.lower():
                return replace(candidate, download_url=urljoin(str(response.url), href))
        raise ProviderError("Anna's Archive 详情页没有可解析的 PDF 链接")


class ZLibraryProvider(HttpProvider):
    name = "zlib"
    base = "https://singlelogin.re"

    def search(self, query: str, limit: int = 10) -> list[Candidate]:
        response = self.client.get(f"{self.base}/s/", params={"q": query}, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        for link in soup.find_all("a", href=re.compile(r"/book/|/b/|/md5/")):
            title = link.get_text(" ", strip=True)
            if len(title) < 5:
                continue
            page_url = urljoin(self.base, link["href"])
            results.append(Candidate(self.name, page_url.rstrip("/").split("/")[-1], title, page_url=page_url))
            if len(results) >= limit:
                break
        return results

    def resolve(self, candidate: Candidate) -> Candidate:
        response = self.client.get(candidate.page_url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "download" in href.lower() or href.lower().endswith(".pdf"):
                return replace(candidate, download_url=urljoin(str(response.url), href))
        raise ProviderError("Z-Library 详情页没有可解析的 PDF 链接")


PROVIDER_TYPES = {
    "internet_archive": InternetArchiveProvider,
    "open_library": OpenLibraryProvider,
    "google_books": GoogleBooksProvider,
    "libgen": LibgenProvider,
    "annas_archive": AnnasArchiveProvider,
    "zlib": ZLibraryProvider,
}


def create_book_providers(names: tuple[str, ...], **kwargs) -> list[BookProvider]:
    unknown = sorted(set(names) - PROVIDER_TYPES.keys())
    if unknown:
        raise ValueError(f"未知教材来源：{', '.join(unknown)}")
    return [PROVIDER_TYPES[name](**kwargs) for name in names]
