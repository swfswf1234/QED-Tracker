"""QED-Tracker FastAPI 服务（8901）。

契约（docs/design/tracker-service.md）：
- 只读查询同步返回：健康、搜索、资源、目录、任务列表；
- 写操作提交后台任务，状态 queued→running→succeeded/failed，并发上限 2；
- 同内容（sha256）幂等复用，重复提交不产生重复文件。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from qed_tracker import __version__
from qed_tracker.api.tasks import TaskManager, TaskStore
from qed_tracker.application import BookService, ResourceService
from qed_tracker.application.catalog_evaluate import CatalogEvaluator
from qed_tracker.application.papers import PaperService
from qed_tracker.catalog import list_catalogs, load_catalog
from qed_tracker.config import Settings, llm_api_key
from qed_tracker.db.models import DownloadStatus, ResourceStatus
from qed_tracker.db.registry import ResourceRegistry
from qed_tracker.db.repository import InvalidTransition, ResourceRepository
from qed_tracker.db.selection_repository import ThreeTableRepository
from qed_tracker.downloader import DownloadManager
from qed_tracker.inventory import Inventory
from qed_tracker.models import Candidate, CatalogTarget, ResourceKind
from qed_tracker.providers import ArxivProvider, create_book_providers
from qed_tracker.providers.book_advisor import BailianBookAdvisor

FRONTEND_ORIGINS = ("http://127.0.0.1:8903", "http://localhost:8903")

# B008：函数调用不得出现在参数默认值中，FastAPI 允许模块级单例。
_EMPTY_BODY: dict[str, Any] = Body(default_factory=dict)


class BookDownloadRequest(BaseModel):
    resource_id: str


class Application:
    """共享的服务容器：任务执行与只读端点复用同一批资源服务。"""

    def __init__(
        self,
        settings: Settings,
        *,
        book_providers=None,
        papers_provider=None,
        downloader=None,
        repository=None,
        advisor=None,
        three_table_repository=None,
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
        if repository is None and settings.db_configured:
            from qed_tracker.database import create_engine_for, session_factory

            self._db_engine = create_engine_for(settings)
            repository = ResourceRepository(session_factory(self._db_engine))
        self.repository = repository
        self.registry = ResourceRegistry(repository)
        self._three_table_repository = three_table_repository
        if three_table_repository is None and settings.db_configured:
            from qed_tracker.database import session_factory

            self._three_table_repository = ThreeTableRepository(session_factory(self._db_engine))
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


def _row_dict(row) -> dict[str, Any]:
    """MySQL qt_resources 行 → JSON（FastAPI 自动编码 datetime）。"""
    return row.to_dict()


def _require_confirmed(app: Application, resource_id: str) -> None:
    """下载任务提交时同步校验：仅 confirmed 可触发，否则 409。"""
    if app.repository is None:
        raise HTTPException(status_code=409, detail="数据库未配置：下载任务需 qt_resources 行")
    row = app.repository.get(resource_id)
    if row is None:
        raise HTTPException(status_code=409, detail=f"资源不存在：{resource_id}")
    if row.status != ResourceStatus.CONFIRMED.value:
        raise HTTPException(status_code=409, detail=f"仅 confirmed 状态可触发下载，当前：{row.status}")


def _transition(app: Application, resource_id: str, op) -> Any:
    if app.repository is None:
        raise HTTPException(status_code=409, detail="数据库未配置：需 qt_resources 行")
    try:
        return op(app.repository, resource_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _remove_resource_file(app: Application, relative_path: str, sha256: str | None = None) -> None:
    """验收级拒绝硬删文件（含本地清单记录），DB rejected 行保留留痕。"""
    path = (app.resources.inventory.data_root / relative_path).resolve()
    try:
        path.relative_to(app.resources.inventory.data_root)
    except ValueError:
        return  # 越界路径防御：不删除
    if path.is_file():
        path.unlink()
    if sha256:
        app.resources.inventory.remove(sha256)


def _make_download_handler(app: Application):
    def handler(params: dict[str, Any], progress) -> dict[str, Any]:
        if app.repository is None:
            raise RuntimeError("数据库未配置：下载任务需 qt_resources 行")
        progress(5, "校验资源状态")
        row = app.repository.get(params["resource_id"])
        if row is None or row.status != ResourceStatus.CONFIRMED.value:
            raise RuntimeError(f"仅 confirmed 状态可触发下载，当前：{row.status if row else '不存在'}")
        source = row.source or {}
        candidate = Candidate(
            provider=source.get("provider", ""),
            provider_id=source.get("provider_id", ""),
            title=row.title,
            authors=tuple(row.authors or ()),
            language=row.language or "",
            year=row.year or "",
            edition=row.edition or "",
            page_url=source.get("page_url", ""),
            download_url=source.get("download_url", ""),
            file_keywords=tuple(source.get("file_keywords", []) or []),
        )
        if not candidate.download_url:
            progress(12, f"解析下载地址（{candidate.provider}）")
            try:
                candidate = app.books.resolve(candidate)
            except Exception as exc:
                raise RuntimeError(f"来源解析下载地址失败（{candidate.provider}）：{exc}") from exc
            if not candidate.download_url:
                raise RuntimeError("候选缺少 download_url，无法下载")
            app.repository.update_source(row.resource_id, source | {"download_url": candidate.download_url})
        progress(15, f"开始下载：{candidate.title}（{candidate.download_url}）")
        app.repository.start_download(row.resource_id)
        try:
            # 2026-08-09：从 catalog_ref 构造 CatalogTarget，下载落盘到课程目录
            # raw/books/<catalog_id>/<course_id>/（此前落 inbox；命名已带 target_id 前缀防并发冲突）
            ref = row.catalog_ref or {}
            target = CatalogTarget(
                id=ref.get("target_id", ""),
                course_id=ref.get("course_id", ""),
                course_name=ref.get("course_id", ""),
                kind=ResourceKind(row.kind),
                title=row.title,
                authors=tuple(row.authors or ()),
                language=row.language or "",
                edition=row.edition or "",
            )
            record = app.books.download(
                candidate,
                kind=ResourceKind(row.kind),
                catalog_target=target,
                catalog_id=ref.get("catalog_id", ""),
            )
        except Exception:
            app.repository.fail(row.resource_id)
            raise
        progress(70, "校验 PDF 并登记本地清单")
        # 候选行迁移为 sha256:<digest> 并回填；同 sha256 已有行则幂等复用（catalog_ref 保留）
        progress(90, "登记 MySQL 索引（qt_resources）")
        app.repository.complete_download(
            row.resource_id,
            sha256=record.sha256,
            relative_path=record.file["relative_path"],
            page_count=record.file.get("page_count", 0),
        )
        progress(100, "完成")
        return record.to_dict()

    return handler


def _make_evaluate_handler(app: Application):
    def handler(params: dict[str, Any], progress) -> dict[str, Any]:
        if app.repository is None:
            raise RuntimeError("数据库未配置：评估候选需 MySQL qt_resources 落库")
        course = params.get("course_id", "")
        progress(10, "加载冻结目录")
        catalog = load_catalog("math-qe")
        progress(20, "搜索并评估（每个来源逐个重试，最慢可能数分钟）")
        evaluator = CatalogEvaluator(app.books, app.repository, advisor=app.advisor)
        report = evaluator.evaluate(catalog, course=course, progress=lambda pct, msg: progress(pct, msg))
        progress(100, "完成")
        return report

    return handler


def create_app(
    settings: Settings,
    *,
    book_providers=None,
    papers_provider=None,
    downloader=None,
    extra_handlers: dict[str, Any] | None = None,
    repository: ResourceRepository | None = None,
    advisor=None,
    three_table_repository: ThreeTableRepository | None = None,
) -> FastAPI:
    app = Application(
        settings,
        book_providers=book_providers,
        papers_provider=papers_provider,
        downloader=downloader,
        repository=repository,
        advisor=advisor,
        three_table_repository=three_table_repository,
    )
    manager = TaskManager(
        TaskStore(settings.state_dir / "tasks"),
        {
            **{"books/download": _make_download_handler(app), "catalog/evaluate": _make_evaluate_handler(app)},
            **(extra_handlers or {}),
        },
    )

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

    @fastapi_app.get("/api/v1/resources")
    def resources(
        status: str = "",
        course_id: str = "",
        kind: str = "",
        language: str = "",
    ) -> list[dict[str, Any]]:
        """资源清单：MySQL 索引（状态权威）+ 本地清单合并，支持状态/课程/类型/语言过滤。"""
        merged: list[dict[str, Any]] = []
        mysql_shas: set[str] = set()
        if app.repository is not None:
            for row in app.repository.list(
                status=status or None,
                course_id=course_id or None,
                kind=kind or None,
                language=language or None,
            ):
                merged.append(_row_dict(row))
                if row.sha256:
                    mysql_shas.add(row.sha256)
        local_kind = kind or None
        for record in app.resources.inventory.list(local_kind):
            if record.sha256 in mysql_shas:
                continue  # MySQL 状态权威，同 sha256 不重复列出
            if course_id and not (record.catalog_ref or {}).get("course_id") == course_id:
                continue
            if language and record.language != language:
                continue
            value = record.to_dict()
            value["status"] = ResourceStatus.DOWNLOADED.value
            value["review_note"] = ""  # 本地清单行无人工评估建议，统一补空
            merged.append(value)
        # roles 透出：MySQL 行无 roles 列，从本地清单事实源回填（方案 A）
        local_roles = {record.sha256: record.roles for record in app.resources.inventory.list() if record.roles}
        for item in merged:
            digest = (item.get("sha256") or "").removeprefix("sha256:")
            if digest in local_roles:
                item["roles"] = local_roles[digest]
            else:
                item["roles"] = None
        return merged

    @fastapi_app.get("/api/v1/resources/{resource_id}")
    def resource_detail(resource_id: str) -> dict[str, Any]:
        record = app.resources.inventory.get(resource_id)
        if record is not None:
            value = record.to_dict()
            value["status"] = ResourceStatus.DOWNLOADED.value
            return value
        if app.repository is not None:
            row = app.repository.get(resource_id)
            if row is not None:
                return _row_dict(row)
        raise HTTPException(status_code=404, detail="资源不存在")

    @fastapi_app.get("/api/v1/resources/{resource_id}/file")
    def resource_file(resource_id: str) -> FileResponse:
        """PDF 预览流：仅 downloaded/approved 可访问（供 8903 验收台 iframe 内嵌）。"""
        relative = None
        status = None
        if app.repository is not None:
            row = app.repository.get(resource_id)
            if row is not None:
                status = row.status
                relative = row.relative_path
        if status not in (ResourceStatus.DOWNLOADED.value, ResourceStatus.APPROVED.value):
            raise HTTPException(status_code=404, detail="资源文件不可访问（仅下载完成的资源可预览）")
        if not relative:
            raise HTTPException(status_code=404, detail="资源文件缺失")
        path = (app.resources.inventory.data_root / relative).resolve()
        try:
            path.relative_to(app.resources.inventory.data_root)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="资源文件缺失") from exc
        if not path.is_file():
            raise HTTPException(status_code=404, detail="资源文件缺失")
        return FileResponse(path, media_type="application/pdf", filename=path.name)

    @fastapi_app.post("/api/v1/resources/{resource_id}/register")
    def register_resource(resource_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        """人工下载登记（QED-021）：用户按 libgen 等方案下载后把文件放进数据根，
        提交相对路径 → PDF 校验 + SHA-256 去重 → pending_manual → downloaded。"""
        if app.repository is None:
            raise HTTPException(status_code=409, detail="数据库未配置：登记需 qt_resources 行")
        relative = str(payload.get("relative_path", "")).strip()
        if not relative:
            raise HTTPException(status_code=422, detail="必须提供数据根内相对路径（relative_path）")
        row = app.repository.get(resource_id)
        if row is None:
            raise HTTPException(status_code=404, detail="资源不存在")
        path = (app.resources.inventory.data_root / relative).resolve()
        try:
            path.relative_to(app.resources.inventory.data_root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="路径必须在数据根目录内") from exc
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"文件不存在：{relative}")
        try:
            record = app.resources.inventory.register(
                path,
                kind=ResourceKind(row.kind),
                title=row.title,
                authors=row.authors,
                language=row.language,
                year=row.year,
                source=dict(row.source or {}),
            )
        except Exception as exc:  # noqa: BLE001 - PDF 校验失败（含 DownloadError）统一 400
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            final = app.repository.complete_download(
                resource_id,
                sha256=record.sha256,
                relative_path=record.file["relative_path"],
                page_count=record.file["page_count"],
            )
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _row_dict(final)

    @fastapi_app.post("/api/v1/resources/{resource_id}/confirm")
    def confirm_resource(resource_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        note = str(payload.get("note", "")).strip()
        return _row_dict(_transition(app, resource_id, lambda repo, rid: repo.confirm(rid, note=note)))

    @fastapi_app.post("/api/v1/resources/{resource_id}/backup")
    def backup_resource(resource_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        """人工评估「备选」：candidate/pending_manual → backup（不下载，可转正/放弃）。"""
        note = str(payload.get("note", "")).strip()
        return _row_dict(_transition(app, resource_id, lambda repo, rid: repo.mark_backup(rid, note=note)))

    @fastapi_app.post("/api/v1/resources/{resource_id}/approve")
    def approve_resource(resource_id: str) -> dict[str, Any]:
        return _row_dict(_transition(app, resource_id, lambda repo, rid: repo.approve(rid)))

    @fastapi_app.post("/api/v1/resources/{resource_id}/reject")
    def reject_resource(resource_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        reason = str(payload.get("reason", "")).strip()
        if not reason:
            raise HTTPException(status_code=422, detail="拒绝必须提供原因（reason）")
        if app.repository is None:
            raise HTTPException(status_code=409, detail="数据库未配置：拒绝留痕需 qt_resources 行")
        row = app.repository.get(resource_id)
        if row is None:
            raise HTTPException(status_code=404, detail="资源不存在")
        if row.status == ResourceStatus.DOWNLOADED.value and row.relative_path:
            # 验收级拒绝：硬删文件，DB 记录保留留痕
            _remove_resource_file(app, row.relative_path, row.sha256)
        try:
            note = str(payload.get("note", "")).strip()
            return _row_dict(app.repository.reject(resource_id, reason=reason, by="web", note=note))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

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

    # ---------------- 三表端点（QED-028/029：qt_selections / qt_downloads / qt_sources） ----------------
    # 契约：根仓库 downloads-three-table-model.md §3.1 + docs/design/three-table-schema.md。
    # 彻底隐藏语义在数据层实现：rejected/superseded（表1）、rejected/failed（表2）默认过滤。

    def _tt(app: Application) -> ThreeTableRepository:
        if app._three_table_repository is None:
            raise HTTPException(status_code=409, detail="数据库未配置：三表端点需 qt_selections 行")
        return app._three_table_repository

    def _selection_view(repo: ThreeTableRepository, row) -> dict[str, Any]:
        value = row.to_dict()
        downloads = repo.list_downloads(row.selection_id)
        value["downloads"] = [d.to_dict() for d in downloads]
        value["download_stats"] = {
            "total": len(downloads),
            "downloaded": sum(1 for d in downloads if d.status == DownloadStatus.DOWNLOADED.value),
            "approved": sum(1 for d in downloads if d.status == DownloadStatus.APPROVED.value),
        }
        return value

    def _require_selection(repo: ThreeTableRepository, selection_id: str):
        row = repo.get_selection(selection_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"选课条目不存在：{selection_id}")
        return row

    def _selection_transition(selection_id: str, op) -> dict[str, Any]:
        repo = _tt(app)
        try:
            row = op(repo, selection_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return row.to_dict()

    @fastapi_app.get("/api/v1/selections")
    def selections(
        course_id: str = "",
        status: str = "",
    ) -> list[dict[str, Any]]:
        """表1 列表：默认过滤 rejected/superseded；显式 status 查询同样受隐藏约束。"""
        return [
            _selection_view(_tt(app), row)
            for row in _tt(app).list_selections(course_id=course_id or None, status=status or None)
        ]

    @fastapi_app.get("/api/v1/selections/{selection_id}")
    def selection_detail(selection_id: str) -> dict[str, Any]:
        repo = _tt(app)
        _require_selection(repo, selection_id)
        return _selection_view(repo, repo.get_selection(selection_id))

    @fastapi_app.post("/api/v1/selections/{selection_id}/confirm")
    def selection_confirm(selection_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        note = str(payload.get("note", "")).strip()
        return _selection_transition(selection_id, lambda repo, sid: repo.confirm_selection(sid, note=note))

    @fastapi_app.post("/api/v1/selections/{selection_id}/backup")
    def selection_backup(selection_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        note = str(payload.get("note", "")).strip()
        return _selection_transition(selection_id, lambda repo, sid: repo.backup_selection(sid, note=note))

    @fastapi_app.post("/api/v1/selections/{selection_id}/reject")
    def selection_reject(selection_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        reason = str(payload.get("reason", "")).strip()
        if not reason:
            raise HTTPException(status_code=422, detail="拒绝必须提供原因（reason）")
        return _selection_transition(
            selection_id, lambda repo, sid: repo.reject_selection(sid, reason=reason, by="web")
        )

    @fastapi_app.post("/api/v1/selections/{selection_id}/supersede")
    def selection_supersede(selection_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        reason = str(payload.get("reason", "")).strip()
        if not reason:
            raise HTTPException(status_code=422, detail="过时必须提供原因（reason）")
        return _selection_transition(
            selection_id, lambda repo, sid: repo.supersede_selection(sid, reason=reason, by="web")
        )

    @fastapi_app.get("/api/v1/resources/{selection_id}/downloads")
    def selection_downloads(selection_id: str) -> list[dict[str, Any]]:
        """表2 册明细列表：默认过滤 rejected/failed（彻底隐藏）。"""
        return [d.to_dict() for d in _tt(app).list_downloads(selection_id)]

    @fastapi_app.post("/api/v1/downloads")
    def create_download(payload: dict[str, Any]) -> dict[str, Any]:
        """新建表2 候选册（先登记再下载，D7）：candidate 态。roles 省略时继承表1。"""
        selection_id = str(payload.get("selection_id", "")).strip()
        if not selection_id:
            raise HTTPException(status_code=422, detail="必须提供 selection_id")
        vol = str(payload.get("vol", "")).strip()
        file_hint = str(payload.get("file_hint", "")).strip()
        roles = payload.get("roles")
        repo = _tt(app)
        _require_selection(repo, selection_id)
        try:
            row = repo.create_download(selection_id, vol=vol, file_hint=file_hint, roles=roles)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return row.to_dict()

    @fastapi_app.get("/api/v1/downloads/{download_id}/sources")
    def download_sources(download_id: str) -> list[dict[str, Any]]:
        repo = _tt(app)
        if repo.get_download(download_id, include_hidden=True) is None:
            raise HTTPException(status_code=404, detail=f"下载明细不存在：{download_id}")
        return [s.to_dict() for s in repo.list_sources(download_id)]

    @fastapi_app.post("/api/v1/downloads/{download_id}/register")
    def download_register(download_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        """人工下载登记（QED-021 延续 → 适配表2）：candidate → downloaded 直转（D7 先登记再下载）。"""
        repo = _tt(app)
        row = repo.get_download(download_id, include_hidden=True)
        if row is None:
            raise HTTPException(status_code=404, detail=f"下载明细不存在：{download_id}")
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
        kind = ResourceKind.BOOK
        if row.roles:
            if "exercises" in row.roles:
                kind = ResourceKind.EXERCISE
            elif "solutions" in row.roles:
                kind = ResourceKind.SUPPLEMENT
        selection = repo.get_selection(row.selection_id)
        title = f"{selection.title} {row.vol or ''}".strip()
        try:
            record = app.resources.inventory.register(path, kind=kind, title=title, source={"channel": "manual"})
        except Exception as exc:  # noqa: BLE001 - PDF 校验失败统一 400
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            final = repo.complete_download(
                download_id,
                sha256=record.sha256,
                relative_path=record.file["relative_path"],
                page_count=record.file["page_count"],
            )
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return final.to_dict()

    @fastapi_app.post("/api/v1/downloads/{download_id}/approve")
    def download_approve(download_id: str) -> dict[str, Any]:
        repo = _tt(app)
        try:
            row = repo.approve_download(download_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return row.to_dict()

    @fastapi_app.post("/api/v1/downloads/{download_id}/reject")
    def download_reject(download_id: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, Any]:
        reason = str(payload.get("reason", "")).strip()
        if not reason:
            raise HTTPException(status_code=422, detail="拒绝必须提供原因（reason）")
        repo = _tt(app)
        try:
            row = repo.reject_download(download_id, reason=reason, by="web")
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

    @fastapi_app.post("/api/v1/tasks/books/download", status_code=202)
    def submit_book_download(payload: BookDownloadRequest) -> dict[str, str]:
        _require_confirmed(app, payload.resource_id)
        record = manager.submit("books/download", payload.model_dump())
        return {"task_id": record.task_id}

    @fastapi_app.post("/api/v1/tasks/catalog/evaluate", status_code=202)
    def submit_catalog_evaluate(payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, str]:
        record = manager.submit("catalog/evaluate", payload)
        return {"task_id": record.task_id}

    @fastapi_app.post("/api/v1/tasks/{task_type}", status_code=202)
    def submit_task(task_type: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, str]:
        try:
            record = manager.submit(task_type, payload)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"task_id": record.task_id}

    return fastapi_app
