"""Open textbook source probes.

These adapters are for discovery/probing only. The one-click downloader keeps using
the known download chain unless a source is explicitly integrated later.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass

from app.tools._http import make_http_client


@dataclass
class SourceProbeResult:
    source: str
    status: str
    title: str = ""
    author: str = ""
    url: str = ""
    access_type: str = ""
    reason: str = ""


class OpenLibraryProbe:
    name = "openlibrary"
    base = "https://openlibrary.org"

    def __init__(self, timeout: float = 20.0, proxy: str = ""):
        self.client = make_http_client(timeout, proxy)

    def search(self, query: str, max_results: int = 5) -> list[SourceProbeResult]:
        try:
            resp = self.client.get(
                f"{self.base}/search.json",
                params={"q": query, "limit": max_results, "fields": "title,author_name,ia,ebook_access"},
                headers={"User-Agent": "QED-Tracker/0.2 textbook source probe"},
            )
            resp.raise_for_status()
            docs = resp.json().get("docs", [])
        except Exception as exc:
            return [SourceProbeResult(self.name, "FAIL", reason=str(exc))]
        results = []
        for doc in docs[:max_results]:
            ia_ids = doc.get("ia") or []
            ia = ia_ids[0] if ia_ids else ""
            results.append(SourceProbeResult(
                source=self.name,
                status="FOUND" if ia else "METADATA_ONLY",
                title=doc.get("title", ""),
                author=", ".join(doc.get("author_name", [])[:3]),
                url=f"https://archive.org/details/{ia}" if ia else "",
                access_type=doc.get("ebook_access", ""),
                reason="internet archive id available" if ia else "metadata only",
            ))
        return results or [SourceProbeResult(self.name, "PASS", reason="no results")]

    def close(self):
        self.client.close()


class InternetArchiveProbe:
    name = "internetarchive"
    base = "https://archive.org"

    def __init__(self, timeout: float = 20.0, proxy: str = ""):
        self.client = make_http_client(timeout, proxy)

    def search(self, query: str, max_results: int = 5) -> list[SourceProbeResult]:
        try:
            resp = self.client.get(
                f"{self.base}/advancedsearch.php",
                params={
                    "q": f'title:({query}) AND mediatype:texts',
                    "fl[]": ["identifier", "title", "creator"],
                    "rows": max_results,
                    "output": "json",
                },
                headers={"User-Agent": "QED-Tracker/0.2 textbook source probe"},
            )
            resp.raise_for_status()
            docs = resp.json().get("response", {}).get("docs", [])
        except Exception as exc:
            return [SourceProbeResult(self.name, "FAIL", reason=str(exc))]
        results = []
        for doc in docs[:max_results]:
            identifier = doc.get("identifier", "")
            results.append(SourceProbeResult(
                source=self.name,
                status="FOUND" if identifier else "METADATA_ONLY",
                title=doc.get("title", ""),
                author=doc.get("creator", "") if isinstance(doc.get("creator", ""), str) else ", ".join(doc.get("creator", [])[:3]),
                url=f"https://archive.org/details/{identifier}" if identifier else "",
                access_type="texts",
                reason="check item files for PDF/EPUB",
            ))
        return results or [SourceProbeResult(self.name, "PASS", reason="no results")]

    def close(self):
        self.client.close()


class GoogleBooksProbe:
    name = "googlebooks"
    base = "https://www.googleapis.com/books/v1"

    def __init__(self, timeout: float = 20.0, proxy: str = ""):
        self.client = make_http_client(timeout, proxy)

    def search(self, query: str, max_results: int = 5) -> list[SourceProbeResult]:
        try:
            resp = self.client.get(
                f"{self.base}/volumes",
                params={"q": query, "maxResults": max_results, "filter": "ebooks"},
                headers={"User-Agent": "QED-Tracker/0.2 textbook source probe"},
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
        except Exception as exc:
            return [SourceProbeResult(self.name, "FAIL", reason=str(exc))]
        results = []
        for item in items[:max_results]:
            info = item.get("volumeInfo", {})
            access = item.get("accessInfo", {})
            pdf = access.get("pdf", {})
            results.append(SourceProbeResult(
                source=self.name,
                status="DOWNLOADABLE" if pdf.get("downloadLink") else "METADATA_ONLY",
                title=info.get("title", ""),
                author=", ".join(info.get("authors", [])[:3]),
                url=pdf.get("downloadLink") or info.get("infoLink", ""),
                access_type=access.get("accessViewStatus", ""),
                reason="pdf download link available" if pdf.get("downloadLink") else "no PDF download link",
            ))
        return results or [SourceProbeResult(self.name, "PASS", reason="no results")]

    def close(self):
        self.client.close()


def manual_search_urls(query: str) -> list[SourceProbeResult]:
    quoted = urllib.parse.quote_plus(query)
    return [
        SourceProbeResult("oapen", "MANUAL", url=f"https://www.oapen.org/search?query={quoted}", reason="open access books search"),
        SourceProbeResult("openalex", "MANUAL", url=f"https://api.openalex.org/works?search={quoted}", reason="open access metadata search"),
        SourceProbeResult("crossref", "MANUAL", url=f"https://api.crossref.org/works?query.bibliographic={quoted}", reason="metadata search"),
    ]
