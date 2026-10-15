"""带重试、逐跳复检、字节硬顶、校验和原子落盘的通用 PDF 下载器 + 书籍验收门（QED-050/068-4）。"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
import re
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import httpx
from pypdf import PdfReader

from qed_tracker.matching import _similarity

logger = logging.getLogger("qed_tracker.downloader")

# QED-068 C 步（068-4）下载器安全件参数
MAX_REDIRECT_HOPS = 5  # 手动逐跳重定向上限（超过即拒绝）
DEFAULT_MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024  # 字节硬顶：现库最大成品 PDF 约 121.5 MiB，取 4 倍余量
_ALLOWED_SCHEMES = frozenset({"http", "https"})
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class DownloadError(RuntimeError):
    pass


class DownloadBlockedError(DownloadError):
    """安全/预算拒绝（异 scheme、非公网主机、超跳数、字节硬顶）：终止性失败，不进重试循环。

    重试会重复发起同一风险连接（如再次指向内网），故与「网络抖动可重试」的 DownloadError 区分。
    """


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


def _resolve_host_ips(host: str) -> list[str]:
    """主机名 → IP 列表（逐跳复检用）；数字地址直接返回，不发 DNS 查询。

    测试经 `tests/conftest.py` 的 autouse `stub_dns` 打桩本函数，默认测试零公网、
    零真实 DNS（口径见 `docs/standards/testing.md`）。
    """
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return [host]
    return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})


def _guard_redirect_target(url: httpx.URL, *, hop: int) -> str:
    """逐跳复检（连接**前**执行）：scheme 限 http/https，主机解析出的每个 IP 须公网可路由。

    非公网 = private/loopback/link-local/multicast/reserved/unspecified（`ipaddress.is_global`
    取反），任一命中即拒；DNS 失败同样拒（fail-closed）。返回主机名供错误文案使用。
    内网代理等白名单场景由调用方显式配置直连 URL，不走重定向放行（068-4 第 1 条注记）。
    """
    if url.scheme not in _ALLOWED_SCHEMES:
        raise DownloadBlockedError(
            f"第 {hop} 跳 scheme 非 http/https：{url.scheme or '（缺 scheme）'}，主机 {url.host or '（缺主机）'}"
        )
    host = url.host
    if not host:
        raise DownloadBlockedError(f"第 {hop} 跳目标缺少主机：{url}")
    try:
        ips = _resolve_host_ips(host)
    except OSError as exc:
        raise DownloadBlockedError(f"第 {hop} 跳主机 {host} 解析失败，按 fail-closed 拒绝：{exc}") from exc
    if not ips:
        raise DownloadBlockedError(f"第 {hop} 跳主机 {host} 无解析结果，按 fail-closed 拒绝")
    for ip in ips:
        try:
            address = ipaddress.ip_address(ip)
        except ValueError as exc:
            raise DownloadBlockedError(f"第 {hop} 跳主机 {host} 解析结果非法：{ip}") from exc
        if not address.is_global:
            raise DownloadBlockedError(
                f"第 {hop} 跳主机 {host} 解析到非公网地址 {ip}，已拒绝（上限内主机白名单需显式配置）"
            )
    return host


class DownloadManager:
    def __init__(
        self,
        *,
        proxy: str = "",
        timeout: float = 30.0,
        retries: int = 3,
        tls_verify: bool = True,
        max_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
    ):
        self.retries = max(1, retries)
        self.max_bytes = max_bytes
        kwargs: dict = {
            # QED-068 C 步：重定向交由 download() 手动逐跳复检，客户端不自动跟随
            # （自动跟随时已连接过中间主机，检查点来不及）。
            "follow_redirects": False,
            "timeout": timeout,
            "verify": tls_verify,
        }
        if proxy:
            kwargs["proxy"] = proxy
        self.client = httpx.Client(**kwargs)

    def close(self) -> None:
        self.client.close()

    def download(self, url: str, destination: Path, *, on_start: Callable[[], None] | None = None) -> DownloadedFile:
        """下载到 destination；`on_start` 在首个 chunk 写入 .part 前回调一次（可选）。

        QED-050 候选级预算释放点（book_fetch.py）：「开始稳定下载」= GET 2xx +
        首个 chunk 已写入 .part，此后该候选允许跑完；默认 None 不改变既有行为。
        QED-068 C 步：重定向手动逐跳（≤5 跳）复检、字节硬顶 `self.max_bytes`；
        安全/预算拒绝（`DownloadBlockedError`）为终止性失败，不重试。
        """
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(destination.suffix + ".part")
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                partial.unlink(missing_ok=True)
                self._fetch_streamed(url, partial, on_start=on_start)
                digest, size, page_count = inspect_pdf(partial)
                os.replace(partial, destination)
                return DownloadedFile(destination, digest, size, page_count)
            except DownloadBlockedError:
                partial.unlink(missing_ok=True)
                raise
            except (httpx.HTTPError, httpx.InvalidURL, OSError, DownloadError) as exc:
                last_error = exc
                if isinstance(exc, DownloadError):
                    partial.unlink(missing_ok=True)
                if attempt + 1 < self.retries:
                    time.sleep(min(2**attempt, 4))
        partial.unlink(missing_ok=True)
        raise DownloadError(f"下载失败：{last_error}") from last_error

    def _fetch_streamed(
        self, url: str, partial: Path, *, on_start: Callable[[], None] | None
    ) -> None:
        """手动逐跳重定向 + 流式写盘：每跳在发起连接前复检，累计字节超硬顶即中断。

        相对 Location 按当前 URL 解析；缺 Location 的重定向按普通失败处理（可重试）。
        """
        current = httpx.URL(url)
        for hop in range(MAX_REDIRECT_HOPS + 1):
            host = _guard_redirect_target(current, hop=hop)
            with self.client.stream("GET", current) as response:
                if response.status_code in _REDIRECT_STATUSES:
                    if hop >= MAX_REDIRECT_HOPS:
                        raise DownloadBlockedError(
                            f"重定向超过 {MAX_REDIRECT_HOPS} 跳上限：停在第 {hop} 跳主机 {host}"
                        )
                    location = response.headers.get("location")
                    if not location:
                        raise DownloadError(f"重定向响应缺少 Location 头：{current}（第 {hop} 跳，主机 {host}）")
                    current = httpx.URL(urljoin(str(current), location))
                    continue
                response.raise_for_status()
                self._write_stream(response, partial, host=host, hop=hop, on_start=on_start)
                return

    def _write_stream(
        self, response, partial: Path, *, host: str, hop: int, on_start: Callable[[], None] | None
    ) -> None:
        written = 0
        with partial.open("wb") as stream:
            announced = False
            # 无参 iter_bytes：逐网络 chunk 惰性产出（带 chunk_size 时 httpx
            # ByteChunker 会攒满该字节数才吐首块，小文件整个下载期无 chunk
            # 写入 .part，预算释放点语义失效）
            for chunk in response.iter_bytes():
                written += len(chunk)
                if written > self.max_bytes:
                    raise DownloadBlockedError(
                        f"下载字节超上限 {self.max_bytes}：主机 {host}（第 {hop} 跳），已读 {written} 字节"
                    )
                if not announced:
                    announced = True
                    if on_start is not None:
                        try:
                            on_start()
                        except Exception:  # noqa: BLE001 - 信号回调不阻塞下载
                            pass
                stream.write(chunk)
