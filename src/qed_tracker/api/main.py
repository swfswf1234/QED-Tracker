"""QED-Tracker FastAPI 服务（8901）。

契约（docs/design/tracker-service.md）：
- 只读查询同步返回：健康、搜索、资源、目录、任务列表；
- 写操作提交后台任务，状态 queued→running→succeeded/failed，并发上限 2；
- 同内容（sha256）幂等复用，重复提交不产生重复文件。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any, Literal

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from qed_tracker import __version__
from qed_tracker.api.tasks import TaskManager, TaskStore
from qed_tracker.application import BookService, ResourceService
from qed_tracker.application.papers import PaperService
from qed_tracker.catalog import list_catalogs, load_catalog
from qed_tracker.config import Settings
from qed_tracker.downloader import DownloadManager
from qed_tracker.inventory import Inventory
from qed_tracker.models import Candidate, ResourceKind
from qed_tracker.providers import ArxivProvider, create_book_providers

FRONTEND_ORIGINS = ("http://127.0.0.1:8903", "http://localhost:8903")

# B008：函数调用不得出现在参数默认值中，FastAPI 允许模块级单例。
_EMPTY_BODY: dict[str, Any] = Body(default_factory=dict)


class BookDownloadRequest(BaseModel):
    provider: str
    provider_id: str
    title: str
    authors: list[str] = []
    language: str = ""
    year: str = ""
    page_url: str = ""
    download_url: str
    kind: Literal["book", "exercise"] = "book"


class Application:
    """共享的服务容器：任务执行与只读端点复用同一批资源服务。"""

    def __init__(self, settings: Settings, *, book_providers=None, papers_provider=None, downloader=None):
        self.settings = settings
        inventory = Inventory(settings.data_root)
        downloader = downloader or DownloadManager(proxy=settings.proxy, timeout=settings.timeout_seconds, retries=settings.retries, tls_verify=settings.tls_verify)
        self.resources = ResourceService(inventory, downloader)
        providers = book_providers if book_providers is not None else create_book_providers(
            settings.sources, proxy=settings.proxy, timeout=settings.timeout_seconds, tls_verify=settings.tls_verify
        )
        self.books = BookService(providers, self.resources)
        self.papers = PaperService(papers_provider or ArxivProvider(retries=settings.retries), self.resources)

    def close(self) -> None:
        self.books.close()
        self.papers.close()


def _candidate_dict(candidate: Candidate) -> dict[str, Any]:
    value = asdict(candidate)
    value["availability"] = candidate.availability.value
    value["authors"] = list(candidate.authors)
    value["subjects"] = list(candidate.subjects)
    return value


def _make_download_handler(app: Application):
    def handler(params: dict[str, Any], progress) -> dict[str, Any]:
        progress(10, "解析候选")
        candidate = Candidate(
            provider=params["provider"],
            provider_id=params["provider_id"],
            title=params["title"],
            authors=tuple(params.get("authors", [])),
            language=params.get("language", ""),
            year=params.get("year", ""),
            page_url=params.get("page_url", ""),
            download_url=params["download_url"],
        )
        kind = ResourceKind(params.get("kind", "book"))
        progress(30, "下载并校验")
        record = app.books.download(candidate, kind=kind)
        progress(100, "完成")
        return record.to_dict()

    return handler


def create_app(
    settings: Settings,
    *,
    book_providers=None,
    papers_provider=None,
    downloader=None,
    extra_handlers: dict[str, Any] | None = None,
) -> FastAPI:
    app = Application(settings, book_providers=book_providers, papers_provider=papers_provider, downloader=downloader)
    manager = TaskManager(TaskStore(settings.state_dir / "tasks"), {**{"books/download": _make_download_handler(app)}, **(extra_handlers or {})})

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

    @fastapi_app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @fastapi_app.get("/books/search")
    def books_search(
        q: str = Query(..., min_length=1),
        limit: int = Query(10, ge=1, le=50),
        source: str = "",
    ) -> list[dict[str, Any]]:
        items = app.books.search(q, limit=limit)
        candidates = [item.candidate for item in items if not source or item.candidate.provider == source]
        return [_candidate_dict(item) for item in candidates]

    @fastapi_app.get("/papers/search")
    def papers_search(
        q: str = "",
        category: str = "",
        author: str = "",
        limit: int = Query(10, ge=1, le=50),
    ) -> list[dict[str, Any]]:
        candidates = app.papers.search(q, category=category, author=author, limit=limit)
        return [_candidate_dict(item) for item in candidates]

    @fastapi_app.get("/resources")
    def resources(kind: Literal["book", "exercise", "paper"] | None = None) -> list[dict[str, Any]]:
        return [record.to_dict() for record in app.resources.inventory.list(kind)]

    @fastapi_app.get("/resources/{resource_id}")
    def resource_detail(resource_id: str) -> dict[str, Any]:
        record = app.resources.inventory.get(resource_id)
        if record is None:
            raise HTTPException(status_code=404, detail="资源不存在")
        return record.to_dict()

    @fastapi_app.get("/catalogs")
    def catalogs() -> list[dict[str, str]]:
        return [{"id": catalog_id} for catalog_id in list_catalogs()]

    @fastapi_app.get("/catalogs/{catalog_id}")
    def catalog_detail(catalog_id: str) -> dict[str, Any]:
        try:
            catalog = load_catalog(catalog_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"id": catalog.id, "name": catalog.name, "description": catalog.description, "status": catalog.status, "targets": [asdict(target) for target in catalog.targets]}

    @fastapi_app.get("/tasks")
    def tasks() -> list[dict[str, Any]]:
        return [record.to_dict() for record in manager.list()]

    @fastapi_app.get("/tasks/{task_id}")
    def task_detail(task_id: str) -> dict[str, Any]:
        record = manager.get(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return record.to_dict()

    @fastapi_app.post("/tasks/books/download", status_code=202)
    def submit_book_download(payload: BookDownloadRequest) -> dict[str, str]:
        record = manager.submit("books/download", payload.model_dump())
        return {"task_id": record.task_id}

    @fastapi_app.post("/tasks/{task_type}", status_code=202)
    def submit_task(task_type: str, payload: dict[str, Any] = _EMPTY_BODY) -> dict[str, str]:
        try:
            record = manager.submit(task_type, payload)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"task_id": record.task_id}

    return fastapi_app
