"""书籍五阶段取书编排（QED-050，2026-09 设计裁决）与登记链路。

五阶段：检索 → 确认（确定性预筛 → 介绍查取(enrich) → LLM 确认） → 下载（候选级预算）
→ 机器验收（staging，无 LLM）→ 登记（mark_owned 唯一写入口）。语义唯一事实源：
docs/design/download-pipeline.md（九项裁决）。

- 阶段1 检索：渠道遍历顺序 = QED_SOURCES；硬编码检索词规则集 ① original_title+第一作者姓
  → ② title+作者（排除 translator）→ ③ title → ④ title+part，渠道内命中即止、跨渠道
  独立执行。全部渠道×query 无可用候选后，LLM 检索词变体兜底一次（book-query/variants@v1，
  书级全局、不逐渠道触发），变体重走渠道×query 循环；LLM 不可用 → 转人工指引。
- 阶段2 确认：预筛只拒硬失配（语言冲突/标题<0.82/作者全部<0.72，元数据缺失不硬拒，
  复用 matching.py 相似度函数）；介绍查取在 providers 内零新增 HTTP 完成（enrich 字段
  随 search/resolve 响应带回）；LLM 确认 book-confirm/assess@v1，verdict ∈
  {confirmed, uncertain}，confirmed→自动下载、uncertain→qt_sources 留痕换下一候选；
  LLM 失败/预算耗尽按 uncertain 降级，不阻塞。QED_BOOK_LLM_CONFIRM=false 时预筛通过
  即下载（明示降级风险）。
- 阶段3 下载：候选级预算（默认 300s）覆盖 resolve→开始稳定下载；「开始稳定下载」=
  首个 chunk 写入 .part（预算释放，允许跑完）；未到释放点超时 → 候选失败换下一个，
  孤儿线程随 service.close() 断连自灭；来源声明 md5 校验保留。
- 阶段4 机器验收：在 staging（tmp/qed-tracker/downloads）执行 accept_pdf 硬门槛
  （魔数/可解析/非加密/页数/大小）+ 文本层软信号（只记录不拒绝）；未过门槛文件停留
  staging 由下载器清理，永不进入数据根成品区。
- 阶段5 登记：repo.mark_owned 唯一写 qt_books.holding/file_path；资源 JSON 登记
  register_candidate；已 owned 书 fetch → no-op。LLM 判断不写资源事实。
- 教程级批处理：refs 聚合书集（去重）→ 排除已 owned → 默认 textbook_ref+exercise_ref
  （include_parallel 显式纳入 parallel_ref）→ 单任务顺序逐书 → 部分失败不中断。

并发与隔离：每次 fetch 经 factory 新建独立 BookService（providers + downloader +
inventory）与 advisor，结束即 close（中止超时候选遗留的孤儿下载线程连接）；staging
路径带唯一 tag，孤儿线程与后续候选不写同名 .download/.part 文件。
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from pathlib import Path

from qed_tracker.application.books import BookService
from qed_tracker.application.resources import ResourceService
from qed_tracker.config import Settings
from qed_tracker.db.knowledge_repository import KnowledgeRepository, _refs_book_ids
from qed_tracker.downloader import DownloadManager, accept_pdf
from qed_tracker.inventory import Inventory, raw_course_dir, raw_general_dir
from qed_tracker.matching import _language, _similarity
from qed_tracker.models import Availability, BookExpectation, Candidate, ResourceKind
from qed_tracker.providers.books import create_book_providers

ProgressCallback = Callable[[int, str], None]


class BookFetchError(RuntimeError):
    """全部自动候选失败：消息携带逐候选摘要、预筛失配与人工下载指引。"""


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


@dataclass(frozen=True, slots=True)
class _Verdict:
    ok: bool  # True=confirmed（或 LLM 关闭降级放行）；False=uncertain/LLM 不可用
    note: str = ""


def _surname(name: str) -> str:
    parts = name.split()
    return parts[-1] if len(parts) > 1 else name


def _hardcoded_queries(book: BookExpectation) -> list[str]:
    """阶段1 硬编码检索词规则集（设计表 ①~④）：出版社/丛书/年份不进检索词。"""
    queries: list[str] = []
    if book.original_title:
        queries.append(" ".join([book.original_title, _surname(book.authors[0])] if book.authors else [book.original_title]).strip())
    if book.authors:
        queries.append(f"{book.title} {' '.join(book.authors)}".strip())
    queries.append(book.title)
    if book.part:
        queries.append(f"{book.title} {book.part}".strip())
    return list(dict.fromkeys(q for q in queries if q))


def _expectation(book) -> BookExpectation:
    """qt_books 行 → 期望元数据（authors 仅 role=author，translator 排除防污染）。"""
    authors = tuple(
        str(entry.get("name", "")).strip()
        for entry in (book.authors or [])
        if isinstance(entry, dict) and entry.get("role", "author") == "author"
    )
    return BookExpectation(
        title=book.title,
        original_title=(book.original_title or "").strip(),
        part=book.part or "",
        authors=tuple(name for name in authors if name),
        language=book.language or "",
        publisher=book.publisher or "",
        edition=book.edition or "",
        year=str(book.year) if book.year else "",
    )


def _prescreen_rejection(candidate: Candidate, book: BookExpectation) -> str:
    """阶段2 确定性预筛（不耗 LLM）：只拒硬失配，元数据缺失不硬拒；空串 = 通过。

    复用 matching.py 相似度函数（设计：取 match_candidate 的硬失配子集，不复用其
    strict 判定与 CatalogTarget 语义——冻结目录链路不动）。
    """
    if book.language and candidate.language and _language(candidate.language) != _language(book.language):
        return f"语言失配（期望 {book.language}，候选 {candidate.language}）"
    expected_titles = [title for title in (book.title, book.original_title) if title]
    if expected_titles and candidate.title:
        best = max(_similarity(candidate.title, title) for title in expected_titles)
        if best < 0.82:
            return f"标题相似度 {best:.2f} < 0.82"
    if candidate.authors and book.authors:
        actual = " ".join(candidate.authors)
        if max((_similarity(actual, author) for author in book.authors), default=0.0) < 0.72:
            return "作者与期望全部低相似"
    return ""


class BookFetchService:
    """对单册书执行五阶段取书，或按教程批处理；书级入口 fetch()，教程级入口 fetch_tutorial()。"""

    def __init__(
        self,
        repo: KnowledgeRepository,
        service_factory: Callable[[], BookService],
        *,
        data_root: Path,
        candidate_budget: float = 300.0,
        min_pages: int = 10,
        min_size_bytes: int = 204800,
        search_limit: int = 8,
        query_variants: int = 3,
        llm_query: bool = True,
        llm_confirm: bool = True,
        advisor_factory: Callable[[], object | None] | None = None,
    ):
        self.repo = repo
        self.service_factory = service_factory
        self.data_root = data_root
        self.candidate_budget = max(0.05, candidate_budget)
        self.min_pages = min_pages
        self.min_size_bytes = min_size_bytes
        self.search_limit = search_limit
        self.query_variants = max(1, query_variants)
        self.llm_query = llm_query
        self.llm_confirm = llm_confirm
        self.advisor_factory = advisor_factory

    # ---------------- 书级入口 ----------------

    def fetch(self, book_id: str, *, progress: ProgressCallback | None = None) -> dict:
        """书级五阶段取书：已 owned → no-op；成功 → holding=owned + file_path。"""
        book = self.repo.get_book(book_id)
        if book is None:
            raise KeyError(f"书籍不存在：{book_id}")
        if book.holding == "owned":
            return {"ok": True, "book_id": book_id, "skipped": True, "reason": "已 owned，无需取书",
                    "file_path": book.file_path or ""}
        expectation = _expectation(book)

        def report(value: int, message: str) -> None:
            if progress is not None:
                progress(value, message)

        advisor = self.advisor_factory() if self.advisor_factory is not None else None
        service = self.service_factory()
        state = _RoundState(book_id=book_id)
        try:
            report(5, f"取书：{book.title}")
            outcome, found_any = self._round(service, advisor, book, expectation, _hardcoded_queries(expectation), state, report)
            if not found_any:
                self.repo.add_source(
                    book_id, channel="search", ok=False,
                    note=f"零可用候选（queries={state.queries_used}）" + self._prescreen_note(state),
                    file_keywords="；".join(dict.fromkeys(state.queries_used)),
                )
                # 书级全局兜底：LLM 检索词变体一次（不逐渠道触发），变体重走渠道×query 循环
                if self.llm_query and advisor is not None:
                    report(35, "硬编码检索词耗尽，请求 LLM 检索词变体")
                    variants, variants_note = self._propose_variants(advisor, expectation)
                    if variants:
                        outcome, found_any = self._round(service, advisor, book, expectation, variants, state, report)
                        if not found_any:
                            self.repo.add_source(book_id, channel="search", ok=False,
                                                 note=f"LLM 变体零可用候选（queries={variants}）")
                    else:
                        note = variants_note or "LLM 检索词变体为空"
                        state.notices.append(note)
                        self.repo.add_source(book_id, channel="search", ok=False, note=note)
                elif self.llm_query:
                    note = "LLM 不可用，无法生成检索词变体"
                    state.notices.append(note)
                    self.repo.add_source(book_id, channel="search", ok=False, note=note)
            if outcome is None:
                self.repo.add_source(
                    book_id, channel="download", ok=False,
                    note=f"全部候选耗尽，转人工处理。{self._prescreen_note(state)}",
                    file_keywords="；".join(dict.fromkeys(state.queries_used)),
                )
                raise BookFetchError(self._failure_message(state))
            return outcome
        except BookFetchError:
            raise
        except Exception as exc:  # noqa: BLE001 - 任务层兜底：异常汇总为书级失败并留痕
            self.repo.add_source(book_id, channel="download", ok=False, note=f"取书任务异常：{exc}")
            raise BookFetchError(f"取书任务异常：{exc}") from exc
        finally:
            service.close()
            if advisor is not None and hasattr(advisor, "close"):
                advisor.close()

    # ---------------- 教程级入口 ----------------

    def fetch_tutorial(
        self, knowledge_id: str, *, include_parallel: bool = False, progress: ProgressCallback | None = None
    ) -> dict:
        """教程级批量取书：refs 聚合书集 → 排除已 owned/retired → 顺序逐书五阶段。

        部分失败不中断：成功的书保持 owned，失败的书汇总进任务结果（附人工指引）。
        """
        knowledge = self.repo.get_knowledge(knowledge_id)
        if knowledge is None:
            raise KeyError(f"教程不存在：{knowledge_id}")
        book_ids: list[str] = []
        ref_lists = [knowledge.textbook_ref or [], knowledge.exercise_ref or []]
        if include_parallel:
            ref_lists.append(knowledge.parallel_ref or [])
        for book_id in _refs_book_ids(*ref_lists):
            if book_id not in book_ids:
                book_ids.append(book_id)
        results: list[dict] = []
        for index, book_id in enumerate(book_ids):
            book = self.repo.get_book(book_id)
            if book is None or book.status == "retired":
                continue
            if book.holding == "owned":
                results.append({"book_id": book_id, "ok": True, "skipped": True, "reason": "已 owned"})
                continue
            if progress is not None:
                progress(int(90 * index / max(1, len(book_ids))), f"取书 {index + 1}/{len(book_ids)}：{book.title}")
            try:
                outcome = self.fetch(book_id)
                results.append({"book_id": book_id, "ok": True,
                                "file_path": outcome.get("file_path", ""), "skipped": outcome.get("skipped", False)})
            except BookFetchError as exc:
                results.append({"book_id": book_id, "ok": False, "error": str(exc)})
        failures = [item for item in results if not item["ok"]]
        return {
            "ok": not failures,
            "knowledge_id": knowledge_id,
            "include_parallel": include_parallel,
            "processed": results,
            "failed_count": len(failures),
        }

    # ---------------- 一轮「渠道 × query」循环 ----------------

    def _round(
        self,
        service: BookService,
        advisor,
        book,
        expectation: BookExpectation,
        queries: list[str],
        state: _RoundState,
        report: ProgressCallback,
    ) -> tuple[dict | None, bool]:
        """按 QED_SOURCES 渠道顺序执行 query 循环（硬编码轮与 LLM 变体轮共用）。

        返回 (成功 outcome, 是否找到过预筛可用候选)。渠道内命中（产出可用候选）即止，
        渠道候选耗尽换下一渠道；metadata_only 候选单独收集为人工指引，不进自动下载。
        """
        found_any = False
        for provider in service.providers:
            channel_hit = False
            for query in queries:
                if channel_hit:
                    break  # 渠道内命中即止：该渠道已有可用候选（未成功也不再跑后续 query）
                if query not in state.queries_used:
                    state.queries_used.append(query)
                try:
                    raw = provider.search(query, self.search_limit)
                except Exception as exc:  # noqa: BLE001 - 渠道级搜索失败留痕继续下一渠道
                    state.provider_failures.append((provider.name, str(exc)))
                    break
                candidates: list[Candidate] = []
                for candidate in raw:
                    key = (candidate.provider, candidate.provider_id, candidate.title.casefold())
                    if key in state.seen:
                        continue
                    state.seen.add(key)
                    if candidate.availability == Availability.METADATA_ONLY:
                        if candidate.links:
                            state.guidance.append(self._guidance(candidate))
                        continue
                    reason = _prescreen_rejection(candidate, expectation)
                    if reason:
                        state.prescreen_rejects.append(f"{candidate.provider}:{candidate.title}（{reason}）")
                        continue
                    candidates.append(candidate)
                if not candidates:
                    continue  # 该 query 无可用候选 → 渠道内下一条 query
                found_any = True
                channel_hit = True
                verdicts = self._confirm(advisor, expectation=expectation, candidates=candidates)
                destination = self._destination_dir(book)
                for index, candidate in enumerate(candidates, 1):
                    verdict = verdicts.get(candidate.provider_id)
                    if verdict is not None and not verdict.ok:
                        state.attempts.append({"provider": candidate.provider, "title": candidate.title,
                                               "ok": False, "note": verdict.note})
                        self.repo.add_source(state.book_id, channel=provider.name,
                                             provider_id=candidate.provider_id, page_url=candidate.page_url,
                                             ok=False, note=verdict.note)
                        continue
                    report(40 + int(50 * (index - 1) / max(1, len(candidates))),
                           f"下载尝试：{candidate.provider} - {candidate.title}")
                    record, failure = self._download_with_budget(
                        service, candidate, destination_dir=destination,
                    )
                    if record is None:
                        state.attempts.append({"provider": candidate.provider, "title": candidate.title,
                                               "ok": False, "note": failure})
                        self.repo.add_source(state.book_id, channel=provider.name,
                                             provider_id=candidate.provider_id, page_url=candidate.page_url,
                                             download_url=candidate.download_url, ok=False, note=failure)
                        continue
                    self.repo.add_source(state.book_id, channel=provider.name,
                                         provider_id=candidate.provider_id, page_url=candidate.page_url,
                                         download_url=candidate.download_url, ok=True, note=record.resource_id)
                    # 阶段5 登记（裁决 4 书级完成判据）：mark_owned 唯一写 holding/file_path
                    self.repo.mark_owned(state.book_id, file_path=record.file["relative_path"])
                    state.attempts.append({"provider": candidate.provider, "title": candidate.title,
                                           "ok": True, "note": record.resource_id})
                    report(95, f"下载完成：{record.file['relative_path']}")
                    return {
                        "ok": True,
                        "book_id": state.book_id,
                        "skipped": False,
                        "file_path": record.file["relative_path"],
                        "resource_id": record.resource_id,
                        "attempts": state.attempts,
                        "provider_failures": state.provider_failures,
                        "manual_guidance": state.guidance,
                    }, True
        return None, found_any

    def _confirm(self, advisor, *, expectation: BookExpectation,
                 candidates: list[Candidate]) -> dict[str, _Verdict]:
        """阶段2 LLM 确认（一批一次调用）；关闭/不可用按设计降级。"""
        if advisor is None or not self.llm_confirm:
            return {candidate.provider_id: _Verdict(True, "") for candidate in candidates}
        try:
            confirmations = advisor.confirm(expectation, candidates)
        except Exception as exc:  # noqa: BLE001 - LLM 失败按 uncertain 降级不阻塞
            note = f"LLM 确认不可用，按 uncertain 处理：{exc}"
            return {candidate.provider_id: _Verdict(False, note) for candidate in candidates}
        verdicts: dict[str, _Verdict] = {}
        for item in confirmations:
            verdicts[item.provider_id] = _Verdict(
                item.verdict == "confirmed", f"LLM {item.verdict}：{item.summary}"
            )
        return verdicts

    def _propose_variants(self, advisor, expectation: BookExpectation) -> tuple[list[str], str]:
        """书级 LLM 检索词变体兜底（一次）；失败返回空表 + 说明（转人工指引，不阻塞）。"""
        try:
            return advisor.propose_queries(expectation, variants=self.query_variants), ""
        except Exception as exc:  # noqa: BLE001 - LLM 不可用/预算耗尽 → 转人工指引
            return [], f"LLM 检索词变体不可用：{exc}"

    # ---------------- 阶段3+4：预算下载与 staging 验收 ----------------

    def _download_with_budget(self, service: BookService, candidate: Candidate, *,
                              destination_dir: Path) -> tuple[object | None, str]:
        """resolve → 预检 → 候选级预算下载 → staging 机器验收 → promote 落盘登记。

        预算覆盖 resolve→开始稳定下载；首个 chunk 写入 .part 即释放（允许跑完）。
        返回 (record, "") 或 (None, 失败原因)。
        """
        started = threading.Event()
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qed-book-fetch")
        tag = uuid.uuid4().hex[:8]

        def _work():
            resolved = service.resolve(candidate)
            if not resolved.download_url:
                raise ValueError("resolve 无直链（IA 无公开 PDF / GB 无 downloadLink）")
            if resolved.size_bytes is not None and resolved.size_bytes < self.min_size_bytes:
                raise ValueError(f"大小预检：resolve 声明 {resolved.size_bytes}B < 下限 {self.min_size_bytes}B")
            return service.resources.stage_download(resolved, staging_tag=tag, on_start=started.set)

        try:
            future = executor.submit(_work)
            try:
                staged = future.result(timeout=self.candidate_budget)
            except FuturesTimeoutError:
                if not started.is_set():
                    # 未到释放点即超时：候选失败换下一个（孤儿线程随 close 断连自灭）
                    return None, f"超时（{self.candidate_budget:g}s 内未开始稳定下载）"
                staged = future.result()  # 已开始稳定下载：预算释放，允许跑完
        except Exception as exc:  # noqa: BLE001 - resolve/预检/传输/md5 失败：候选失败留痕
            return None, str(exc)[:300]
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        # 阶段4 机器验收（staging 上，无 LLM）：未过门槛文件永不进 raw/
        result = accept_pdf(staged.path, min_pages=self.min_pages, min_size=self.min_size_bytes)
        if not result.accepted:
            staged.path.unlink(missing_ok=True)
            return None, "机器验收拒绝：" + "；".join(result.reasons) + self._soft_signal_note(result)
        record = service.resources.promote_staged(
            staged, candidate, kind=ResourceKind.BOOK,
            destination_dir=destination_dir,
        )
        return record, ""

    # ---------------- 内部 ----------------

    def _destination_dir(self, book) -> Path:
        """成品桶：refs 反查归属课程 → raw/<domain>/<course>/；反查不到 → 领域通用桶。"""
        course_id = self.repo.first_course_for_book(book.book_id)
        if course_id:
            return raw_course_dir(self.data_root, course_id)
        return raw_general_dir(self.data_root)

    @staticmethod
    def _guidance(candidate: Candidate) -> dict:
        return {
            "provider": candidate.provider,
            "title": candidate.title,
            "links": [{"label": link.label, "url": link.url, "kind": link.kind} for link in candidate.links],
        }

    @staticmethod
    def _soft_signal_note(result) -> str:
        if result.text_chars < 0:
            return "；文本层无法评估"
        if result.text_chars == 0:
            return "；无文本层（扫描版/空白页，软信号不拒绝）"
        return ""

    @staticmethod
    def _prescreen_note(state: _RoundState) -> str:
        if not state.prescreen_rejects:
            return ""
        return f"预筛失配 {len(state.prescreen_rejects)} 项：" + "；".join(state.prescreen_rejects[:5])

    @staticmethod
    def _failure_message(state: _RoundState) -> str:
        lines = [f"全部自动候选失败，已转人工处理（queries={state.queries_used}）。"]
        for note in state.notices:
            lines.append(f"- {note}")
        for attempt in state.attempts:
            lines.append(f"- [{attempt['provider']}] {attempt['title']}: {attempt['note']}")
        if state.prescreen_rejects:
            lines.append("预筛失配（未耗 LLM，未下载）：")
            lines.extend(f"- {item}" for item in state.prescreen_rejects)
        for name, error in state.provider_failures:
            lines.append(f"- 来源搜索失败 {name}: {error}")
        if state.guidance:
            lines.append("人工下载指引：")
            for item in state.guidance:
                links = ", ".join(link["url"] for link in item["links"])
                lines.append(f"- [{item['provider']}] {item['title']}: {links}")
        return "\n".join(lines)


class _RoundState:
    """单次书级 fetch 的跨轮聚合状态（attempt/留痕/去重跨硬编码轮与 LLM 变体轮共享）。"""

    def __init__(self, *, book_id: str):
        self.book_id = book_id
        self.queries_used: list[str] = []
        self.seen: set[tuple[str, str, str]] = set()
        self.attempts: list[dict] = []
        self.guidance: list[dict] = []
        self.prescreen_rejects: list[str] = []
        self.provider_failures: list[tuple[str, str]] = []
        self.notices: list[str] = []  # LLM 兜底链路说明（变体不可用等），进失败消息与留痕
