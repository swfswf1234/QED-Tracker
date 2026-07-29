"""带续传、校验和原子落盘的通用 PDF 下载器。"""

from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from pypdf import PdfReader


class DownloadError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DownloadedFile:
    path: Path
    sha256: str
    size_bytes: int
    page_count: int


def safe_filename(value: str, fallback: str = "resource") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", value).strip()
    cleaned = re.sub(r"\s+", "_", cleaned).rstrip(". ")
    return (cleaned[:120] or fallback) + ("" if cleaned.lower().endswith(".pdf") else ".pdf")


def inspect_pdf(path: Path) -> tuple[str, int, int]:
    with path.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise DownloadError("下载内容不是 PDF")
    try:
        page_count = len(PdfReader(path, strict=False).pages)
    except Exception as exc:
        raise DownloadError(f"PDF 结构无效：{exc}") from exc
    if page_count < 1:
        raise DownloadError("PDF 没有可读取页面")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size, page_count


class DownloadManager:
    def __init__(self, *, proxy: str = "", timeout: float = 30.0, retries: int = 3, tls_verify: bool = True):
        self.retries = max(1, retries)
        kwargs: dict = {"follow_redirects": True, "timeout": timeout, "verify": tls_verify}
        if proxy:
            kwargs["proxy"] = proxy
        self.client = httpx.Client(**kwargs)

    def close(self) -> None:
        self.client.close()

    def download(self, url: str, destination: Path) -> DownloadedFile:
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(destination.suffix + ".part")
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                if partial.exists():
                    try:
                        digest, size, page_count = inspect_pdf(partial)
                    except DownloadError:
                        pass
                    else:
                        os.replace(partial, destination)
                        return DownloadedFile(destination, digest, size, page_count)
                offset = partial.stat().st_size if partial.exists() else 0
                headers = {"Range": f"bytes={offset}-"} if offset else {}
                with self.client.stream("GET", url, headers=headers) as response:
                    response.raise_for_status()
                    append = offset > 0 and response.status_code == 206
                    if offset and not append:
                        offset = 0
                    mode = "ab" if append else "wb"
                    with partial.open(mode) as stream:
                        for chunk in response.iter_bytes(1024 * 1024):
                            stream.write(chunk)
                digest, size, page_count = inspect_pdf(partial)
                os.replace(partial, destination)
                return DownloadedFile(destination, digest, size, page_count)
            except (httpx.HTTPError, OSError, DownloadError) as exc:
                last_error = exc
                if isinstance(exc, DownloadError):
                    partial.unlink(missing_ok=True)
                if attempt + 1 < self.retries:
                    time.sleep(min(2 ** attempt, 4))
        partial.unlink(missing_ok=True)
        raise DownloadError(f"下载失败：{last_error}") from last_error
