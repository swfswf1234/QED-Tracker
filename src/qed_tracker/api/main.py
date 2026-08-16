"""QED-Tracker FastAPI 服务（8901）。

契约（docs/design/tracker-service.md）：
- 只读查询同步返回：健康、搜索、资源、目录、任务列表；
- 写操作提交后台任务，状态 queued→running→succeeded/failed，并发上限 2；
- 同内容（sha256）幂等复用，重复提交不产生重复文件。
- QED-030：qt_resources 旧资源 API 已退役（0005 drop），资源域为五层模型语义
  （qed_domain → qed_course → qt_knowledge → qt_books → qt_sources）。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from qed_tracker import __version__
from qed_tracker.api.tasks import TaskManager, TaskStore
from qed_tracker.application import BookService, ResourceService
from qed_tracker.application.papers import PaperService
from qed_tracker.catalog import list_catalogs, load_catalog
from qed_tracker.config import Settings, llm_api_key
from qed_tracker.db.knowledge_repository import InvalidTransition, KnowledgeRepository
from qed_tracker.downloader import DownloadManager
from qed_tracker.inventory import Inventory
from qed_tracker.models import Candidate
from qed_tracker.providers import ArxivProvider, create_book_providers
from qed_tracker.providers.book_advisor import BailianBookAdvisor

FRONTEND_ORIGINS = ("http://127.0.0.1:8903", "http://localhost:8903")

# B008：函数调用不得出现在参数默认值中，FastAPI 允许模块级单例。
_EMPTY_BODY: dict[str, Any] = Body(default_factory=dict)


class Application:
    """共享的服务容器：任务执行与只读端点复用同一批资源服务。"""

    def __init__(
        self,
        settings: Settings,
        *,
        book_providers=None,
        papers_provider=None,
        downloader=None,
        advisor=None,
        knowledge_repository=None,
    ):
        self.settings = settings
        inventory = Inventory(settings.data_root)
        downloader = downloader or DownloadManager(
            proxy=settings.proxy,
            timeout=settings.timeout_seconds,
            retries=settings.retries,
            tls_verify=settings.tls_verify,
        )
        self.resources = ResourceService(inventory, downloader)
        providers = (
            book_providers
            if book_providers is not None
            else create_book_providers(
                settings.sources, proxy=settings.proxy, timeout=settings.timeout_seconds, tls_verify=settings.tls_verify
            )
        )
        self.books = BookService(providers, self.resources)
        self.papers = PaperService(papers_provider or ArxivProvider(retries=settings.retries), self.resources)
        self._db_engine = None
        self._knowledge_repository = knowledge_repository
        if knowledge_repository is None and settings.db_configured:
            from qed_tracker.database import create_engine_for, session_factory

            self._db_engine = create_engine_for(settings)
            self._knowledge_repository = KnowledgeRepository(session_factory(self._db_engine))
        if advisor is None and settings.llm_configured:
            advisor = BailianBookAdvisor(
                api_key=llm_api_key(),
                model=settings.llm_model,
                base_url=settings.llm_base_url,
                timeout=settings.llm_timeout_seconds,
                call_budget=settings.llm_call_budget,
                max_tokens=settings.llm_max_tokens,
            )
        self.advisor = advisor

    def close(self) -> None:
        self.books.close()
        self.papers.close()
        if self.advisor is not None:
            self.advisor.close()
        if self._db_engine is not None:
            self._db_engine.dispose()


def _candidate_dict(candidate: Candidate) -> dict[str, Any]:
    value = asdict(candidate)
    value["availability"] = candidate.availability.value
    value["authors"] = list(candidate.authors)
    value["subjects"] = list(candidate.subjects)
    return value


def create_app(
    settings: Settings,
    *,
    book_providers=None,
    papers_provider=None,
    downloader=None,
    extra_handlers: dict[str, Any] | None = None,
    advisor=None,
    knowledge_repository: KnowledgeRepository | None = None,
) -> FastAPI:
    app = Application(
        settings,
        book_providers=book_providers,
        papers_provider=papers_provider,
        downloader=downloader,
        advisor=advisor,
        knowledge_repository=knowledge_repository,
    )
    manager = TaskManager(TaskStore(settings.state_dir / "tasks"), dict(extra_handlers or {}))

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        manager.shutdown(wait=True)
        app.close()

    fastapi_app = FastAPI(title="QED-Tracker", version=__version__, lifespan=lifespan)
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=list(FRONTEND_ORIGINS),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @fastapi_app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @fastapi_app.get("/api/v1/books/search")
    def books_search(
        q: str = Query(..., min_length=1),
        limit: int = Query(10, ge=1, le=50),
        source: str = "",
    ) -> list[dict[str, Any]]:
        items = app.books.search(q, limit=limit)
        candidates = [item.candidate for item in items if not source or item.candidate.provider == source]
        return [_candidate_dict(item) for item in candidates]

    @fastapi_app.get("/api/v1/papers/search")
    def papers_search(
        q: str = "",
        category: str = "",
        author: str = "",
        limit: int = Query(10, ge=1, le=50),
    ) -> list[dict[str, Any]]:
        candidates = app.papers.search(q, category=category, author=author, limit=limit)
        return [_candidate_dict(item) for item in candidates]

    @fastapi_app.get("/api/v1/catalogs")
    def catalogs() -> list[dict[str, str]]:
        return [{"id": catalog_id} for catalog_id in list_catalogs()]

    @fastapi_app.get("/api/v1/catalogs/{catalog_id}")
    def catalog_detail(catalog_id: str) -> dict[str, Any]:
        try:
            catalog = load_catalog(catalog_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "id": catalog.id,
            "name": catalog.name,
            "description": catalog.description,
            "status": catalog.status,
            "targets": [asdict(target) for target in catalog.targets],
        }

    # ---------------- 五层端点（QED-031：qt_knowledge / qt_books / qt_sources） ----------------
    # 契约：docs/design/database-schema.md。彻底隐藏语义在数据层实现（rejected/superseded/failed 默认过滤）。

    def _kn(app: Application) -> KnowledgeRepository:
        if app._knowledge_repository is None:
            raise HTTPException(status_code=409, detail="数据库未配置：五层端点需 qed_course/qt_knowledge 行")
        return app._knowledge_repository

    def _knowledge_view(repo: KnowledgeRepository, row) -> dict[str, Any]:
        value = row.to_dict()
        value["books"] = [b.to_dict() for b in repo.list_books(row.knowledge_id)]
        return value

    def _require_knowledge(repo: KnowledgeRepository, knowledge_id: str):
        row = repo.get_knowledge(knowledge_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"知识行不存在：{knowledge_id}")
        return row

    def _book_transition(book_id: str, op) -> dict[str, Any]:
        repo = _kn(app)
        try:
            row = op(repo, book_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return row.to_dict()

    @fastapi_app.get("/api/v1/knowledge")
    def knowledge_list(course_id: str = "", status: str = "") -> list[dict[str, Any]]:
        return [row.to_dict() for row in _kn(app).list_knowledge(course_id=course_id or None, status=status or None)]

    @fastapi_app.get("/api/v1/knowledge/{knowledge_id}")
    def knowledge_detail(knowledge_id: str) -> dict[str, Any]:
        repo = _kn(app)
        _require_knowledge(repo, knowledge_id)
        return _knowledge_view(repo, repo.get_knowledge(knowledge_id))

    @fastapi_app.post("/api/v1/knowledge/{knowledge_id}/confirm")
    def knowledge_confirm(knowledge_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        repo = _kn(app)
        try:
            row = repo.confirm_knowledge(
                knowledge_id,
                textbook_ref=payload.get("textbook_ref"),
                exercise_ref=payload.get("exercise_ref"),
                textbook_intro=str(payload.get("textbook_intro", "")),
                exercise_intro=str(payload.get("exercise_intro", "")),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return row.to_dict()

    @fastapi_app.post("/api/v1/knowledge/{knowledge_id}/complete")
    def knowledge_complete(knowledge_id: str) -> dict[str, Any]:
        repo = _kn(app)
        try:
            row = repo.complete_knowledge(knowledge_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return row.to_dict()

    @fastapi_app.post("/api/v1/knowledge/{knowledge_id}/reject")
    def knowledge_reject(knowledge_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        reason = str(payload.get("reason", "")).strip()
        if not reason:
            raise HTTPException(status_code=422, detail="拒绝必须提供原因（reason）")
        repo = _kn(app)
        try:
            row = repo.reject_knowledge(knowledge_id, reason=reason, by="web")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return row.to_dict()

    @fastapi_app.post("/api/v1/knowledge/{knowledge_id}/supersede")
    def knowledge_supersede(knowledge_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        reason = str(payload.get("reason", "")).strip()
        if not reason:
            raise HTTPException(status_code=422, detail="过时必须提供原因（reason）")
        repo = _kn(app)
        try:
            row = repo.supersede_knowledge(knowledge_id, reason=reason, by="web")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return row.to_dict()

    @fastapi_app.post("/api/v1/books")
    def create_book(payload: dict[str, Any]) -> dict[str, Any]:
        """新建书行候选（先登记再下载）：candidate 态。"""
        knowledge_id = str(payload.get("knowledge_id", "")).strip()
        if not knowledge_id:
            raise HTTPException(status_code=422, detail="必须提供 knowledge_id")
        title = str(payload.get("title", "")).strip()
        if not title:
            raise HTTPException(status_code=422, detail="必须提供 title")
        repo = _kn(app)
        _require_knowledge(repo, knowledge_id)
        row = repo.create_book(
            knowledge_id,
            kind=str(payload.get("kind", "textbook")),
            roles=payload.get("roles") or [],
            title=title,
            part=str(payload.get("part", "")),
            display_title=str(payload.get("display_title", "")),
            authors=payload.get("authors", []),
            language=str(payload.get("language", "")),
            version=payload.get("version"),
            source=payload.get("source"),
            original_url=str(payload.get("original_url", "")),
        )
        return row.to_dict()

    @fastapi_app.get("/api/v1/books/{book_id}/sources")
    def book_sources(book_id: str) -> list[dict[str, Any]]:
        repo = _kn(app)
        if repo.get_book(book_id, include_hidden=True) is None:
            raise HTTPException(status_code=404, detail=f"书行不存在：{book_id}")
        return [s.to_dict() for s in repo.list_sources(book_id)]

    @fastapi_app.post("/api/v1/books/{book_id}/sources")
    def book_add_source(book_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        repo = _kn(app)
        if repo.get_book(book_id, include_hidden=True) is None:
            raise HTTPException(status_code=404, detail=f"书行不存在：{book_id}")
        row = repo.add_source(
            book_id,
            channel=str(payload.get("channel", "manual")),
            provider_id=str(payload.get("provider_id", "")),
            page_url=str(payload.get("page_url", "")),
            download_url=str(payload.get("download_url", "")),
            file_keywords=str(payload.get("file_keywords", "")),
            ok=bool(payload.get("ok", False)),
            note=str(payload.get("note", "")),
        )
        return row.to_dict()

    @fastapi_app.post("/api/v1/books/{book_id}/register")
    def book_register(book_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        """人工下载登记（candidate → downloaded 直转）：relative_path 必须存在且为 PDF。"""
        repo = _kn(app)
        row = repo.get_book(book_id, include_hidden=True)
        if row is None:
            raise HTTPException(status_code=404, detail=f"书行不存在：{book_id}")
        relative = str(payload.get("relative_path", "")).strip()
        if not relative:
            raise HTTPException(status_code=422, detail="必须提供数据根内相对路径（relative_path）")
        path = (app.resources.inventory.data_root / relative).resolve()
        try:
            path.relative_to(app.resources.inventory.data_root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="路径必须在数据根目录内") from exc
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"文件不存在：{relative}")
        from qed_tracker.downloader import inspect_pdf

        try:
            digest, size, pages = inspect_pdf(path)
        except Exception as exc:  # noqa: BLE001 - PDF 校验失败统一 400
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        file_name = f"{row.display_title and Path(row.display_title).stem or 'book'}_{digest[:8]}.pdf"
        try:
            final = repo.complete_download(
                book_id,
                sha256=digest,
                relative_path=relative,
                page_count=pages,
                absolute_path=str(path),
                file_name=file_name,
            )
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return final.to_dict()

    @fastapi_app.post("/api/v1/books/{book_id}/decide")
    def book_decide(book_id: str) -> dict[str, Any]:
        return _book_transition(book_id, lambda repo, bid: repo.decide_book(bid))

    @fastapi_app.post("/api/v1/books/{book_id}/start")
    def book_start(book_id: str) -> dict[str, Any]:
        return _book_transition(book_id, lambda repo, bid: repo.start_download(bid))

    @fastapi_app.post("/api/v1/books/{book_id}/fail")
    def book_fail(book_id: str) -> dict[str, Any]:
        return _book_transition(book_id, lambda repo, bid: repo.fail_download(bid))

    @fastapi_app.post("/api/v1/books/{book_id}/retry")
    def book_retry(book_id: str) -> dict[str, Any]:
        return _book_transition(book_id, lambda repo, bid: repo.retry_download(bid))

    @fastapi_app.post("/api/v1/books/{book_id}/complete")
    def book_complete(book_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        sha256 = str(payload.get("sha256", "")).strip()
        relative_path = str(payload.get("relative_path", "")).strip()
        if not sha256 or not relative_path:
            raise HTTPException(status_code=422, detail="sha256 与 relative_path 必填")
        repo = _kn(app)
        try:
            row = repo.complete_download(
                book_id,
                sha256=sha256,
                relative_path=relative_path,
                page_count=payload.get("page_count"),
                absolute_path=str(payload.get("absolute_path", "")),
                file_name=str(payload.get("file_name", "")),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return row.to_dict()

    @fastapi_app.post("/api/v1/books/{book_id}/verify")
    def book_verify(book_id: str) -> dict[str, Any]:
        return _book_transition(book_id, lambda repo, bid: repo.verify_book(bid))

    @fastapi_app.post("/api/v1/books/{book_id}/reject")
    def book_reject(book_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        reason = str(payload.get("reason", "")).strip()
        if not reason:
            raise HTTPException(status_code=422, detail="拒绝必须提供原因（reason）")
        repo = _kn(app)
        try:
            row = repo.reject_book(book_id, reason=reason, by="web",
                                   note=str(payload.get("note", "")))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return row.to_dict()

    @fastapi_app.post("/api/v1/books/{book_id}/supersede")
    def book_supersede(book_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        reason = str(payload.get("reason", "")).strip()
        if not reason:
            raise HTTPException(status_code=422, detail="过时必须提供原因（reason）")
        repo = _kn(app)
        try:
            row = repo.supersede_book(book_id, reason=reason, by="web")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return row.to_dict()

    @fastapi_app.get("/api/v1/tasks")
    def tasks() -> list[dict[str, Any]]:
        return [record.to_dict() for record in manager.list()]

    @fastapi_app.get("/api/v1/tasks/{task_id}")
    def task_detail(task_id: str) -> dict[str, Any]:
        record = manager.get(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return record.to_dict()

    @fastapi_app.post("/api/v1/tasks/{task_type}", status_code=202)
    def submit_task(task_type: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, str]:
        try:
            record = manager.submit(task_type, payload)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"task_id": record.task_id}

    return fastapi_app
