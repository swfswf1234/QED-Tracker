"""书籍自动取书执行器（方案 A，2026-08-28）：搜索 → 逐候选限时下载 → 状态转移与渠道留痕。

背景：8901 books API 此前只有状态转移端点（decide/start/...），点击"下载"后没有任何
组件执行实际下载，书行永远停在 downloading。本模块把 CLI mainline download 的自动链
（BookService.search → 逐候选下载 → complete_download）移植为可注入、可测试的用例层，
供 API 后台任务（book_download）调用。

超时语义（用户裁决 2026-08-28）：每个候选一个总预算（默认 600s，QED_FETCH_ATTEMPT_TIMEOUT），
预算内无响应/未完成即记失败并切换下一候选；全部候选失败后书行置 failed，任务以
BookFetchError 结束并附人工下载指引（metadata_only 候选的链接清单）。

并发与隔离：每次 fetch 经 factory 新建独立 BookService（providers + downloader + inventory），
结束即 close（顺带中止超时候选遗留的孤儿下载线程的连接）；staging 路径带唯一 tag，
避免孤儿线程与后续候选写同名 .download/.part 文件。
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path

from qed_tracker.application.books import BookService
from qed_tracker.application.resources import ResourceService
from qed_tracker.config import Settings
from qed_tracker.db.knowledge_repository import InvalidTransition, KnowledgeRepository
from qed_tracker.downloader import DownloadManager
from qed_tracker.inventory import Inventory
from qed_tracker.models import Availability, Candidate
from qed_tracker.providers.books import create_book_providers

ProgressCallback = Callable[[int, str], None]

_ALLOWED_FETCH_STATUSES = ("candidate", "decided", "failed")


class BookFetchError(RuntimeError):
    """全部自动候选失败：消息携带逐候选摘要与人工下载指引。"""


def build_book_service(settings: Settings, names: tuple[str, ...] | None = None) -> BookService:
    """每次取书任务新建独立 BookService（与 CLI _book_service 同构，任务结束 close）。"""
    providers = create_book_providers(
        names or settings.sources,
        proxy=settings.proxy,
        timeout=settings.timeout_seconds,
        tls_verify=settings.tls_verify,
    )
    downloader = DownloadManager(
        proxy=settings.proxy,
        timeout=settings.timeout_seconds,
        retries=settings.retries,
        tls_verify=settings.tls_verify,
    )
    return BookService(providers, ResourceService(Inventory(settings.data_root), downloader))


class BookFetchService:
    """对单个书行执行自动取书；输入 book_id（UI 决定的具体书行，非 CLI 的 knowledge 粗选）。"""

    def __init__(
        self,
        repo: KnowledgeRepository,
        service_factory: Callable[[], BookService],
        *,
        data_root: Path,
        attempt_timeout: float = 600.0,
    ):
        self.repo = repo
        self.service_factory = service_factory
        self.data_root = data_root
        self.attempt_timeout = max(0.05, attempt_timeout)

    # ---------------- 公共入口 ----------------

    def fetch(self, book_id: str, *, progress: ProgressCallback | None = None) -> dict:
        book = self.repo.get_book(book_id, include_hidden=True)
        if book is None:
            raise KeyError(f"书行不存在：{book_id}")
        if book.status not in _ALLOWED_FETCH_STATUSES:
            raise ValueError(
                f"书行状态 {book.status} 不可自动取书（仅 candidate/decided/failed）；"
                "downloading 卡住请先 cancel 复位"
            )
        if book.status == "candidate":
            self.repo.decide_book(book_id)
        self.repo.start_download(book_id)

        authors = " ".join(a for a in (book.authors or []) if a).strip()
        # 检索词构造（4.1 优化点落地）：决策引用含 original_title（英文原名）时优先，
        # 中文名/音译名在各来源（IA/OL/GB）命中率低；英文查询无候选时回退中文书名。
        original_title = ""
        knowledge = self.repo.get_knowledge(book.knowledge_id)
        if knowledge is not None and isinstance(knowledge.textbook_ref, dict):
            original_title = str(knowledge.textbook_ref.get("original_title", "") or "").strip()
        queries = [f"{q} {authors}".strip() for q in (original_title, book.title) if q]
        seen_queries: set[str] = set()
        queries = [q for q in queries if q and not (q in seen_queries or seen_queries.add(q))]
        attempts: list[dict] = []

        def report(value: int, message: str) -> None:
            if progress is not None:
                progress(value, message)

        service = self.service_factory()
        try:
            candidates = []
            provider_failures: list = []
            seen_candidates: set[tuple[str, str, str]] = set()
            downloadable: list = []
            for index_q, query in enumerate(queries):
                report(10 + int(5 * index_q / len(queries)), f"搜索候选：{query}")
                ranked = service.search(query, limit=8)
                provider_failures.extend([name, error] for name, error in service.failures)
                for item in ranked:
                    c = item.candidate
                    key = (c.provider, c.provider_id, c.title.casefold())
                    if key in seen_candidates:
                        continue
                    seen_candidates.add(key)
                    candidates.append(c)
                    if c.availability == Availability.DOWNLOADABLE:
                        downloadable.append(c)
                if downloadable:
                    break  # 英文原名命中即止，避免多余来源调用（如 google_books 限流）
            manual = [self._guidance(c) for c in candidates if c.availability == Availability.METADATA_ONLY and c.links]
            if not downloadable:
                self.repo.add_source(book_id, channel="search", ok=False, note=f"无自动可下载候选（queries={queries}）")
                self._safe_fail(book_id)
                raise BookFetchError(self._failure_message(queries, attempts, manual, provider_failures))

            total = len(downloadable)
            for index, candidate in enumerate(downloadable, 1):
                report(
                    15 + int(75 * (index - 1) / total),
                    f"尝试 {index}/{total}：{candidate.provider} - {candidate.title}",
                )
                try:
                    record = self._timed_download(service, candidate)
                except FuturesTimeoutError:
                    note = f"超时（{int(self.attempt_timeout)}s 无响应/未完成）"
                    attempts.append(
                        {"provider": candidate.provider, "title": candidate.title, "ok": False, "note": note}
                    )
                    self.repo.add_source(book_id, channel=candidate.provider, ok=False, note=note)
                    continue
                except Exception as exc:  # noqa: BLE001 - 逐候选兜底：失败留痕换下一个
                    note = str(exc)[:300]
                    attempts.append(
                        {"provider": candidate.provider, "title": candidate.title, "ok": False, "note": note}
                    )
                    self.repo.add_source(book_id, channel=candidate.provider, ok=False, note=note)
                    continue
                attempts.append(
                    {"provider": candidate.provider, "title": candidate.title, "ok": True, "note": record.resource_id}
                )
                self.repo.add_source(book_id, channel=candidate.provider, ok=True, note=record.resource_id)
                final = self.repo.complete_download(
                    book_id,
                    sha256=record.sha256,
                    relative_path=record.file["relative_path"],
                    page_count=record.file.get("page_count"),
                    absolute_path=str(record.absolute_path(self.data_root)),
                    file_name=Path(record.file["relative_path"]).name,
                )
                report(95, f"下载完成：{record.file['relative_path']}")
                return {
                    "ok": True,
                    "book_id": book_id,
                    "status": final.status,
                    "attempts": attempts,
                    "provider_failures": provider_failures,
                    "manual_guidance": manual,
                    "resource_id": record.resource_id,
                    "relative_path": record.file["relative_path"],
                }
            self.repo.add_source(book_id, channel="download", ok=False, note="全部自动候选失败")
            self._safe_fail(book_id)
            raise BookFetchError(self._failure_message(queries, attempts, manual, provider_failures))
        except BookFetchError:
            raise
        except Exception as exc:  # noqa: BLE001 - 任务层兜底：书行复位为 failed
            self._safe_fail(book_id)
            raise BookFetchError(f"取书任务异常：{exc}") from exc
        finally:
            service.close()

    def cancel(self, book_id: str, *, note: str = "cancel", by: str = "web") -> dict:
        """downloading 卡住复位 → decided（UI/运维入口，供 fetch 前清理失联状态）。"""
        return self.repo.cancel_download(book_id, note=note, by=by).to_dict()

    # ---------------- 内部 ----------------

    def _timed_download(self, service: BookService, candidate: Candidate):
        """单候选下载，预算内未完成即放弃（孤儿线程随 service.close 断连自灭）。

        staging 唯一 tag：孤儿线程与后续候选不会写同名 .download/.part。
        """
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qed-fetch")
        tag = uuid.uuid4().hex[:8]

        def _download():
            return service.download(candidate, staging_tag=tag)

        try:
            return executor.submit(_download).result(timeout=self.attempt_timeout)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _guidance(candidate: Candidate) -> dict:
        return {
            "provider": candidate.provider,
            "title": candidate.title,
            "links": [{"label": link.label, "url": link.url, "kind": link.kind} for link in candidate.links],
        }

    def _safe_fail(self, book_id: str) -> None:
        # 常规路径状态已保证 downloading → failed 合法；并发场景下可能已被转移，静默忽略。
        try:
            self.repo.fail_download(book_id)
        except (InvalidTransition, KeyError):
            pass

    @staticmethod
    def _failure_message(queries: list[str], attempts: list[dict], manual: list[dict], provider_failures: list) -> str:
        lines = [f"全部自动候选失败，已转人工处理（queries={queries}）。"]
        for attempt in attempts:
            lines.append(f"- [{attempt['provider']}] {attempt['title']}: {attempt['note']}")
        for name, error in provider_failures:
            lines.append(f"- 来源搜索失败 {name}: {error}")
        if manual:
            lines.append("人工下载指引：")
            for item in manual:
                links = ", ".join(link["url"] for link in item["links"])
                lines.append(f"- [{item['provider']}] {item['title']}: {links}")
        return "\n".join(lines)
