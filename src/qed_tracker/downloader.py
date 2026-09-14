"""带重试、校验和原子落盘的通用 PDF 下载器 + 书籍机器验收门（QED-050）。"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
from pypdf import PdfReader

from qed_tracker.matching import _similarity

logger = logging.getLogger("qed_tracker.downloader")


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


@dataclass(frozen=True, slots=True)
class AcceptanceResult:
    """书籍机器验收结果（QED-050 阶段 4，无 LLM）：硬门槛全过 accepted=True。

    text_chars 为文本层软信号（pypdf extract_text 字符数）：-1=无法评估（非 PDF/
    解析失败/加密），0=无文本层（扫描版/空白页）；只记录进 qt_sources.note 不参与
    判定（防误杀扫描版）。
    """

    accepted: bool
    page_count: int
    size_bytes: int
    text_chars: int
    reasons: tuple[str, ...]  # 拒绝门槛项逐条记录（空 = 通过）


def accept_pdf(path: Path, *, min_pages: int = 10, min_size: int = 204800) -> AcceptanceResult:
    """书籍机器验收门：魔数 / pypdf 可解析（strict=False）/ 非加密 / 页数 / 大小。

    任一硬门槛不满足即拒绝（reasons 逐项记录，供编排层换下一候选 + 留痕）。
    在 staging 上调用；未过门槛文件由调用方清理、永不进入数据根成品区 raw/。
    加密文件（is_encrypted）不放行——空密码可解的属主加密同样拒绝，取页数前先判。
    """
    reasons: list[str] = []
    with path.open("rb") as stream:
        header = stream.read(5)
    if header != b"%PDF-":
        reasons.append("魔数非 %PDF-")
    size = path.stat().st_size
    if size < min_size:
        reasons.append(f"大小 {size} < 下限 {min_size}")

    reader: PdfReader | None = None
    page_count = 0
    text_chars = -1
    if header == b"%PDF-":
        try:
            reader = PdfReader(path, strict=False)
        except Exception as exc:
            reasons.append(f"PDF 结构无效：{exc}")
        if reader is not None and reader.is_encrypted:
            reasons.append("PDF 已加密")
            reader = None
    if reader is not None:
        try:
            page_count = len(reader.pages)
        except Exception as exc:
            page_count = 0
            reasons.append(f"PDF 结构无效：{exc}")
        else:
            if page_count < min_pages:
                reasons.append(f"页数 {page_count} < 下限 {min_pages}")
            try:
                text_chars = len("".join(page.extract_text() or "" for page in reader.pages))
            except Exception:
                text_chars = -1
    return AcceptanceResult(
        accepted=not reasons,
        page_count=page_count,
        size_bytes=size,
        text_chars=text_chars,
        reasons=tuple(reasons),
    )


@dataclass(frozen=True, slots=True)
class ContentVerificationResult:
    """下载后内容校验结果（REQ-019, QED-066）：PDF 首页文本 vs 登记标题。

    passed=True 表示标题匹配（或无法评估时默认放行）；passed=False 时 score < 阈值，
    调用方可将 message 写入 qt_sources.note 作为软信号留痕。
    """

    passed: bool
    score: float  # 相似度（0.0~1.0），无法评估时为 1.0
    message: str  # 人类可读说明


def verify_content(
    path: Path,
    expected_titles: list[str],
    *,
    threshold: float = 0.5,
    max_chars: int = 500,
) -> ContentVerificationResult:
    """下载后内容校验：提取 PDF 首页文本，与登记标题做相似度比对（REQ-019, QED-066）。

    软信号——只记录不拒绝：扫描版/无文本层/提取失败时默认放行（passed=True）；
    相似度 < threshold 时 passed=False，调用方可将 message 写入 qt_sources.note。
    """
    if not expected_titles:
        return ContentVerificationResult(passed=True, score=1.0, message="无基准标题，跳过内容校验")

    # 提取首页文本
    try:
        reader = PdfReader(str(path), strict=False)
        if not reader.pages:
            return ContentVerificationResult(passed=True, score=1.0, message="PDF 无页面，跳过内容校验")
        first_page_text = reader.pages[0].extract_text() or ""
    except Exception as exc:
        logger.debug("内容校验：PDF 首页文本提取失败：%s", exc)
        return ContentVerificationResult(passed=True, score=1.0, message=f"首页文本提取失败，跳过：{exc}")

    # 清理文本：取前 max_chars 字符，去掉多余空白
    snippet = re.sub(r"\s+", " ", first_page_text[:max_chars]).strip()
    if not snippet:
        return ContentVerificationResult(passed=True, score=1.0, message="首页无文本层（扫描版），跳过内容校验")

    # 与每个期望标题比对，取最高分
    best_score = max((_similarity(snippet, title) for title in expected_titles if title), default=1.0)
    if best_score >= threshold:
        return ContentVerificationResult(passed=True, score=best_score,
                                         message=f"标题匹配（score={best_score:.2f}）")
    return ContentVerificationResult(
        passed=False, score=best_score,
        message=f"标题不匹配（score={best_score:.2f} < {threshold}），首页片段：{snippet[:80]}...",
    )


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

    def download(self, url: str, destination: Path, *, on_start: Callable[[], None] | None = None) -> DownloadedFile:
        """下载到 destination；`on_start` 在首个 chunk 写入 .part 前回调一次（可选）。

        QED-050 候选级预算释放点（book_fetch.py）：「开始稳定下载」= GET 2xx +
        首个 chunk 已写入 .part，此后该候选允许跑完；默认 None 不改变既有行为。
        """
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(destination.suffix + ".part")
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                partial.unlink(missing_ok=True)
                with self.client.stream("GET", url) as response:
                    response.raise_for_status()
                    with partial.open("wb") as stream:
                        announced = False
                        # 无参 iter_bytes：逐网络 chunk 惰性产出（带 chunk_size 时 httpx
                        # ByteChunker 会攒满该字节数才吐首块，小文件整个下载期无 chunk
                        # 写入 .part，预算释放点语义失效）
                        for chunk in response.iter_bytes():
                            if not announced:
                                announced = True
                                if on_start is not None:
                                    try:
                                        on_start()
                                    except Exception:  # noqa: BLE001 - 信号回调不阻塞下载
                                        pass
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
