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
from qed_tracker.db.knowledge_repository import (
    AdoptionConflict,
    CourseHasKnowledge,
    DomainNotEmpty,
    InvalidTransition,
    KnowledgeRepository,
)
from qed_tracker.db.models import QedDomain
from qed_tracker.downloader import DownloadManager
from qed_tracker.inventory import Inventory
from qed_tracker.models import Candidate
from qed_tracker.prompt_lab.pipeline import (
    CoursePipeline,
    DomainPipeline,
    NameConfirmationRequired,
    PipelineError,
)
from qed_tracker.prompt_lab.templates import DEFAULT_SCOPE
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
        # 会话工厂来源：优先复用注入 repo 的工厂（测试 SQLite 路径），
        # 否则凭据齐备时自建 MySQL engine——两表域操作必须共享同一事务边界。
        factory = knowledge_repository.session_factory if knowledge_repository is not None else None
        if factory is None and settings.db_configured:
            from qed_tracker.database import create_engine_for, session_factory

            self._db_engine = create_engine_for(settings)
            factory = session_factory(self._db_engine)
            self._knowledge_repository = KnowledgeRepository(factory)
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

    all_handlers = {**(extra_handlers or {})}
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
            "level": domain.level,
            "classic_tracks": domain.classic_tracks or [],
            "exploration_stage": domain.exploration_stage,
            "path_results": domain.path_results,
            "stages": list(domain.stages),
            "courses": [
                {
                    "course_id": row.course_id,
                    "name": row.name,
                    "aliases": list(row.aliases),
                    "track": row.track,
                    "stage": row.stage,
                    "prerequisites": list(row.prerequisites),
                    "related_targets": list(row.related_targets),
                    "description": row.description,
                    "exploration_stage": row.exploration_stage,
                }
                for row in repo.list_courses(domain.domain_id)
            ],
        }

    def api_error(status_code: int, code: str, message: str) -> HTTPException:
        return HTTPException(status_code=status_code, detail={"code": code, "message": message})

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

    # ---------------- REQ-059: 领域管理五端点 ----------------

    def _domain_view_flat(domain: QedDomain) -> dict[str, Any]:
        return {
            "domain_id": domain.domain_id,
            "name": domain.name,
            "description": domain.description,
            "stages": domain.stages or [],
            "level": domain.level,
            "scope": domain.scope,
            "classic_tracks": domain.classic_tracks or [],
            "path_results": domain.path_results,
            "exploration_stage": domain.exploration_stage,
        }

    @fastapi_app.get("/api/v1/domains")
    def list_domains() -> list[dict[str, Any]]:
        repo = _kn(app)
        return [_domain_view_flat(d) for d in repo.list_domains()]

    @fastapi_app.patch("/api/v1/domains/{domain_id}")
    def patch_domain(domain_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        repo = _kn(app)
        try:
            row = repo.update_domain(
                domain_id,
                description=payload.get("description"),
                stages=payload.get("stages"),
                level=payload.get("level"),
                scope=payload.get("scope"),
                classic_tracks=payload.get("classic_tracks"),
                path_results=payload.get("path_results"),
                exploration_stage=payload.get("exploration_stage"),
            )
        except KeyError:
            raise api_error(404, "DOMAIN_NOT_FOUND", f"领域不存在：{domain_id}") from None
        return _domain_view_flat(row)

    def _gen_domain_id(name: str) -> str:
        """服务端 domain_id 生成：slug 直用，否则 d_<md5[:10]>。"""
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        if _SLUG_RE.match(slug):
            return slug
        import hashlib as _hl
        return f"d_{_hl.md5(name.encode()).hexdigest()[:10]}"

    def _gen_course_id(domain_id: str, name: str) -> str:
        import hashlib as _hl
        return f"c_{_hl.md5(f'{domain_id}:{name}'.encode()).hexdigest()[:10]}"

    _SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")

    @fastapi_app.post("/api/v1/domains", status_code=201)
    def create_domain(payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        if not name:
            raise api_error(422, "INVALID_PARAMS", "name 不能为空")
        repo = _kn(app)
        # name 唯一性检查
        for d in repo.list_domains():
            if d.name == name:
                raise api_error(409, "DOMAIN_NAME_CONFLICT", f"领域名已存在：{name}")
        # 可选 id 指定（范本导入/目录对齐场景）；缺省服务端生成
        domain_id = str(payload.get("domain_id", "")).strip()
        if domain_id:
            if not _SLUG_RE.match(domain_id):
                raise api_error(422, "INVALID_PARAMS", f"domain_id 非法（需匹配 {_SLUG_RE.pattern}）：{domain_id}")
            if repo.get_domain(domain_id) is not None:
                raise api_error(409, "DOMAIN_NAME_CONFLICT", f"domain_id 已存在：{domain_id}")
        else:
            domain_id = _gen_domain_id(name)
        row = repo.create_domain(
            domain_id=domain_id,
            name=name,
            description=payload.get("description", ""),
            stages=payload.get("stages", []),
            level=payload.get("level", ""),
            scope=payload.get("scope", ""),
            classic_tracks=payload.get("classic_tracks", []),
        )
        return _domain_view_flat(row)

    @fastapi_app.post("/api/v1/domains/{domain_id}/courses", status_code=201)
    def create_course(domain_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        if not name:
            raise api_error(422, "INVALID_PARAMS", "name 不能为空")
        repo = _kn(app)
        domain = next((d for d in repo.list_domains() if d.domain_id == domain_id), None)
        if domain is None:
            raise api_error(404, "DOMAIN_NOT_FOUND", f"领域不存在：{domain_id}")
        # 可选 id 指定（范本导入/目录对齐场景）；缺省服务端生成
        course_id = str(payload.get("course_id", "")).strip()
        if course_id:
            if not _SLUG_RE.match(course_id):
                raise api_error(422, "INVALID_PARAMS", f"course_id 非法（需匹配 {_SLUG_RE.pattern}）：{course_id}")
            if repo.get_course(course_id) is not None:
                raise api_error(409, "COURSE_ALREADY_EXISTS", f"course_id 已存在：{course_id}")
        else:
            course_id = _gen_course_id(domain_id, name)
        row = repo.create_course(
            course_id=course_id,
            domain_id=domain_id,
            name=name,
            stage=payload.get("stage", ""),
            sort_order=payload.get("sort_order", 0),
            description=payload.get("description", ""),
            aliases=payload.get("aliases"),
            track=payload.get("track", ""),
            prerequisites=payload.get("prerequisites"),
        )
        return row.to_dict()

    @fastapi_app.patch("/api/v1/courses/{course_id}")
    def patch_course(course_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        repo = _kn(app)
        try:
            row = repo.update_course(
                course_id,
                stage=payload.get("stage"),
                sort_order=payload.get("sort_order"),
                description=payload.get("description"),
                aliases=payload.get("aliases"),
                track=payload.get("track"),
                prerequisites=payload.get("prerequisites"),
            )
        except KeyError:
            raise api_error(404, "COURSE_NOT_FOUND", f"课程不存在：{course_id}") from None
        return row.to_dict()

    @fastapi_app.delete("/api/v1/courses/{course_id}")
    def delete_course(course_id: str) -> dict[str, str]:
        repo = _kn(app)
        try:
            repo.delete_course(course_id)
        except KeyError:
            raise api_error(404, "COURSE_NOT_FOUND", f"课程不存在：{course_id}") from None
        except CourseHasKnowledge as exc:
            raise api_error(409, "COURSE_HAS_KNOWLEDGE", str(exc)) from None
        return {"ok": "true"}

    @fastapi_app.delete("/api/v1/domains/{domain_id}")
    def delete_domain(domain_id: str) -> dict[str, str]:
        repo = _kn(app)
        try:
            repo.delete_domain(domain_id)
        except KeyError:
            raise api_error(404, "DOMAIN_NOT_FOUND", f"领域不存在：{domain_id}") from None
        except DomainNotEmpty as exc:
            raise api_error(409, "DOMAIN_NOT_EMPTY", str(exc)) from None
        return {"ok": "true"}

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

    @fastapi_app.get("/api/v1/tasks")
    def tasks() -> list[dict[str, Any]]:
        return [record.to_dict() for record in manager.list()]

    # ---------------- prompt 优化 dry-run 端点（QED-043 评估模式） ----------------
    # 同步执行领域探索管线，不入任务队列；唯一痕迹是 qed_llm_calls 的 LLM 日志。

    @fastapi_app.post("/api/v1/prompt-explores/dry-run")
    def prompt_explore_dry_run(payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        domain_name = str(payload.get("domain_name", "")).strip()
        if not domain_name or len(domain_name) > 100:
            raise api_error(400, "INVALID_PARAMS", "domain_name 非空且长度 ≤100")
        mode = str(payload.get("mode", "")).strip() or "direct"
        if mode not in ("direct", "text", "doc"):
            raise api_error(400, "INVALID_PARAMS", "mode 必须为 direct/text/doc")
        if settings.api_select != "qed-engine" and not llm_api_key():
            raise api_error(409, "LLM_UNAVAILABLE", "未配置 API_KEY：dry-run 需要 LLM（可在 .env 提供）")
        scope_hint = str(payload.get("scope_hint", "")).strip() or DEFAULT_SCOPE
        try:
            pipeline = DomainPipeline(**_advisor_kwargs())
        except Exception as exc:  # noqa: BLE001 - 初始化失败统一映射
            raise api_error(409, "LLM_UNAVAILABLE", f"管线初始化失败：{exc}") from exc
        try:
            report = pipeline.explore(
                domain_name,
                scope_hint=scope_hint,
                mode=mode,
                ref_text=str(payload.get("ref_text", "")),
                ref_doc_path=str(payload.get("ref_doc_path", "")),
                confirm_name_override=str(payload.get("confirm_name_override", "")).strip(),
            )
        except NameConfirmationRequired as exc:
            # P12 阶段一：评估期直接返回标记，人工确认后以规范名重新发起
            return {"dry_run": True, "confirmation_required": True, "name_check": exc.name_check}
        except PipelineError as exc:
            status_code = 400 if exc.code == "INVALID_PARAMS" else 502
            raise api_error(status_code, exc.code, str(exc)) from exc
        finally:
            pipeline.close()
        return {"dry_run": True, "confirmation_required": False, "report": report, "calls": list(pipeline.step_calls)}

    @fastapi_app.post("/api/v1/courses/{course_id}/prompt-explores/dry-run")
    def course_prompt_explore_dry_run(
        course_id: str, payload: dict[str, Any] = _EMPTY_BODY
    ) -> dict[str, Any]:
        """课程教材探索 dry-run（QED-047，A1）：同步单步 tutorials@v1，不写任何表。"""
        mode = str(payload.get("mode", "")).strip() or "direct"
        if mode not in ("direct", "text", "doc"):
            raise api_error(400, "INVALID_PARAMS", "mode 必须为 direct/text/doc")
        if settings.api_select != "qed-engine" and not llm_api_key():
            raise api_error(409, "LLM_UNAVAILABLE", "未配置 API_KEY：dry-run 需要 LLM（可在 .env 提供）")
        repo = _kn(app)
        course_row = repo.get_course(course_id)
        if course_row is None:
            raise api_error(404, "COURSE_NOT_FOUND", f"课程不存在：{course_id}")
        try:
            pipeline = CoursePipeline(**_advisor_kwargs())
        except Exception as exc:  # noqa: BLE001 - 初始化失败统一映射
            raise api_error(409, "LLM_UNAVAILABLE", f"管线初始化失败：{exc}") from exc
        try:
            report = pipeline.explore(
                course_row.to_dict(),
                mode=mode,
                ref_text=str(payload.get("ref_text", "")),
                ref_doc_path=str(payload.get("ref_doc_path", "")),
            )
        except PipelineError as exc:
            status_code = 400 if exc.code == "INVALID_PARAMS" else 502
            raise api_error(status_code, exc.code, str(exc)) from exc
        finally:
            pipeline.close()
        return {"dry_run": True, "report": report, "calls": list(pipeline.step_calls)}

    def _validate_adopt_tutorials(payload: dict[str, Any]) -> list[dict[str, Any]]:
        """A2 轻校验：1~4 套；每套 set_no(≤4)/set_name(≤200)/textbook.title 非空，exercise 可空。"""
        tutorials = payload.get("tutorials")
        if not isinstance(tutorials, list) or not 1 <= len(tutorials) <= 4:
            raise api_error(422, "INVALID_PARAMS", "tutorials 必须为 1~4 套")
        for i, item in enumerate(tutorials):
            if not isinstance(item, dict):
                raise api_error(422, "INVALID_PARAMS", f"tutorials[{i}] 必须为对象")
            set_no = str(item.get("set_no", "")).strip()
            if not set_no or len(set_no) > 4:
                raise api_error(422, "INVALID_PARAMS", f"tutorials[{i}].set_no 非空且 ≤4 字符")
            set_name = str(item.get("set_name", "")).strip()
            if not set_name or len(set_name) > 200:
                raise api_error(422, "INVALID_PARAMS", f"tutorials[{i}].set_name 非空且 ≤200 字符")
            textbook = item.get("textbook")
            if not isinstance(textbook, dict) or not str(textbook.get("title", "")).strip():
                raise api_error(422, "INVALID_PARAMS", f"tutorials[{i}].textbook.title 非空")
            exercise = item.get("exercise")
            if exercise is not None and (
                not isinstance(exercise, dict) or not str(exercise.get("title", "")).strip()
            ):
                raise api_error(422, "INVALID_PARAMS", f"tutorials[{i}].exercise.title 非空（或 null 同源）")
        return tutorials

    @fastapi_app.post("/api/v1/courses/{course_id}/knowledge", status_code=201)
    def adopt_course_knowledge(course_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        """A2 课程知识采纳：每套建 draft qt_knowledge 行，预填六字段（幂等/套号冲突见仓储）。"""
        repo = _kn(app)
        if repo.get_course(course_id) is None:
            raise api_error(404, "COURSE_NOT_FOUND", f"课程不存在：{course_id}")
        tutorials = _validate_adopt_tutorials(payload)
        try:
            results = repo.adopt_tutorials(course_id, tutorials)
        except KeyError as exc:
            raise api_error(404, "COURSE_NOT_FOUND", str(exc)) from exc
        except AdoptionConflict as exc:
            raise api_error(409, "SET_NO_CONFLICT", str(exc)) from exc
        return {"created": results}

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
