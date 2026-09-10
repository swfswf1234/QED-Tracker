"""QED-Tracker FastAPI 服务（8901）。

契约（docs/architecture/api.md；服务运行面见 docs/design/service-management.md）：
- 只读查询同步返回：健康、搜索、资源、目录、任务列表；
- 写操作提交后台任务，状态 queued→running→succeeded/failed，并发上限 2；
- 同内容（sha256）幂等复用，重复提交不产生重复文件。
- QED-030：qt_resources 旧资源 API 已退役（0005 drop），资源域为五层模型语义
  （qed_domain → qed_course → qt_knowledge → qt_books → qt_sources）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from qed_tracker import __version__
from qed_tracker.api.tasks import TaskManager
from qed_tracker.application import BookService, ResourceService
from qed_tracker.application.book_fetch import BookFetchService, build_book_service
from qed_tracker.application.domain_file import (
    read_domain_courses_file,
    read_domain_file,
    write_domain_courses_file,
    write_domain_file,
)
from qed_tracker.application.knowledge_import import _BOOK_ID_RE, KnowledgeImportError, validate_domain
from qed_tracker.application.papers import PaperService
from qed_tracker.catalog import list_catalogs, load_catalog
from qed_tracker.config import Settings, llm_api_key
from qed_tracker.db.knowledge_repository import (
    CLEAR,
    AdoptionConflict,
    CourseHasKnowledge,
    DomainNotEmpty,
    InvalidExplorationTransition,
    KnowledgeRepository,
)
from qed_tracker.db.models import BookStatus, QedDomain
from qed_tracker.db.tasks_repository import ActiveTaskExists, TaskStore
from qed_tracker.downloader import DownloadManager, inspect_pdf, safe_filename
from qed_tracker.inventory import Inventory, downloads_tmp_dir, raw_course_dir
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

logger = logging.getLogger("qed_tracker.api")

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
        self._db_engine = None
        self._knowledge_repository = knowledge_repository
        self._session_factory = None
        # 会话工厂来源：优先复用注入 repo 的工厂（测试 SQLite 路径），
        # 否则凭据齐备时自建 MySQL engine——两表域操作必须共享同一事务边界。
        factory = knowledge_repository.session_factory if knowledge_repository is not None else None
        if factory is None and settings.db_configured:
            from qed_tracker.db.engine import create_engine_for, session_factory

            self._db_engine = create_engine_for(settings)
            factory = session_factory(self._db_engine)
            self._knowledge_repository = KnowledgeRepository(factory)
        self._session_factory = factory
        # REQ-032：PaperService 需要 session_factory 创建 SelectionStore
        self.papers = PaperService(
            papers_provider or ArxivProvider(retries=settings.retries),
            self.resources,
            session_factory=factory,
        )
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
    book_service_factory=None,
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

    # 测试注入假工厂（不得访问公网）；默认每次任务经 build_book_service 新建独立服务。
    service_factory = book_service_factory or (lambda: build_book_service(settings))

    def _book_advisor():
        """每次 fetch 新建书级 advisor 实例（L6 裁决：budget 隔离；预算 = QED_BOOK_LLM_BUDGET）。"""
        if not settings.llm_configured:
            return None
        return BailianBookAdvisor(
            api_key=llm_api_key(),
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            call_budget=settings.book_llm_budget,
            max_tokens=settings.llm_max_tokens,
            api_select=settings.api_select,
            gateway_url=settings.llm_gateway_url,
            engine=app._db_engine,
        )

    def _new_fetcher() -> BookFetchService:
        """每次任务新建取书编排器（服务/顾问经工厂隔离，结束 close 自灭孤儿线程）。"""
        return BookFetchService(
            _kn(app),
            service_factory,
            data_root=settings.data_root,
            candidate_budget=settings.book_candidate_budget,
            min_pages=settings.book_min_pages,
            min_size_bytes=settings.book_min_size_bytes,
            search_limit=settings.book_search_limit,
            query_variants=settings.book_query_variants,
            llm_query=settings.book_llm_query,
            llm_confirm=settings.book_llm_confirm,
            advisor_factory=_book_advisor,
        )

    def _book_download_handler(params: dict[str, Any], progress) -> dict[str, Any]:
        """book_download 后台任务：书级五阶段取书（检索→确认→预算下载→staging 验收→登记）。"""
        book_id = str(params.get("book_id", "")).strip()
        if not book_id:
            raise ValueError("book_id 必填")
        return _new_fetcher().fetch(book_id, progress=progress)

    def _tutorial_fetch_handler(params: dict[str, Any], progress) -> dict[str, Any]:
        """tutorial_fetch 后台任务：教程级批量取书（refs 聚合 → 排除 owned → 顺序逐书）。"""
        knowledge_id = str(params.get("knowledge_id", "")).strip()
        if not knowledge_id:
            raise ValueError("knowledge_id 必填")
        include_parallel = params.get("include_parallel") is True
        return _new_fetcher().fetch_tutorial(
            knowledge_id, include_parallel=include_parallel, progress=progress
        )

    def _domain_explore_handler(params: dict[str, Any], progress) -> dict[str, Any]:
        """domain_explore 后台任务：LLM 探索领域（只跑 domain@v4）→ 结果写入 domains.json → 已生成。"""
        domain_id = str(params.get("domain_id", "")).strip()
        if not domain_id:
            raise ValueError("domain_id 必填")
        mode = str(params.get("mode", "web")).strip() or "web"
        repo = _kn(app)
        domain = repo.get_domain(domain_id)
        if domain is None:
            raise ValueError(f"领域不存在：{domain_id}")
        progress(10, "初始化管线")
        pipeline = DomainPipeline(**_advisor_kwargs())
        try:
            report = pipeline.explore_domain_only(domain.name, mode=mode)
        except NameConfirmationRequired as exc:
            repo.update_domain(
                domain_id, exploration_stage="待确认",
                explore_pending={"kind": "name_confirmation", "name_check": exc.name_check},
            )
            return {"domain_id": domain_id, "status": "name_confirmation_required"}
        except PipelineError as exc:
            repo.update_domain(domain_id, exploration_stage="待确认",
                               explore_pending={"kind": "error", "error": str(exc)})
            raise
        finally:
            pipeline.close()
        progress(80, "写入探索结果")
        # 组装与 import 同构的 domain JSON → 写入文件（不含 courses，courses 由 confirm-domain 后后台生成）
        domain_data = {
            "domain": domain_id,
            "name": domain.name,
            "description": report["domain"].get("description", ""),
            "stages": report["domain"].get("stages", []),
            "level": domain.level or "",
            "scope": domain.scope or "",
            "classic_tracks": report["domain"].get("classic_tracks", []),
            "courses": [],  # courses@v8 尚未执行，留空
        }
        write_domain_file(app.settings.data_root, domain_id, domain_data)
        repo.update_domain(domain_id, exploration_stage="已生成")
        progress(100, "完成")
        return {"domain_id": domain_id, "courses_found": 0}

    def _domain_explore_courses_handler(params: dict[str, Any], progress) -> dict[str, Any]:
        """domain_explore_courses 后台任务：只跑 courses@v8 → 结果写入 courses.json → 待确认。"""
        domain_id = str(params.get("domain_id", "")).strip()
        if not domain_id:
            raise ValueError("domain_id 必填")
        mode = str(params.get("mode", "direct")).strip() or "direct"
        repo = _kn(app)
        domain = repo.get_domain(domain_id)
        if domain is None:
            raise ValueError(f"领域不存在：{domain_id}")
        progress(10, "读取领域信息")
        try:
            domain_info = read_domain_file(app.settings.data_root, domain_id)
        except FileNotFoundError:
            raise ValueError(f"领域文件不存在：raw/{domain_id}/domains.json，请先完成领域探索")
        progress(20, "初始化管线")
        pipeline = DomainPipeline(**_advisor_kwargs())
        try:
            report = pipeline.explore_courses_only(domain.name, domain_info, mode=mode)
        except PipelineError as exc:
            repo.update_domain(domain_id, exploration_stage="待确认",
                               explore_pending={"kind": "error", "error": str(exc)})
            raise
        finally:
            pipeline.close()
        progress(80, "写入课程探索结果")
        # 组装 courses JSON → 写入文件
        courses_data = {
            "domain_id": domain_id,
            "courses": [
                {
                    "course_id": c["course_id"],
                    "name": c["name"],
                    "track": c.get("track", ""),
                    "stage": c.get("stage", ""),
                    "aliases": c.get("aliases", []),
                    "summary": c.get("summary", ""),
                    "prerequisites": c.get("prerequisites", []),
                }
                for c in report["courses"]
            ],
            "path": report.get("path", {}),
        }
        write_domain_courses_file(app.settings.data_root, domain_id, courses_data)
        repo.update_domain(domain_id, exploration_stage="待确认")
        progress(100, "完成")
        return {"domain_id": domain_id, "courses_found": len(courses_data["courses"])}

    def _course_explore_handler(params: dict[str, Any], progress) -> dict[str, Any]:
        """course_explore 后台任务：LLM 探索课程教材 → 结果写入 explore_pending → 待确认。"""
        course_id = str(params.get("course_id", "")).strip()
        if not course_id:
            raise ValueError("course_id 必填")
        mode = str(params.get("mode", "web")).strip() or "web"
        repo = _kn(app)
        course_row = repo.get_course(course_id)
        if course_row is None:
            raise ValueError(f"课程不存在：{course_id}")
        progress(10, "初始化管线")
        pipeline = CoursePipeline(**_advisor_kwargs())
        try:
            course_data = {
                "course_id": course_row.course_id,
                "name": course_row.name,
                "aliases": course_row.aliases or [],
                "stage": course_row.stage,
                "prerequisites": course_row.prerequisites or [],
                "note": course_row.description or "",
            }
            report = pipeline.explore(course_data, domain_name=course_row.domain_id, mode=mode)
        except PipelineError as exc:
            repo.update_course(course_id, exploration_stage="待确认",
                               explore_pending={"kind": "error", "error": str(exc)})
            raise
        finally:
            pipeline.close()
        progress(80, "写入探索结果")
        tutorials = report.get("tutorials", [])
        explore_pending = {
            "kind": "review_results",
            "tutorials": [
                {"proposal_id": t.get("proposal_id", ""), "set_no": t.get("set_no", ""),
                 "set_name": t.get("set_name", ""), "reason": t.get("reason", "")}
                for t in tutorials
            ],
        }
        repo.update_course(course_id, exploration_stage="待确认", explore_pending=explore_pending)
        progress(100, "完成")
        return {"course_id": course_id, "tutorials_found": len(tutorials)}

    # extra_handlers 优先级高于内置 handler（测试可覆盖 domain_explore/course_explore）
    all_handlers = {
        "book_download": _book_download_handler,
        "tutorial_fetch": _tutorial_fetch_handler,
        "domain_explore": _domain_explore_handler,
        "domain_explore_courses": _domain_explore_courses_handler,
        "course_explore": _course_explore_handler,
        **(extra_handlers or {}),
    }
    # REQ-032：TaskStore 使用 qt_tasks 数据库表
    # 优先复用 knowledge_repository 的 session_factory（测试 SQLite / 生产 MySQL），
    # 否则为 TaskStore 创建独立的 SQLite 引擎（兼容无 MySQL 测试场景）。
    if app._session_factory is not None:
        task_store = TaskStore(app._session_factory)
    else:
        import sqlalchemy as _sa
        from sqlalchemy.pool import StaticPool

        from qed_tracker.db.engine import session_factory as _sf
        from qed_tracker.db.models import Base as _Base
        _engine = _sa.create_engine(
            "sqlite://", future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        _Base.metadata.create_all(_engine)
        app._task_engine = _engine  # prevent GC
        task_store = TaskStore(_sf(_engine))
    manager = TaskManager(task_store, all_handlers)
    app._manager = manager  # 暴露给测试和 lifespan

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        manager.shutdown(wait=True)
        app.close()

    fastapi_app = FastAPI(title="QED-Tracker", version=__version__, lifespan=lifespan)
    fastapi_app._manager = manager  # 暴露给测试
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
    # 契约：docs/architecture/database-private-tables.md。彻底隐藏语义在数据层实现（rejected/superseded/failed 默认过滤）。

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
            raise HTTPException(status_code=404, detail=f"教程不存在：{knowledge_id}")
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
        """领域课程详情：待确认状态优先返回 courses.json 文件数据，否则从数据库读取。"""
        repo = _kn(app)
        domain = next((d for d in repo.list_domains() if d.domain_id == domain_id), None)
        if domain is None:
            raise HTTPException(status_code=404, detail=f"未知学科课程体系：{domain_id}")

        # 待确认状态：优先返回 courses.json 文件数据
        if domain.exploration_stage == "待确认":
            try:
                courses_data = read_domain_courses_file(app.settings.data_root, domain_id)
                # 合并 domain 基本信息 + courses.json 数据
                view = _domain_view(repo, domain)
                view["courses"] = courses_data.get("courses", [])
                view["path"] = courses_data.get("path", {})
                view["source"] = "json_file"
                return view
            except FileNotFoundError:
                # JSON 文件不存在，回退到数据库
                pass

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

    @fastapi_app.get("/api/v1/domains/{domain_id}")
    def domain_detail(domain_id: str) -> dict[str, Any]:
        """领域详情：已生成状态优先返回 JSON 文件数据，否则从数据库读取。"""
        repo = _kn(app)
        domain = repo.get_domain(domain_id)
        if domain is None:
            raise api_error(404, "DOMAIN_NOT_FOUND", f"领域不存在：{domain_id}")

        # 已生成状态：优先返回 JSON 文件数据
        if domain.exploration_stage == "已生成":
            try:
                json_data = read_domain_file(app.settings.data_root, domain_id)
                return {
                    "domain_id": domain_id,
                    "name": json_data.get("name", domain.name),
                    "description": json_data.get("description", domain.description),
                    "stages": json_data.get("stages", []),
                    "level": json_data.get("level", domain.level),
                    "scope": json_data.get("scope", domain.scope),
                    "classic_tracks": json_data.get("classic_tracks", []),
                    "courses": json_data.get("courses", []),
                    "exploration_stage": domain.exploration_stage,
                    "source": "json_file",
                }
            except FileNotFoundError:
                # JSON 文件不存在，回退到数据库
                pass

        # 其他状态：从数据库读取
        return _domain_view(repo, domain)

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

    # ---------------- REQ-067-B12: apply-results / re-explore ----------------

    def _require_domain(repo: KnowledgeRepository, domain_id: str) -> QedDomain:
        domain = repo.get_domain(domain_id)
        if domain is None:
            raise api_error(404, "DOMAIN_NOT_FOUND", f"领域不存在：{domain_id}")
        return domain

    def _require_course(repo: KnowledgeRepository, course_id: str):
        course = repo.get_course(course_id)
        if course is None:
            raise api_error(404, "COURSE_NOT_FOUND", f"课程不存在：{course_id}")
        return course

    def _sync_courses_from_json_to_db(
        repo: KnowledgeRepository,
        domain_id: str,
        data_root: Path,
    ) -> int:
        """将 courses.json 中的课程同步到 qed_course 数据库表（幂等：已存在则更新）。

        courses@v8 后台任务只写入 JSON 文件，不写入数据库。
        apply_domain_results 需要从数据库查询课程，因此需要先同步。
        返回同步的课程数。
        """
        try:
            courses_data = read_domain_courses_file(data_root, domain_id)
        except FileNotFoundError:
            return 0  # 无文件则跳过（回退到纯数据库查询）
        courses = courses_data.get("courses", [])
        synced = 0
        for index, course in enumerate(courses):
            cid = str(course["course_id"])
            repo.create_course(
                course_id=cid,
                domain_id=domain_id,
                name=course["name"],
                stage=course.get("stage", ""),
                sort_order=index,
                prerequisites=course.get("prerequisites", []),
                aliases=course.get("aliases", []),
                description=course.get("summary", ""),
                track=course.get("track", ""),
            )
            synced += 1
        return synced

    @fastapi_app.post("/api/v1/domains/{domain_id}/apply-results")
    def domain_apply_results(domain_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """确认领域探索结果：选择要保留的课程，删除其余，exploration_stage -> 已完成。"""
        repo = _kn(app)
        domain = _require_domain(repo, domain_id)
        if domain.exploration_stage != "待确认":
            raise api_error(409, "INVALID_TRANSITION",
                            f"当前状态 {domain.exploration_stage}，需要 待确认")
        selected_courses = payload.get("selected_courses")
        if not isinstance(selected_courses, list):
            raise api_error(422, "INVALID_PARAMS", "selected_courses 必须是数组")
        # 待确认状态下，courses@v8 写入的是 JSON 文件而非数据库，需先同步
        _sync_courses_from_json_to_db(repo, domain_id, app.settings.data_root)
        try:
            kept = repo.apply_domain_results(domain_id, selected_courses)
        except InvalidExplorationTransition as exc:
            raise api_error(409, "INVALID_TRANSITION", str(exc)) from None
        return {"domain_id": domain_id, "courses_kept": kept}

    @fastapi_app.post("/api/v1/domains/{domain_id}/re-explore", status_code=202)
    def domain_re_explore(domain_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        """重置领域探索：exploration_stage -> 探索中，提交后台重新探索任务。"""
        repo = _kn(app)
        domain = _require_domain(repo, domain_id)
        if domain.exploration_stage != "待确认":
            raise api_error(409, "INVALID_TRANSITION",
                            f"当前状态 {domain.exploration_stage}，需要 待确认")
        # 更新描述（可选）+ 重置状态
        description = payload.get("description") or domain.description
        repo.update_domain(domain_id, description=description,
                           exploration_stage="探索中", explore_pending=CLEAR)
        # 提交后台任务
        record = manager.submit("domain_explore", {"domain_id": domain_id, "mode": payload.get("mode", "web")})
        return {"task_id": record.task_id}

    @fastapi_app.post("/api/v1/courses/{course_id}/apply-results")
    def course_apply_results(course_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """确认课程探索结果：选择要保留的教程，删除其余，exploration_stage -> 已完成。"""
        repo = _kn(app)
        course = _require_course(repo, course_id)
        if course.exploration_stage != "待确认":
            raise api_error(409, "INVALID_TRANSITION",
                            f"当前状态 {course.exploration_stage}，需要 待确认")
        selected_tutorials = payload.get("selected_tutorials")
        if not isinstance(selected_tutorials, list):
            raise api_error(422, "INVALID_PARAMS", "selected_tutorials 必须是数组")
        try:
            kept = repo.apply_course_results(course_id, selected_tutorials)
        except InvalidExplorationTransition as exc:
            raise api_error(409, "INVALID_TRANSITION", str(exc)) from None
        return {"course_id": course_id, "tutorials_kept": kept}

    @fastapi_app.post("/api/v1/courses/{course_id}/re-explore", status_code=202)
    def course_re_explore(course_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        """重置课程探索：exploration_stage -> 探索中，提交后台重新探索任务。"""
        repo = _kn(app)
        course = _require_course(repo, course_id)
        if course.exploration_stage != "待确认":
            raise api_error(409, "INVALID_TRANSITION",
                            f"当前状态 {course.exploration_stage}，需要 待确认")
        # 更新描述（可选）+ 重置状态
        description = payload.get("description") or course.description
        repo.update_course(course_id, description=description,
                           exploration_stage="探索中", explore_pending=CLEAR)
        # 提交后台任务
        record = manager.submit("course_explore", {"course_id": course_id, "mode": payload.get("mode", "web")})
        return {"task_id": record.task_id}

    @fastapi_app.post("/api/v1/domains/import")
    def import_domain(payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        """领域知识 JSON 导入（QED-050-D）：校验 → 写入文件暂存 → 更新领域状态为已生成。

        body：`{"domain": {...}}`（内联 JSON）或 `{"file_path": "..."}`（本机可读文件路径）。
        落盘语义：写入 QED_DATA_ROOT/raw/{domain_id}/domains.json，同时更新 domain 的
        exploration_stage 为"已生成"。用户查看文件后调 POST /domains/{domain_id}/confirm
        继续后续流程。
        """
        file_path = str(payload.get("file_path", "")).strip()
        if file_path:
            try:
                with open(file_path, encoding="utf-8") as stream:
                    data = json.load(stream)
            except OSError as exc:
                raise api_error(400, "INVALID_PARAMS", f"文件不可读：{file_path}") from exc
            except json.JSONDecodeError as exc:
                raise api_error(400, "INVALID_PARAMS", f"JSON 解析失败：{exc}") from exc
        else:
            data = payload.get("domain")
        if data is None:
            raise api_error(422, "INVALID_PARAMS", "必须提供 domain 对象或 file_path")
        try:
            data = validate_domain(data)
        except KnowledgeImportError as exc:
            raise api_error(400, "INVALID_PARAMS", str(exc)) from exc

        domain_id = str(data["domain"])
        target = write_domain_file(app.settings.data_root, domain_id, data)

        # 更新领域状态为"已生成"（领域必须已存在）
        repo = _kn(app)
        try:
            repo.update_domain(domain_id, exploration_stage="已生成")
        except KeyError:
            raise api_error(404, "DOMAIN_NOT_FOUND", f"领域不存在：{domain_id}") from None

        return {
            "domain_id": domain_id,
            "file_path": str(target),
            "exploration_stage": "已生成",
            "message": "领域知识已写入文件，状态更新为已生成",
        }

    @fastapi_app.post("/api/v1/domains/{domain_id}/confirm")
    def domain_confirm(domain_id: str) -> dict[str, Any]:
        """确认领域知识：读取 domains.json → upsert QedDomain。

        如果 domains.json 中已有课程（手动导入），直接写入 courses.json，设置 stage="待确认"。
        如果没有课程（LLM 探索），异步提交 courses@v8 后台任务。

        幂等：重复 confirm 只覆盖，不重复创建。
        """
        repo = _kn(app)
        try:
            data = read_domain_file(app.settings.data_root, domain_id)
        except FileNotFoundError:
            raise api_error(404, "FILE_NOT_FOUND", f"领域文件不存在：raw/{domain_id}/domains.json，请先导入")

        # upsert domain
        if repo.get_domain(domain_id) is None:
            repo.create_domain(
                domain_id=domain_id, name=data["name"], description=data.get("description", ""),
                stages=data.get("stages", []), level=data.get("level", ""),
                scope=data.get("scope", ""), classic_tracks=data.get("classic_tracks", []),
            )
        else:
            repo.update_domain(
                domain_id, description=data.get("description", ""),
                stages=data.get("stages", []), level=data.get("level", ""),
                scope=data.get("scope", ""), classic_tracks=data.get("classic_tracks", []),
                exploration_stage="探索中",
            )

        # 检查 domains.json 中是否已有课程
        existing_courses = data.get("courses", [])

        if existing_courses:
            # 手动导入：直接写入 courses.json，不触发 LLM
            courses_data = {
                "domain_id": domain_id,
                "courses": existing_courses,
                "path": data.get("path", {}),
            }
            write_domain_courses_file(app.settings.data_root, domain_id, courses_data)
            repo.update_domain(domain_id, exploration_stage="待确认")
            return {
                "domain_id": domain_id,
                "task_id": None,
                "exploration_stage": "待确认",
                "message": "领域已确认，课程已从导入文件同步",
            }
        else:
            # LLM 探索：提交 courses@v8 任务
            record = manager.submit("domain_explore_courses", {
                "domain_id": domain_id,
                "mode": "direct",
            })
            return {
                "domain_id": domain_id,
                "task_id": record.task_id,
                "exploration_stage": "探索中",
                "message": "已提交 courses@v8 后台任务，轮询 GET /api/v1/tasks/{task_id} 等待完成",
            }

    @fastapi_app.post("/api/v1/domains/{domain_id}/courses/import")
    def import_domain_courses(domain_id: str) -> dict[str, Any]:
        """从 domains.json 读取 courses 并写入 qed_course，探索中→待确认。

        用于 confirm-domain 后手动导入课程的场景。
        """
        repo = _kn(app)
        domain = _require_domain(repo, domain_id)
        if domain.exploration_stage not in ("已生成", "探索中"):
            raise api_error(409, "INVALID_TRANSITION",
                            f"当前状态 {domain.exploration_stage}，需要 已生成 或 探索中")

        try:
            data = read_domain_file(app.settings.data_root, domain_id)
        except FileNotFoundError:
            raise api_error(404, "FILE_NOT_FOUND", f"领域文件不存在：raw/{domain_id}/domains.json")

        courses = data.get("courses", [])
        if not courses:
            raise api_error(400, "INVALID_PARAMS", "domains.json 中没有课程数据")

        created = 0
        updated = 0
        for index, course in enumerate(courses):
            cid = str(course["course_id"])
            if repo.get_course(cid) is None:
                repo.create_course(
                    course_id=cid, domain_id=domain_id, name=course["name"],
                    stage=course.get("stage", ""), sort_order=index,
                    prerequisites=course.get("prerequisites", []),
                    aliases=course.get("aliases", []),
                    description=course.get("summary", ""), track=course.get("track", ""),
                )
                created += 1
            else:
                repo.update_course(
                    cid, stage=course.get("stage", ""), description=course.get("summary", ""),
                    aliases=course.get("aliases", []), track=course.get("track", ""),
                    prerequisites=course.get("prerequisites", []),
                )
                updated += 1

        repo.update_domain(domain_id, exploration_stage="待确认")
        return {
            "domain_id": domain_id,
            "courses_created": created,
            "courses_updated": updated,
            "exploration_stage": "待确认",
        }

    @fastapi_app.get("/api/v1/knowledge")
    def knowledge_list(course_id: str = "", status: str = "") -> list[dict[str, Any]]:
        return [row.to_dict() for row in _kn(app).list_knowledge(course_id=course_id or None, status=status or None)]

    @fastapi_app.get("/api/v1/knowledge/{knowledge_id}")
    def knowledge_detail(knowledge_id: str) -> dict[str, Any]:
        repo = _kn(app)
        _require_knowledge(repo, knowledge_id)
        return _knowledge_view(repo, repo.get_knowledge(knowledge_id))

    @fastapi_app.post("/api/v1/knowledge/{knowledge_id}/confirm")
    def knowledge_confirm(knowledge_id: str) -> dict[str, Any]:
        repo = _kn(app)
        _require_knowledge(repo, knowledge_id)
        row = repo.confirm_knowledge(knowledge_id)
        return _knowledge_view(repo, row)

    @fastapi_app.post("/api/v1/books", status_code=201)
    def create_book(payload: dict[str, Any]) -> dict[str, Any]:
        """书库化创建（QED-050）：book_id 显式、无 knowledge_id（归属由教程 refs 承载）。

        body：book_id（{abbr}-b{NN}）与 title 必填；authors=[{name, role}]；可选
        part/original_title/publisher/edition/year/language/roles/status/domain_id/notes。
        """
        book_id = str(payload.get("book_id", "")).strip()
        if not _BOOK_ID_RE.match(book_id):
            raise api_error(422, "INVALID_PARAMS",
                            f"book_id 格式错误（应为 {{abbr}}-b{{NN}}）：{book_id}")
        title = str(payload.get("title", "")).strip()
        if not title:
            raise api_error(422, "INVALID_PARAMS", "必须提供 title")
        status = str(payload.get("status", "candidate")).strip()
        if status not in {item.value for item in BookStatus}:
            raise api_error(422, "INVALID_PARAMS", f"status 值域错误（{'/'.join(s.value for s in BookStatus)}）：{status}")
        year = payload.get("year")
        if year is not None and type(year) is not int:
            raise api_error(422, "INVALID_PARAMS", "year 必须为整数")
        authors = payload.get("authors")
        if authors is not None and not (isinstance(authors, list) and all(isinstance(item, dict) for item in authors)):
            raise api_error(422, "INVALID_PARAMS", "authors 必须为对象数组（[{name, role}]）")
        repo = _kn(app)
        if repo.get_book(book_id) is not None:
            raise api_error(409, "BOOK_ALREADY_EXISTS", f"book_id 已存在：{book_id}")
        row = repo.create_book(
            book_id,
            title=title,
            part=str(payload.get("part", "")),
            original_title=str(payload.get("original_title", "")).strip() or None,
            authors=authors or [],
            publisher=str(payload.get("publisher", "")),
            edition=str(payload.get("edition", "")),
            year=year,
            language=str(payload.get("language", "")),
            roles=payload.get("roles") or [],
            status=status,
            domain_id=str(payload.get("domain_id", "")),
            notes=str(payload.get("notes", "")) or None,
        )
        return row.to_dict()

    @fastapi_app.get("/api/v1/books/{book_id}/sources")
    def book_sources(book_id: str) -> list[dict[str, Any]]:
        repo = _kn(app)
        if repo.get_book(book_id) is None:
            raise HTTPException(status_code=404, detail=f"书籍不存在：{book_id}")
        return [s.to_dict() for s in repo.list_sources(book_id)]

    @fastapi_app.post("/api/v1/books/{book_id}/sources")
    def book_add_source(book_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        repo = _kn(app)
        if repo.get_book(book_id) is None:
            raise HTTPException(status_code=404, detail=f"书籍不存在：{book_id}")
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

    def _inspect_local_pdf(path: Path) -> tuple[str, int, int]:
        """人工路径完整性校验（魔数 + pypdf 可解析 + sha256）：失败统一 400。

        跳过初筛门槛（页数/大小/文本层不拒人工文件，QED-050 人工导入设计）。
        """
        try:
            return inspect_pdf(path)
        except Exception as exc:  # noqa: BLE001 - PDF 校验失败统一 400
            raise api_error(400, "INVALID_PARAMS", str(exc)) from exc

    def _sha256_file(path: Path) -> str:
        """既有文件内容指纹（导入去重比对用，不要求目标为可解析 PDF）。"""
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @fastapi_app.post("/api/v1/books/{book_id}/register")
    def book_register(book_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        """数据根内已有文件原地登记（QED-050 人工路径）：完整性校验 → mark_owned 唯一写入口。"""
        repo = _kn(app)
        if repo.get_book(book_id) is None:
            raise api_error(404, "BOOK_NOT_FOUND", f"书籍不存在：{book_id}")
        relative = str(payload.get("relative_path", "")).strip()
        if not relative:
            raise api_error(422, "INVALID_PARAMS", "必须提供数据根内相对路径（relative_path）")
        path = (app.resources.inventory.data_root / relative).resolve()
        try:
            path.relative_to(app.resources.inventory.data_root)
        except ValueError as exc:
            raise api_error(400, "INVALID_PARAMS", "路径必须在数据根目录内") from exc
        if not path.is_file():
            raise api_error(404, "FILE_NOT_FOUND", f"文件不存在：{relative}")
        digest, size, pages = _inspect_local_pdf(path)
        repo.mark_owned(book_id, file_path=path.relative_to(app.resources.inventory.data_root).as_posix())
        repo.add_source(book_id, channel="local_import", ok=True, download_url=relative,
                        note=f"原地登记（{size} bytes，{pages} 页，sha256 {digest[:8]}）")
        return repo.get_book(book_id).to_dict()

    @fastapi_app.post("/api/v1/books/{book_id}/import")
    def book_import(book_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        """人工导入（QED-050，D3）：本地 PDF（可在数据根外）→ 完整性校验 → 暂存原子落盘 → mark_owned。

        body：`{"file_path": "...", "target_path": "..."?}`
        - 跳过初筛门槛（页数/大小/文本层不拒人工文件）；完整性失败（魔数/pypdf）400 拒绝；
        - target_path（D9：期望路径不含 sha，落盘补 `_<sha8>`）或默认桶经 refs 反查
          （raw/<domain>/<course>/，反查不到 → 422 要求显式 target_path）；
        - 目标已存在同 sha → 复用不重复落盘；不同内容 → 409 不覆盖用户文件；
        - 渠道留痕 channel=local_import。
        """
        repo = _kn(app)
        row = repo.get_book(book_id)
        if row is None:
            raise api_error(404, "BOOK_NOT_FOUND", f"书籍不存在：{book_id}")
        file_path = str(payload.get("file_path", "")).strip()
        if not file_path:
            raise api_error(422, "INVALID_PARAMS", "必须提供本地文件路径（file_path）")
        source = Path(file_path).expanduser()
        if not source.is_file():
            raise api_error(404, "FILE_NOT_FOUND", f"文件不存在：{file_path}")
        digest, size, pages = _inspect_local_pdf(source)

        data_root = app.resources.inventory.data_root
        raw_target = str(payload.get("target_path", "")).strip()
        if raw_target:
            target = (data_root / raw_target).resolve()
            try:
                target.relative_to(data_root)
            except ValueError as exc:
                raise api_error(400, "INVALID_PARAMS", f"target_path 必须在数据根目录内：{raw_target}") from exc
        else:
            course_id = repo.first_course_for_book(book_id)
            if not course_id:
                raise api_error(422, "NO_COURSE_REF",
                                "书籍无教程引用归属，无法推导默认路径（请显式提供 target_path）")
            base = safe_filename(row.title).removesuffix(".pdf")
            target = raw_course_dir(data_root, course_id) / f"{base}_{digest[:8]}.pdf"
        # D9：期望路径不含 sha 后缀 → 落盘按命名规则补 _<sha8>
        if target.suffix.lower() == ".pdf" and not target.stem.endswith(f"_{digest[:8]}"):
            target = target.with_name(f"{target.stem}_{digest[:8]}.pdf")

        if target.exists():
            existing_digest = _sha256_file(target)
            if existing_digest != digest:
                raise api_error(409, "TARGET_CONFLICT",
                                f"目标已存在且内容不同（不覆盖用户文件）：{target.relative_to(data_root).as_posix()}")
        elif target.resolve() != source.resolve():
            target.parent.mkdir(parents=True, exist_ok=True)
            staging = downloads_tmp_dir(data_root) / f"{target.stem}_{uuid.uuid4().hex[:8]}.download"
            staging.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, staging)
            if staging.stat().st_size != size:
                staging.unlink(missing_ok=True)
                raise api_error(400, "INVALID_PARAMS", "导入文件大小与校验不符（拷贝失败）")
            os.replace(staging, target)

        relative = target.relative_to(data_root).as_posix()
        repo.mark_owned(book_id, file_path=relative)
        repo.add_source(book_id, channel="local_import", ok=True, download_url=str(source),
                        note=f"手工导入（{size} bytes，{pages} 页，sha256 {digest[:8]}；跳过初筛门槛）")
        return repo.get_book(book_id).to_dict()

    @fastapi_app.post("/api/v1/books/{book_id}/fetch", status_code=202)
    def book_fetch(book_id: str) -> dict[str, str]:
        """书级自动取书（QED-050 五阶段）：202 + 后台任务；已 owned 由编排层 no-op。

        并发防护：同书已有活动 fetch 任务 → 409；退役书不再取书。
        """
        repo = _kn(app)
        row = repo.get_book(book_id)
        if row is None:
            raise api_error(404, "BOOK_NOT_FOUND", f"书籍不存在：{book_id}")
        if row.status == BookStatus.RETIRED.value:
            raise api_error(409, "BOOK_RETIRED", f"书籍已退役，不可取书：{book_id}")
        try:
            record = manager.submit("book_download", {"book_id": book_id}, dedup={"book_id": book_id})
        except ActiveTaskExists as exc:
            raise api_error(409, "TASK_ALREADY_RUNNING", str(exc)) from exc
        return {"task_id": record.task_id, "book_id": book_id}

    @fastapi_app.post("/api/v1/knowledge/{knowledge_id}/fetch", status_code=202)
    def knowledge_fetch(knowledge_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, str]:
        """教程级批量取书（QED-050 双入口）：refs 聚合书集 → 排除已 owned → 单任务顺序逐书。

        body 可选 `{"include_parallel": true}` 显式纳入 parallel_ref；部分失败不中断，
        结果汇总进任务 result。并发防护：同教程已有活动任务 → 409。
        """
        repo = _kn(app)
        _require_knowledge(repo, knowledge_id)
        params = {"knowledge_id": knowledge_id, "include_parallel": payload.get("include_parallel") is True}
        try:
            record = manager.submit("tutorial_fetch", params, dedup={"knowledge_id": knowledge_id})
        except ActiveTaskExists as exc:
            raise api_error(409, "TASK_ALREADY_RUNNING", str(exc)) from exc
        return {"task_id": record.task_id, "knowledge_id": knowledge_id}

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
            # dry-run 不写任何表：engine 置 None，避免在同步 handler 中复用共享 DB 引擎（联调 2026-08-28）
            pipeline = DomainPipeline(**{**_advisor_kwargs(), "engine": None})
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
            logger.warning("prompt-explore dry-run 失败：%s：%s", exc.code, exc)
            status_code = 400 if exc.code == "INVALID_PARAMS" else 502
            raise api_error(status_code, exc.code, str(exc)) from exc
        finally:
            pipeline.close()
        return {"dry_run": True, "confirmation_required": False, "report": report, "calls": list(pipeline.step_calls)}

    @fastapi_app.post("/api/v1/courses/{course_id}/prompt-explores/dry-run")
    def course_prompt_explore_dry_run(
        course_id: str, payload: dict[str, Any] = _EMPTY_BODY
    ) -> dict[str, Any]:
        """课程教材探索 dry-run（QED-047，A1）：同步单步 tutorials@v2，不写任何表。"""
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
            # dry-run 不写任何表：engine 置 None，避免在同步 handler 中复用共享 DB 引擎（联调 2026-08-28）
            pipeline = CoursePipeline(**{**_advisor_kwargs(), "engine": None})
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
            logger.warning("course prompt-explore dry-run 失败：%s：%s", exc.code, exc)
            status_code = 400 if exc.code == "INVALID_PARAMS" else 502
            raise api_error(status_code, exc.code, str(exc)) from exc
        finally:
            pipeline.close()
        return {"dry_run": True, "report": report, "calls": list(pipeline.step_calls)}

    def _validate_adopt_tutorials(payload: dict[str, Any]) -> list[dict[str, Any]]:
        """A2 轻校验：新契约（tutorials@v2 输出格式）。"""
        source = str(payload.get("source", "explore")).strip() or "explore"
        if source not in ("explore", "manual"):
            raise api_error(422, "INVALID_PARAMS", "source 必须为 explore（默认）或 manual")
        tutorials = payload.get("tutorials")
        if not isinstance(tutorials, list) or not 1 <= len(tutorials) <= 6:
            raise api_error(422, "INVALID_PARAMS", "tutorials 必须为 1~6 套")
        for i, item in enumerate(tutorials):
            if not isinstance(item, dict):
                raise api_error(422, "INVALID_PARAMS", f"tutorials[{i}] 必须为对象")
            set_no = str(item.get("set_no", "")).strip()
            if not set_no or len(set_no) > 4:
                raise api_error(422, "INVALID_PARAMS", f"tutorials[{i}].set_no 非空且 ≤4")
            name = str(item.get("name", "")).strip()
            if not name or len(name) > 128:
                raise api_error(422, "INVALID_PARAMS", f"tutorials[{i}].name 非空且 ≤128")
            position = str(item.get("position", "")).strip()
            if position not in ("beginner", "intermediate", "advanced", "comprehensive", "elective"):
                raise api_error(422, "INVALID_PARAMS", f"tutorials[{i}].position 值域错误")
            intro = str(item.get("intro", "")).strip()
            if not intro or len(intro) < 120:
                raise api_error(422, "INVALID_PARAMS", f"tutorials[{i}].intro 至少 120 字")
            textbook_ref = item.get("textbook_ref", [])
            if not isinstance(textbook_ref, list) or not textbook_ref:
                raise api_error(422, "INVALID_PARAMS", f"tutorials[{i}].textbook_ref 必须是非空数组")
            exercise_ref = item.get("exercise_ref")
            if exercise_ref is not None and not isinstance(exercise_ref, list):
                raise api_error(422, "INVALID_PARAMS", f"tutorials[{i}].exercise_ref 必须是 null 或数组")
            parallel_ref = item.get("parallel_ref")
            if parallel_ref is not None and not isinstance(parallel_ref, list):
                raise api_error(422, "INVALID_PARAMS", f"tutorials[{i}].parallel_ref 必须是 null 或数组")
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
        except ValueError as exc:
            # 数据文件版显式 knowledge_id/book_id 格式错误（kt-{abbr}-{set_no} / {abbr}-b{NN}）
            raise api_error(422, "INVALID_PARAMS", str(exc)) from exc
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
