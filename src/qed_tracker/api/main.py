"""QED-Tracker FastAPI 服务（8901）。

契约（docs/design/tracker-service.md）：
- 只读查询同步返回：健康、搜索、资源、目录、任务列表；
- 写操作提交后台任务，状态 queued→running→succeeded/failed，并发上限 2；
- 同内容（sha256）幂等复用，重复提交不产生重复文件。
- QED-030：qt_resources 旧资源 API 已退役（0005 drop），资源域为五层模型语义
  （qed_domain → qed_course → qt_knowledge → qt_books → qt_sources）。
"""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from qed_tracker import __version__
from qed_tracker.api.tasks import TaskManager, TaskStore
from qed_tracker.application import BookService, ResourceService
from qed_tracker.application.papers import PaperService
from qed_tracker.catalog import list_catalogs, load_catalog
from qed_tracker.config import Settings, llm_api_key
from qed_tracker.db.knowledge_repository import InvalidTransition, KnowledgeRepository, tutorial_name
from qed_tracker.db.models import QedDomain
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
        self._exploration_repository = None
        if settings.db_configured:
            from qed_tracker.database import create_engine_for, session_factory

            if self._db_engine is None:
                self._db_engine = create_engine_for(settings)
            if self._knowledge_repository is None:
                self._knowledge_repository = KnowledgeRepository(session_factory(self._db_engine))
            from qed_tracker.db.exploration_repository import ExplorationRepository

            self._exploration_repository = ExplorationRepository(session_factory(self._db_engine))
        if advisor is None and settings.llm_configured:
            advisor = BailianBookAdvisor(
                api_key=llm_api_key(),
                model=settings.llm_model,
                base_url=settings.llm_base_url,
                timeout=settings.llm_timeout_seconds,
                call_budget=settings.llm_call_budget,
                max_tokens=settings.llm_max_tokens,
                api_select=settings.api_select,
                gateway_url=settings.llm_gateway_url,
                engine=self._db_engine,
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
    def _advisor_kwargs() -> dict[str, Any]:
        """每次 run 新建 advisor 实例的共享配置（L6 裁决：budget 隔离）。"""
        return dict(
            api_key=llm_api_key(),
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            call_budget=settings.llm_call_budget,
            max_tokens=settings.llm_max_tokens,
            api_select=settings.api_select,
            gateway_url=settings.llm_gateway_url,
            engine=app._db_engine,
        )

    def _explore_course_handler(params: dict[str, Any], progress: Any) -> dict[str, Any]:
        run_id = params.get("run_id", "")
        if app._exploration_repository is None:
            raise RuntimeError("数据库未配置：探索任务需要数据库")
        repo = app._exploration_repository
        run = repo.get_run(run_id)
        if run is None:
            return {"run_id": run_id, "status": "not_found"}
        kn_repo = app._knowledge_repository
        if kn_repo is None:
            repo.finish_failed(run_id, error={"code": "DB_UNAVAILABLE", "message": "知识库未配置"})
            return {"run_id": run_id, "status": "failed"}
        course = None
        for c in kn_repo.list_courses():
            if c.course_id == run.course_id:
                course = c
                break
        if course is None:
            repo.finish_failed(run_id, error={"code": "COURSE_NOT_FOUND", "message": f"课程不存在：{run.course_id}"})
            return {"run_id": run_id, "status": "failed"}
        if app.advisor is None:
            repo.finish_failed(run_id, error={"code": "LLM_UNAVAILABLE", "message": "LLM 未配置"})
            return {"run_id": run_id, "status": "failed"}
        from qed_tracker.providers.explore_advisor import CourseExploreAdvisor, ExploreAdvisorError

        try:
            advisor = CourseExploreAdvisor(**_advisor_kwargs())
        except Exception:
            repo.finish_failed(run_id, error={"code": "LLM_UNAVAILABLE", "message": "LLM 初始化失败"})
            return {"run_id": run_id, "status": "failed"}
        try:
            course_dict = {
                "course_id": course.course_id,
                "name": course.name,
                "aliases": list(course.aliases),
                "stage": course.stage,
                "prerequisites": list(course.prerequisites),
                "related_targets": list(course.related_targets),
                "note": course.note,
            }
            mode = run.params.get("mode", "direct")
            ref_text = run.params.get("ref_text", "")
            ref_doc_path = run.params.get("ref_doc_path", "")
            proposals = advisor.propose(course_dict, mode=mode, ref_text=ref_text, ref_doc_path=ref_doc_path)
            repo.finish_ready(run_id, proposals=proposals, meta=advisor.metadata())
            return {"run_id": run_id, "status": "ready", "proposal_count": len(proposals)}
        except ExploreAdvisorError as exc:
            repo.finish_failed(run_id, error={"code": exc.code, "message": str(exc)})
            return {"run_id": run_id, "status": "failed"}
        finally:
            advisor.close()

    def _explore_curriculum_handler(params: dict[str, Any], progress: Any) -> dict[str, Any]:
        run_id = params.get("run_id", "")
        if app._exploration_repository is None:
            raise RuntimeError("数据库未配置：探索任务需要数据库")
        repo = app._exploration_repository
        run = repo.get_run(run_id)
        if run is None:
            return {"run_id": run_id, "status": "not_found"}
        if app.advisor is None:
            repo.finish_failed(run_id, error={"code": "LLM_UNAVAILABLE", "message": "LLM 未配置"})
            return {"run_id": run_id, "status": "failed"}
        from qed_tracker.providers.explore_advisor import CurriculumExploreAdvisor, ExploreAdvisorError

        try:
            advisor = CurriculumExploreAdvisor(**_advisor_kwargs())
        except Exception:
            repo.finish_failed(run_id, error={"code": "LLM_UNAVAILABLE", "message": "LLM 初始化失败"})
            return {"run_id": run_id, "status": "failed"}
        try:
            mode = run.params.get("mode", "direct")
            ref_text = run.params.get("ref_text", "")
            ref_doc_path = run.params.get("ref_doc_path", "")
            changes = advisor.propose(run.domain_name, mode=mode, ref_text=ref_text, ref_doc_path=ref_doc_path)
            repo.finish_ready(run_id, proposals=changes, meta=advisor.metadata())
            return {"run_id": run_id, "status": "ready", "change_count": len(changes)}
        except ExploreAdvisorError as exc:
            repo.finish_failed(run_id, error={"code": exc.code, "message": str(exc)})
            return {"run_id": run_id, "status": "failed"}
        finally:
            advisor.close()

    explore_handlers = {
        "explore_course": _explore_course_handler,
        "explore_curriculum": _explore_curriculum_handler,
    }
    all_handlers = {**explore_handlers, **(extra_handlers or {})}
    manager = TaskManager(TaskStore(settings.state_dir / "tasks"), all_handlers)

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

    def _domain_view(repo: KnowledgeRepository, domain: QedDomain) -> dict[str, Any]:
        """课程体系只读透出（QED-033）：字段与 courses.py Curriculum/Course dataclass 一致，不透出审计列。"""
        return {
            "domain_id": domain.domain_id,
            "name": domain.name,
            "description": domain.description,
            "stages": list(domain.stages),
            "courses": [
                {
                    "course_id": row.course_id,
                    "name": row.name,
                    "aliases": list(row.aliases),
                    "stage": row.stage,
                    "prerequisites": list(row.prerequisites),
                    "related_targets": list(row.related_targets),
                    "note": row.note,
                }
                for row in repo.list_courses(domain.domain_id)
            ],
        }

    def api_error(status_code: int, code: str, message: str) -> HTTPException:
        return HTTPException(status_code=status_code, detail={"code": code, "message": message})

    def _explore_run_view(run) -> dict[str, Any]:
        return {
            "run_id": run.run_id,
            "scope": run.scope,
            "course_id": run.course_id,
            "domain_name": run.domain_name,
            "status": run.status,
            "params": run.params,
            "proposals": run.proposals or [],
            "adopted_proposal_ids": run.adopted_ids or [],
            "conflicts": run.conflicts,
            "error": run.error,
            "task_id": run.task_id,
            "meta": run.meta,
            "created_at": run.created_at.isoformat() if hasattr(run.created_at, "isoformat") else str(run.created_at),
            "updated_at": run.updated_at.isoformat() if hasattr(run.updated_at, "isoformat") else str(run.updated_at),
        }

    def _er():
        if app._exploration_repository is None:
            raise api_error(409, "DB_UNAVAILABLE", "数据库未配置：探索端点需 QtExploreRun 表")
        return app._exploration_repository

    @fastapi_app.get("/api/v1/courses")
    def courses() -> list[dict[str, Any]]:
        """课程体系列表（qed_domain/qed_course 共享表，按领域分组全量，sort_order 有序；无加工直接透出）。"""
        repo = _kn(app)
        return [_domain_view(repo, domain) for domain in repo.list_domains()]

    @fastapi_app.get("/api/v1/courses/{domain_id}")
    def course_detail(domain_id: str) -> dict[str, Any]:
        repo = _kn(app)
        domain = next((d for d in repo.list_domains() if d.domain_id == domain_id), None)
        if domain is None:
            raise HTTPException(status_code=404, detail=f"未知学科课程体系：{domain_id}")
        return _domain_view(repo, domain)

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
            ok=payload.get("ok") is True,
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
        from qed_tracker.downloader import inspect_pdf, safe_filename

        try:
            digest, size, pages = inspect_pdf(path)
        except Exception as exc:  # noqa: BLE001 - PDF 校验失败统一 400
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        file_name = f"{safe_filename(row.display_title or 'book')}_{digest[:8]}.pdf"
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
        if not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
            raise HTTPException(status_code=422, detail="sha256 必须为 64 位十六进制")
        page_count = payload.get("page_count")
        if page_count is not None and type(page_count) is not int:
            raise HTTPException(status_code=422, detail="page_count 必须为整数")
        repo = _kn(app)
        try:
            row = repo.complete_download(
                book_id,
                sha256=sha256,
                relative_path=relative_path,
                page_count=page_count,
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

    # ---------------- 课程探索端点（QED-040/041） ----------------

    @fastapi_app.post("/api/v1/courses/{course_id}/explore", status_code=202)
    def course_explore(course_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        mode = str(payload.get("mode", "")).strip()
        if mode not in ("direct", "text", "doc"):
            raise api_error(400, "INVALID_PARAMS", "mode 必须为 direct/text/doc")
        if mode == "text" and not str(payload.get("ref_text", "")).strip():
            raise api_error(400, "INVALID_PARAMS", "mode=text 需要非空 ref_text")
        if mode == "doc":
            ref_doc = str(payload.get("ref_doc_path", "")).strip()
            if not ref_doc:
                raise api_error(400, "INVALID_PARAMS", "mode=doc 需要非空 ref_doc_path")
            from pathlib import Path

            if not Path(ref_doc).is_file():
                raise api_error(400, "INVALID_PARAMS", f"ref_doc_path 不可读：{ref_doc}")
        kn_repo = _kn(app)
        course = None
        for c in kn_repo.list_courses():
            if c.course_id == course_id:
                course = c
                break
        if course is None:
            raise api_error(404, "COURSE_NOT_FOUND", f"课程不存在：{course_id}")
        repo = _er()
        if repo.find_running("course", course_id) is not None:
            raise api_error(409, "COURSE_EXPLORATION_IN_PROGRESS", f"课程 {course_id} 已有运行中的探索")
        run = repo.create_run(
            "course",
            params={"mode": mode, "ref_text": payload.get("ref_text", ""), "ref_doc_path": payload.get("ref_doc_path", "")},
            course_id=course_id,
        )
        record = manager.submit("explore_course", {"run_id": run.run_id})
        repo.attach_task(run.run_id, record.task_id)
        return {"run_id": run.run_id, "task_id": record.task_id, "status": "running"}

    @fastapi_app.get("/api/v1/explore-runs/{run_id}")
    def explore_run_detail(run_id: str) -> dict[str, Any]:
        repo = _er()
        run = repo.get_run(run_id)
        if run is None:
            raise api_error(404, "RUN_NOT_FOUND", f"探索运行不存在：{run_id}")
        if run.status == "running" and run.task_id:
            task = manager.get(run.task_id)
            if task is None:
                run = repo.finish_failed(run_id, error={"code": "TASK_LOST", "message": "关联任务不存在"})
            elif task.status == "failed":
                run = repo.finish_failed(run_id, error={"code": "TASK_FAILED", "message": "关联任务已失败"})
        return _explore_run_view(run)

    @fastapi_app.post("/api/v1/explore-runs/{run_id}/adopt")
    def explore_run_adopt(run_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        repo = _er()
        run = repo.get_run(run_id)
        if run is None:
            raise api_error(404, "RUN_NOT_FOUND", f"探索运行不存在：{run_id}")
        if run.status != "ready":
            raise api_error(409, "RUN_STATE_CONFLICT", f"运行状态 {run.status} 不允许采纳（需 ready）")
        selected = payload.get("selected", [])
        proposals = run.proposals or []
        proposal_ids = {p.get("id") or p.get("proposal_id") or p.get("set_no") for p in proposals}
        for sid in selected:
            if sid not in proposal_ids:
                raise api_error(400, "INVALID_PARAMS", f"proposal {sid} 不存在于推荐列表")
        kn_repo = _kn(app)
        tutorial_count = len([
            k for k in kn_repo.list_knowledge(course_id=run.course_id, kind="tutorial")
            if k.status in ("draft", "confirmed", "completed")
        ])
        remaining = 4 - tutorial_count
        if len(selected) > remaining:
            raise api_error(409, "CAPACITY_REACHED", f"课程最多 4 套教程，已 {tutorial_count}，本次最多 {remaining}")
        # 从课程行获取 domain_id（不依赖 course_id 字符串解析）
        course_row = None
        for c in kn_repo.list_courses():
            if c.course_id == run.course_id:
                course_row = c
                break
        domain_id = course_row.domain_id if course_row else "math"
        adopted = []
        for sid in selected:
            proposal = next((p for p in proposals if p.get("proposal_id") == sid), None)
            if proposal is None:
                raise api_error(400, "INVALID_PARAMS", f"未知 proposal_id：{sid}")
            title = proposal.get("textbook", {}).get("title", "") if proposal else ""
            authors = proposal.get("textbook", {}).get("authors", []) if proposal else []
            set_no = proposal.get("set_no", "") if proposal else ""
            try:
                kn = kn_repo.create_knowledge(
                    domain_id=domain_id,
                    course_id=run.course_id,
                    kind="tutorial",
                    set_no=set_no,
                    name=tutorial_name(set_no, title, authors),
                )
            except Exception as exc:
                raise api_error(500, "KNOWLEDGE_CREATE_FAILED", f"创建知识行失败：{exc}") from exc
            adopted.append({"knowledge_id": kn.knowledge_id, "set_name": proposal.get("set_name", "")})
        updated_run = repo.adopt_run(run_id, adopted_ids=[a["knowledge_id"] for a in adopted])
        return {
            "adopted": adopted,
            "remaining_slots": remaining - len(selected),
            "run": _explore_run_view(updated_run),
        }

    @fastapi_app.post("/api/v1/explore-runs/{run_id}/discard")
    def explore_run_discard(run_id: str) -> dict[str, Any]:
        repo = _er()
        run = repo.get_run(run_id)
        if run is None:
            raise api_error(404, "RUN_NOT_FOUND", f"探索运行不存在：{run_id}")
        if run.status not in ("ready", "discarded"):
            raise api_error(409, "RUN_STATE_CONFLICT", f"运行状态 {run.status} 不允许放弃（需 ready/discarded）")
        updated = repo.discard_run(run_id)
        return _explore_run_view(updated)

    @fastapi_app.get("/api/v1/courses/{course_id}/explore-runs")
    def course_explore_runs(
        course_id: str,
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ) -> list[dict[str, Any]]:
        repo = _er()
        runs = repo.list_runs("course", course_id, limit=limit, offset=offset)
        return [
            {
                "run_id": r.run_id,
                "status": r.status,
                "proposal_count": len(r.proposals or []),
                "adopted_count": len(r.adopted_ids or []),
                "created_at": r.created_at.isoformat() if hasattr(r.created_at, "isoformat") else str(r.created_at),
                "updated_at": r.updated_at.isoformat() if hasattr(r.updated_at, "isoformat") else str(r.updated_at),
            }
            for r in runs
        ]

    # ---------------- 领域探索端点（QED-041） ----------------

    @fastapi_app.post("/api/v1/curriculum-explore", status_code=202)
    def curriculum_explore(payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        domain_name = str(payload.get("domain_name", "")).strip()
        if not domain_name or len(domain_name) > 100:
            raise api_error(400, "INVALID_PARAMS", "domain_name 非空且长度 ≤100")
        mode = str(payload.get("mode", "")).strip()
        if mode not in ("direct", "text", "doc"):
            raise api_error(400, "INVALID_PARAMS", "mode 必须为 direct/text/doc")
        if mode == "text" and not str(payload.get("ref_text", "")).strip():
            raise api_error(400, "INVALID_PARAMS", "mode=text 需要非空 ref_text")
        if mode == "doc":
            ref_doc = str(payload.get("ref_doc_path", "")).strip()
            if not ref_doc:
                raise api_error(400, "INVALID_PARAMS", "mode=doc 需要非空 ref_doc_path")
            from pathlib import Path

            if not Path(ref_doc).is_file():
                raise api_error(400, "INVALID_PARAMS", f"ref_doc_path 不可读：{ref_doc}")
        repo = _er()
        if repo.find_running("curriculum", domain_name) is not None:
            raise api_error(409, "CURRICULUM_EXPLORATION_IN_PROGRESS", f"领域 {domain_name} 已有运行中的探索")
        run = repo.create_run(
            "curriculum",
            domain_name=domain_name,
            params={"mode": mode, "ref_text": payload.get("ref_text", ""), "ref_doc_path": payload.get("ref_doc_path", "")},
        )
        record = manager.submit("explore_curriculum", {"run_id": run.run_id})
        repo.attach_task(run.run_id, record.task_id)
        return {"run_id": run.run_id, "task_id": record.task_id, "status": "running"}

    @fastapi_app.get("/api/v1/curriculum-runs/{run_id}")
    def curriculum_run_detail(run_id: str) -> dict[str, Any]:
        repo = _er()
        run = repo.get_run(run_id)
        if run is None:
            raise api_error(404, "RUN_NOT_FOUND", f"探索运行不存在：{run_id}")
        if run.status == "running" and run.task_id:
            task = manager.get(run.task_id)
            if task is None:
                run = repo.finish_failed(run_id, error={"code": "TASK_LOST", "message": "关联任务不存在"})
            elif task.status == "failed":
                run = repo.finish_failed(run_id, error={"code": "TASK_FAILED", "message": "关联任务已失败"})
        return _explore_run_view(run)

    @fastapi_app.post("/api/v1/curriculum-runs/{run_id}/apply")
    def curriculum_run_apply(run_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        repo = _er()
        run = repo.get_run(run_id)
        if run is None:
            raise api_error(404, "RUN_NOT_FOUND", f"探索运行不存在：{run_id}")
        if run.status != "ready":
            raise api_error(409, "RUN_STATE_CONFLICT", f"运行状态 {run.status} 不允许应用（需 ready）")
        selected = payload.get("selected", [])
        proposals = run.proposals or []
        change_ids = {p.get("change_id") for p in proposals}
        for sid in selected:
            if sid not in change_ids:
                raise api_error(400, "INVALID_PARAMS", f"change_id {sid} 不存在于推荐列表")
        kn_repo = _kn(app)
        applied: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        applied_domain_id: str = ""
        for sid in selected:
            proposal = next((p for p in proposals if p.get("change_id") == sid), None)
            action = proposal.get("action", "")
            entity = proposal.get("entity", "")
            target_id = proposal.get("target_id", "")
            payload_data = proposal.get("payload", {})
            if action == "create_domain" and entity == "domain":
                # 幂等创建：已存在视为冲突
                existing_domain = None
                for d in kn_repo.list_domains():
                    if d.domain_id == target_id:
                        existing_domain = d
                        break
                if existing_domain is not None:
                    conflicts.append({"change_id": sid, "reason": f"领域 id 已存在：{target_id}"})
                    continue
                kn_repo.create_domain(
                    domain_id=target_id,
                    name=payload_data.get("name", ""),
                    description=payload_data.get("description", ""),
                    stages=payload_data.get("stages", []),
                )
                applied.append({"change_id": sid, "entity": "domain", "target_id": target_id})
                applied_domain_id = target_id
            elif action == "create_course" and entity == "course":
                # 幂等创建：已存在视为冲突
                existing_course = None
                for c in kn_repo.list_courses():
                    if c.course_id == target_id:
                        existing_course = c
                        break
                if existing_course is not None:
                    conflicts.append({"change_id": sid, "reason": f"课程 id 已存在：{target_id}"})
                    continue
                kn_repo.create_course(
                    course_id=target_id,
                    domain_id=applied_domain_id,
                    name=payload_data.get("name", ""),
                    stage=payload_data.get("stage", ""),
                    sort_order=payload_data.get("sort_order", 0),
                    prerequisites=payload_data.get("prerequisites", []),
                    aliases=payload_data.get("aliases", []),
                    note=payload_data.get("note", ""),
                )
                applied.append({"change_id": sid, "entity": "course", "target_id": target_id})
            else:
                conflicts.append({"change_id": sid, "reason": f"不支持的操作：{action} {entity}"})
        updated_run = repo.apply_run(run_id, applied_ids=[a["change_id"] for a in applied], conflicts=conflicts)
        return {
            "applied": applied,
            "conflicts": conflicts,
            "run": _explore_run_view(updated_run),
        }

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
