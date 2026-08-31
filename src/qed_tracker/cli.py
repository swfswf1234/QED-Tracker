"""`qed-tracker` 统一命令行入口。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qed_tracker.db.knowledge_repository import KnowledgeRepository

import uvicorn

from qed_tracker import __version__
from qed_tracker.application import BookService, ResourceService, attempts_markdown
from qed_tracker.application.papers import PaperService
from qed_tracker.axiom import AxiomClient
from qed_tracker.catalog import list_catalogs, load_catalog
from qed_tracker.config import Settings, llm_api_key, load_settings
from qed_tracker.courses import Curriculum
from qed_tracker.database import upgrade_database
from qed_tracker.downloader import DownloadManager
from qed_tracker.inventory import Inventory, raw_course_dir, raw_general_dir
from qed_tracker.models import Availability, Candidate, ResourceKind
from qed_tracker.profiles import list_paper_profiles, load_paper_profile
from qed_tracker.providers import ArxivProvider, BailianPaperAdvisor, create_book_providers


def _add_limit(parser: argparse.ArgumentParser, default: int = 10) -> None:
    parser.add_argument("--limit", type=int, default=default, help="每个来源的最大结果数")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qed-tracker", description="教材、习题集与 arXiv 论文下载工具")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--data-root", type=Path, help="覆盖数据根目录")
    parser.add_argument("--proxy", help="覆盖 HTTP 代理")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    commands = parser.add_subparsers(dest="command", required=True)

    books = commands.add_parser("books", help="教材和习题集")
    books_commands = books.add_subparsers(dest="books_command", required=True)
    books_get = books_commands.add_parser("get", help="搜索，并在显式选择时下载")
    books_get.add_argument("query")
    books_get.add_argument("--source", action="append", dest="sources")
    books_get.add_argument("--pick", type=int, help="直接选择搜索结果序号")
    books_get.add_argument("--kind", choices=["book", "exercise"], default="book")
    _add_limit(books_get)
    books_url = books_commands.add_parser("fetch-url", help="从明确的 PDF URL 下载")
    books_url.add_argument("url")
    books_url.add_argument("--title", required=True)
    books_url.add_argument("--author", action="append", default=[])
    books_url.add_argument("--language", default="")
    books_url.add_argument("--kind", choices=["book", "exercise"], default="book")
    books_import = books_commands.add_parser(
        "import", help="手动导入本地 PDF（外部路径 → 校验 → 拷入数据根 → 登记 downloaded）"
    )
    books_import.add_argument("book_id", help="书行标识（qt_books.book_id）")
    books_import.add_argument("file_path", type=Path, help="本地 PDF 路径（可在数据根外）")
    books_import.add_argument("--target", dest="target_path", default="",
                              help="期望落盘相对路径（raw/<domain>/<course>/<书名>.pdf，自动补 _<sha8>）")
    books_import.add_argument("--url", dest="tracker_url", help="覆盖 8901 地址（默认取配置 tracker_url）")

    papers = commands.add_parser("papers", help="arXiv 论文")
    paper_commands = papers.add_subparsers(dest="papers_command", required=True)
    paper_search = paper_commands.add_parser("search", help="按关键词、分类或作者搜索")
    paper_search.add_argument("query", nargs="?", default="")
    paper_search.add_argument("--category", default="")
    paper_search.add_argument("--author", default="")
    paper_search.add_argument("--download", type=int, action="append", default=[], metavar="INDEX")
    _add_limit(paper_search)
    paper_get = paper_commands.add_parser("get", help="按 arXiv ID 或 URL 下载")
    paper_get.add_argument("identifiers", nargs="+")
    paper_recommend = paper_commands.add_parser("recommend", help="用百炼规划检索并生成论文选择报告")
    paper_recommend.add_argument("goal", nargs="?", default="", help="本次临时研究目标")
    paper_recommend.add_argument("--profile", default="llm-engineering", help="内置档案名或 JSON 路径")
    paper_recommend.add_argument("--category", action="append", dest="categories", default=[])
    paper_recommend.add_argument("--top", type=int, default=10, help="最多推荐数量")
    _add_limit(paper_recommend)
    paper_profiles = paper_commands.add_parser("profiles", help="查看论文目标档案")
    paper_profile_commands = paper_profiles.add_subparsers(dest="profiles_command", required=True)
    paper_profile_commands.add_parser("list", help="列出内置档案")
    paper_profile_show = paper_profile_commands.add_parser("show", help="显示档案")
    paper_profile_show.add_argument("profile")
    paper_selections = paper_commands.add_parser("selections", help="查看选择报告或显式下载")
    paper_selection_commands = paper_selections.add_subparsers(dest="selections_command", required=True)
    paper_selection_commands.add_parser("list", help="列出选择报告")
    paper_selection_show = paper_selection_commands.add_parser("show", help="显示选择报告")
    paper_selection_show.add_argument("selection_id")
    paper_selection_download = paper_selection_commands.add_parser("download", help="从固定选择报告下载推荐论文")
    paper_selection_download.add_argument("selection_id")
    paper_selection_download.add_argument("--pick", type=int, action="append", required=True)

    catalog = commands.add_parser("catalog", help="冻结下载目录")
    catalog_commands = catalog.add_subparsers(dest="catalog_command", required=True)
    catalog_commands.add_parser("list", help="列出内置目录")
    catalog_show = catalog_commands.add_parser("show", help="显示目录目标")
    catalog_show.add_argument("catalog_id")
    catalog_run = catalog_commands.add_parser("run", help="严格匹配目录目标")
    catalog_run.add_argument("catalog_id")
    catalog_run.add_argument("--course", default="")
    catalog_run.add_argument("--download", action="store_true", help="下载严格匹配项；默认只预览")
    catalog_run.add_argument("--report", type=Path)
    _add_limit(catalog_run, 8)

    inventory = commands.add_parser("inventory", help="本地 PDF 清单")
    inventory_commands = inventory.add_subparsers(dest="inventory_command", required=True)
    inventory_scan = inventory_commands.add_parser("scan", help="原地登记数据根内已有 PDF")
    inventory_scan.add_argument("roots", type=Path, nargs="*")
    inventory_list = inventory_commands.add_parser("list", help="列出资源")
    inventory_list.add_argument("--kind", choices=[kind.value for kind in ResourceKind])
    inventory_commands.add_parser("verify", help="校验文件与清单")

    axiom = commands.add_parser("axiom", help="交付给 Axiom-Flow")
    axiom_commands = axiom.add_subparsers(dest="axiom_command", required=True)
    axiom_push = axiom_commands.add_parser("push", help="显式上传一个已登记 PDF")
    axiom_push.add_argument("resource")
    axiom_push.add_argument("--url", dest="axiom_url")
    axiom_push.add_argument("--parse", action="store_true")
    axiom_push.add_argument("--page-start", type=int)
    axiom_push.add_argument("--page-end", type=int)

    config = commands.add_parser("config", help="生效配置")
    config_commands = config.add_subparsers(dest="config_command", required=True)
    config_commands.add_parser("show", help="显示生效配置")

    courses = commands.add_parser("courses", help="学科课程体系")
    courses_commands = courses.add_subparsers(dest="courses_command", required=True)
    courses_commands.add_parser("list", help="列出学科课程体系")
    courses_show = courses_commands.add_parser("show", help="查看单门课（含前置/关联目标）")
    courses_show.add_argument("course_id")

    domains = commands.add_parser("domains", help="领域知识手动导入")
    domains_commands = domains.add_subparsers(dest="domains_command", required=True)
    domains_import = domains_commands.add_parser("import", help="导入领域标准答案 JSON（docs/knowledge/<domain>.json）")
    domains_import.add_argument("path", type=Path, help="领域 JSON 文件路径")
    domains_import.add_argument("--url", dest="tracker_url", help="覆盖 8901 地址（默认取配置 tracker_url）")

    knowledge = commands.add_parser("knowledge", help="课程知识手动导入")
    knowledge_commands = knowledge.add_subparsers(dest="knowledge_command", required=True)
    knowledge_import = knowledge_commands.add_parser(
        "import",
        help="导入课程标准答案 JSON（docs/knowledge/<domain>/<course>.json）→ 导入即确认+建候选册",
    )
    knowledge_import.add_argument("path", type=Path, help="课程 JSON 文件路径")
    knowledge_import.add_argument("--url", dest="tracker_url", help="覆盖 8901 地址（默认取配置 tracker_url）")

    mainline = commands.add_parser("mainline", help="主链路教材条目（课程梳理→下载→验收）")
    mainline_commands = mainline.add_subparsers(dest="mainline_command", required=True)
    mainline_list = mainline_commands.add_parser("list", help="列出课程教材条目")
    mainline_list.add_argument("--course", required=True)
    mainline_new = mainline_commands.add_parser("new", help="新建条目（LLM 预填评价）")
    mainline_new.add_argument("--course", required=True)
    mainline_new.add_argument("--title", required=True)
    mainline_new.add_argument("--author", action="append", default=[])
    mainline_new.add_argument(
        "--set-no", default="",
        help="套标记（1~4 中文套 / en 英文对照套）：有值时 name 按「教程{set_no}：书名（作者）」规范生成",
    )
    mainline_review = mainline_commands.add_parser("review", help="人工评审定稿（版本/简介）")
    mainline_review.add_argument("knowledge_id")
    mainline_review.add_argument("--intro", help="教材简介（缺省用模板占位，人工审定）")
    mainline_review.add_argument("--version", help="教材版本号（如 第8版）")
    mainline_review.add_argument(
        "--title", help="教材原始书名（缺省从 name 剥离「教程{set_no}：」前缀与（作者）后缀回退）"
    )
    mainline_review.add_argument("--author", action="append", default=[], help="教材作者（可重复）")
    mainline_download = mainline_commands.add_parser("download", help="触发渠道下载")
    mainline_download.add_argument("knowledge_id")
    mainline_verify = mainline_commands.add_parser("verify", help="校验已下载文件")
    mainline_verify.add_argument("knowledge_id")
    mainline_verify.add_argument("--book", help="指定书行 book_id（缺省取首个已下载书行）")
    mainline_approve = mainline_commands.add_parser("approve", help="验收通过 → 移交根仓库")
    mainline_approve.add_argument("knowledge_id")
    mainline_approve.add_argument("--book", help="指定书行 book_id（缺省取首个未移交的 verified 书行）")
    mainline_reject = mainline_commands.add_parser("reject", help="验收不通过（填原因）")
    mainline_reject.add_argument("knowledge_id")
    mainline_reject.add_argument("--reason", required=True)
    mainline_commands.add_parser("channels", help="渠道有效性汇总")

    migrate = commands.add_parser("migrate", help="一次性存量迁移（math.json + 三表 → 五表；幂等可重放）")
    migrate.add_argument("--drop-legacy", action="store_true", help="迁移完成后删除旧表（qt_selections/qt_downloads）")

    serve = commands.add_parser("serve", help="启动工作台 API 服务（8901）")
    serve.add_argument("--host", default="127.0.0.1", help="监听地址")
    serve.add_argument("--port", type=int, default=None, help="监听端口（默认取配置 port）")
    return parser


def _settings(args) -> Settings:
    return load_settings(data_root=args.data_root, proxy=args.proxy)


def _curriculum_repository(settings: Settings) -> KnowledgeRepository | None:
    if not settings.db_configured:
        return None
    from qed_tracker.database import create_engine_for, session_factory
    from qed_tracker.db.knowledge_repository import KnowledgeRepository

    engine = create_engine_for(settings)
    return KnowledgeRepository(session_factory(engine))


def _print(value, json_output: bool = False) -> None:
    if json_output:
        print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
    else:
        print(value)


def _candidate_dict(candidate: Candidate) -> dict:
    value = asdict(candidate)
    value["availability"] = candidate.availability.value
    value["authors"] = list(candidate.authors)
    return value


def _display_candidates(candidates: list[Candidate]) -> None:
    for index, item in enumerate(candidates, 1):
        authors = ", ".join(item.authors) or "-"
        print(f"[{index}] [{item.provider}] [{item.availability.value}] {item.title}")
        print(f"    {authors} | {item.language or '-'} | {item.year or '-'}")


def _book_service(settings: Settings, names: tuple[str, ...] | None = None) -> BookService:
    providers = create_book_providers(
        names or settings.sources,
        proxy=settings.proxy,
        timeout=settings.timeout_seconds,
        tls_verify=settings.tls_verify,
    )
    downloader = DownloadManager(
        proxy=settings.proxy, timeout=settings.timeout_seconds, retries=settings.retries, tls_verify=settings.tls_verify
    )
    return BookService(providers, ResourceService(Inventory(settings.data_root), downloader))


def _books_import(args, settings: Settings) -> int:
    """手动下载导入：外部 PDF → 经 8901 POST /books/{id}/import 登记（D3/D4；无离线直连）。"""
    import httpx

    base_url = (args.tracker_url or settings.tracker_url).rstrip("/")
    payload: dict = {"file_path": str(args.file_path)}
    if getattr(args, "target_path", ""):
        payload["target_path"] = args.target_path
    try:
        response = httpx.post(f"{base_url}/api/v1/books/{args.book_id}/import", json=payload, timeout=120.0)
    except httpx.HTTPError as exc:
        _print({"error": f"8901 服务不可达（{base_url}）：{exc}；请先启动 qed-tracker serve"}, True) if args.json else print(
            f"ERROR: 8901 服务不可达（{base_url}）：{exc}；请先启动 qed-tracker serve", file=sys.stderr
        )
        return 6
    if response.status_code >= 400:
        detail = response.json().get("detail", response.text)
        _print({"error": detail}, True) if args.json else print(f"ERROR: {detail}", file=sys.stderr)
        return 2
    _print(response.json(), args.json)
    return 0


def _paper_service(settings: Settings, *, with_advisor: bool = False) -> PaperService:
    provider = ArxivProvider(retries=settings.retries)
    manager = DownloadManager(
        proxy=settings.proxy,
        timeout=max(settings.timeout_seconds, 120),
        retries=settings.retries,
        tls_verify=settings.tls_verify,
    )
    resources = ResourceService(Inventory(settings.data_root), manager)
    advisor = None
    if with_advisor:
        advisor = BailianPaperAdvisor(
            api_key=llm_api_key(),
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            call_budget=settings.llm_call_budget,
            max_tokens=settings.llm_max_tokens,
            api_select=settings.api_select,
            gateway_url=settings.llm_gateway_url,
            engine=_llm_call_engine(settings),
        )
    return PaperService(provider, resources, advisor=advisor)


def _display_selection(report: dict) -> None:
    print(f"Selection: {report['selection_id']} | {report['status']}")
    for item in report.get("assessments", []):
        candidate = item["candidate"]
        assessment = item["assessment"]
        marker = "RECOMMEND" if item.get("recommended") else "REVIEW"
        print(f"[{item['rank']}] [{marker}] [{item['score']}] {candidate['title']}")
        print(f"    {candidate['identifiers'].get('arxiv', '-')} | {assessment['reason']}")


def _books(args, settings: Settings) -> int:
    inventory = Inventory(settings.data_root)
    if args.books_command == "import":
        return _books_import(args, settings)
    if args.books_command == "fetch-url":
        manager = DownloadManager(
            proxy=settings.proxy,
            timeout=settings.timeout_seconds,
            retries=settings.retries,
            tls_verify=settings.tls_verify,
        )
        resources = ResourceService(inventory, manager)
        try:
            candidate = Candidate(
                "url", args.url, args.title, tuple(args.author), args.language, page_url=args.url, download_url=args.url
            )
            record = resources.download_candidate(
                candidate, kind=ResourceKind(args.kind), destination_dir=raw_general_dir(settings.data_root)
            )
            _print(record.to_dict(), args.json)
            return 0
        finally:
            resources.close()
    try:
        service = _book_service(settings, tuple(args.sources) if args.sources else None)
    except ValueError as exc:
        _print({"error": str(exc)}, True) if args.json else print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    try:
        ranked = service.search(args.query, limit=args.limit)
        candidates = [item.candidate for item in ranked]
        for name, error in service.failures:
            print(f"WARN {name}: {error}", file=sys.stderr)
        if not candidates:
            print("没有搜索结果", file=sys.stderr)
            return 3
        if args.pick is None:
            _print([_candidate_dict(item) for item in candidates], True) if args.json else _display_candidates(
                candidates
            )
            return 0
        pick = args.pick
        if pick < 1 or pick > len(candidates):
            print("选择序号超出范围", file=sys.stderr)
            return 2
        candidate = candidates[pick - 1]
        if candidate.availability != Availability.DOWNLOADABLE:
            print("该结果只有元数据，不能直接下载", file=sys.stderr)
            return 3
        record = service.download(candidate, kind=ResourceKind(args.kind))
        _print(record.to_dict(), args.json)
        return 0
    finally:
        service.close()


def _papers(args, settings: Settings) -> int:
    if args.papers_command == "profiles":
        try:
            if args.profiles_command == "list":
                _print(list(list_paper_profiles()), args.json)
                return 0
            profile = load_paper_profile(args.profile)
            _print(asdict(profile), True) if args.json else print(
                json.dumps(asdict(profile), ensure_ascii=False, indent=2)
            )
            return 0
        except ValueError as exc:
            _print({"error": str(exc)}, True) if args.json else print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    service = _paper_service(settings, with_advisor=args.papers_command == "recommend")
    try:
        if args.papers_command == "selections":
            if args.selections_command == "list":
                reports = service.list_selections()
                summaries = [
                    {
                        "selection_id": item["selection_id"],
                        "status": item["status"],
                        "created_at": item["created_at"],
                        "profile": item["profile"]["id"],
                    }
                    for item in reports
                ]
                _print(summaries, args.json) if args.json else print(
                    "\n".join(f"{item['selection_id']} | {item['status']} | {item['profile']}" for item in summaries)
                )
                return 0
            if args.selections_command == "show":
                report = service.get_selection(args.selection_id)
                _print(report, True) if args.json else _display_selection(report)
                return 0
            report, failures = service.download_selection(args.selection_id, args.pick)
            _print(report, True) if args.json else _display_selection(report)
            if failures == len(set(args.pick)):
                return 5
            return 4 if failures else 0
        if args.papers_command == "recommend":
            profile = load_paper_profile(args.profile)
            report = service.recommend(
                profile, goal=args.goal, categories=args.categories, limit=args.limit, top=args.top
            )
            _print(report, True) if args.json else _display_selection(report)
            return 0 if report["status"] == "ranked" else 3
        if args.papers_command == "get":
            candidates = service.get(args.identifiers)
            picks = range(len(candidates))
        else:
            candidates = service.search(args.query, category=args.category, author=args.author, limit=args.limit)
            if args.json and not args.download:
                _print([_candidate_dict(item) for item in candidates], True)
            elif not args.download:
                _display_candidates(candidates)
            picks = [index - 1 for index in args.download]
        records = []
        for index in picks:
            if index < 0 or index >= len(candidates):
                raise ValueError(f"论文序号超出范围：{index + 1}")
            records.append(service.download(candidates[index]))
        if records:
            _print([record.to_dict() for record in records], args.json)
        return 0 if candidates else 3
    except ValueError as exc:
        _print({"error": str(exc)}, True) if args.json else print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    finally:
        service.close()


def _catalog(args, settings: Settings) -> int:
    if args.catalog_command == "list":
        _print(list(list_catalogs()), args.json)
        return 0
    catalog = load_catalog(args.catalog_id)
    if args.catalog_command == "show":
        value = {
            "id": catalog.id,
            "name": catalog.name,
            "description": catalog.description,
            "status": catalog.status,
            "targets": [asdict(target) for target in catalog.targets],
        }
        _print(value, True) if args.json else print(
            "\n".join(
                f"{target.id}: {target.course_name} | {target.kind.value} | {target.title}"
                for target in catalog.targets
            )
        )
        return 0
    try:
        service = _book_service(settings)
    except ValueError as exc:
        _print({"error": str(exc)}, True) if args.json else print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    try:
        attempts = service.run_catalog(catalog, course=args.course, download=args.download, limit=args.limit)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(attempts_markdown(catalog, attempts), encoding="utf-8")
        if args.json:
            _print(
                [
                    {
                        "target": asdict(item.target),
                        "status": item.status,
                        "reason": item.reason,
                        "resource": item.record.to_dict() if item.record else None,
                    }
                    for item in attempts
                ],
                True,
            )
        else:
            for item in attempts:
                print(f"[{item.status}] {item.target.id} | {item.target.title} | {item.reason}")
        return 4 if any(item.status == "FAILED" for item in attempts) else 0
    finally:
        service.close()


def _inventory(args, settings: Settings) -> int:
    inventory = Inventory(settings.data_root)
    if args.inventory_command == "list":
        records = inventory.list(args.kind)
        _print([record.to_dict() for record in records], args.json) if args.json else print(
            "\n".join(
                f"{record.resource_id} | {record.kind} | {record.title} | {record.file['relative_path']}"
                for record in records
            )
        )
        return 0
    if args.inventory_command == "scan":
        roots = args.roots or [settings.data_root]
        records, errors = inventory.scan(roots)
        value = {"registered": len(records), "errors": [{"path": str(path), "error": error} for path, error in errors]}
        _print(value, args.json)
        return 4 if errors else 0
    if args.inventory_command == "verify":
        results = inventory.verify()
        _print(
            [{"resource_id": record.resource_id, "status": status} for record, status in results], True
        ) if args.json else print(
            "\n".join(f"[{status}] {record.resource_id} {record.title}" for record, status in results)
        )
        return 4 if any(status != "ok" for _, status in results) else 0
    raise ValueError(f"未知 inventory 命令：{args.inventory_command}")


def _axiom(args, settings: Settings) -> int:
    if (args.page_start is not None or args.page_end is not None) and not args.parse:
        raise ValueError("--page-start/--page-end 只能与 --parse 一起使用")
    if args.page_start is not None and args.page_start < 1:
        raise ValueError("--page-start 必须大于等于 1")
    if args.page_end is not None and args.page_start is not None and args.page_end < args.page_start:
        raise ValueError("--page-end 不能小于 --page-start")
    inventory = Inventory(settings.data_root)
    resource = inventory.get(args.resource)
    if resource is None:
        path = Path(args.resource)
        if not path.is_absolute():
            path = settings.data_root / path
        resource = inventory.register(path, kind=ResourceKind.BOOK, title=path.stem)
    client = AxiomClient(
        args.axiom_url or settings.axiom_url, timeout=max(settings.timeout_seconds, 120), tls_verify=settings.tls_verify
    )
    try:
        result = client.push(resource, inventory, parse=args.parse, page_start=args.page_start, page_end=args.page_end)
        _print(result, True if args.json else False)
        return 0
    finally:
        client.close()


def _config(args, settings: Settings) -> int:
    if args.config_command == "show":
        _print(
            {
                "data_root": str(settings.data_root),
                "proxy": settings.proxy,
                "timeout_seconds": settings.timeout_seconds,
                "retries": settings.retries,
                "sources": list(settings.sources),
                "axiom_url": settings.axiom_url,
                "tls_verify": settings.tls_verify,
                "llm_model": settings.llm_model,
                "llm_base_url": settings.llm_base_url,
                "llm_timeout_seconds": settings.llm_timeout_seconds,
                "llm_call_budget": settings.llm_call_budget,
                "llm_max_tokens": settings.llm_max_tokens,
                "port": settings.port,
                "tracker_url": settings.tracker_url,
                "db_host": settings.db_host,
                "db_port": settings.db_port,
                "db_name": settings.db_name,
                "db_user": settings.db_user,
                "db_configured": settings.db_configured,
            },
            True,
        )
        return 0
    raise ValueError(f"未知 config 命令：{args.config_command}")


def _courses(args, settings: Settings) -> int:
    from qed_tracker.courses import list_courses, set_repository

    repo = _curriculum_repository(settings)
    if repo is None:
        _print({"error": "数据库未配置：课程体系读取需 qed_course 表"}, True) if args.json else print(
            "ERROR: 数据库未配置：课程体系读取需 qed_course 表", file=sys.stderr
        )
        return 2
    set_repository(repo)

    if args.courses_command == "list":
        subjects = list_courses()
        if args.json:
            _print({"subjects": list(subjects)}, True)
        else:
            for subject in subjects:
                print(subject)
        return 0
    try:
        curriculum = _load_curriculum(args.course_id)
    except ValueError as exc:
        _print({"error": str(exc)}, True) if args.json else print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        _print(
            {
                "subject": curriculum.subject,
                "name": curriculum.name,
                "description": curriculum.description,
                "stages": list(curriculum.stages),
                "courses": [asdict(c) for c in curriculum.courses],
            },
            True,
        )
    else:
        print(f"{curriculum.name}（{curriculum.subject}）：{curriculum.description}")
        for course in curriculum.courses:
            prefix = " " if course.prerequisites else "*"
            print(
                f"{prefix} {course.course_id} {course.name} [{course.stage}] 前置: {', '.join(course.prerequisites) or '-'}"
            )
    return 0


def _load_curriculum(subject_or_course_id: str) -> Curriculum:
    """按学科名或课程 ID 定位课程体系（课程 ID 需在某个学科内解析）。"""
    from qed_tracker.courses import list_courses, load_course

    try:
        return load_course(subject_or_course_id)
    except ValueError:
        for subject in list_courses():
            curriculum = load_course(subject)
            if any(course.course_id == subject_or_course_id for course in curriculum.courses):
                return curriculum
        raise ValueError(f"未知学科课程体系：{subject_or_course_id}") from None


def _domains(args, settings: Settings) -> int:
    """手动领域知识导入：本地校验 → 经 8901 API 写入共享表（D4，D10：无离线直连）。"""
    import httpx

    from qed_tracker.application.knowledge_import import KnowledgeImportError, validate_domain

    try:
        with open(args.path, encoding="utf-8") as stream:
            data = json.load(stream)
    except OSError as exc:
        _print({"error": f"文件不可读：{args.path}（{exc}）"}, True) if args.json else print(
            f"ERROR: 文件不可读：{args.path}（{exc}）", file=sys.stderr
        )
        return 2
    except json.JSONDecodeError as exc:
        _print({"error": f"JSON 解析失败：{exc}"}, True) if args.json else print(
            f"ERROR: JSON 解析失败：{exc}", file=sys.stderr
        )
        return 2
    try:
        validate_domain(data)
    except KnowledgeImportError as exc:
        _print({"error": f"校验失败：{exc}"}, True) if args.json else print(
            f"ERROR: 校验失败：{exc}", file=sys.stderr
        )
        return 2

    base_url = (args.tracker_url or settings.tracker_url).rstrip("/")
    try:
        response = httpx.post(
            f"{base_url}/api/v1/domains/import",
            json={"domain": data},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        _print({"error": f"8901 服务不可达（{base_url}）：{exc}；请先启动 qed-tracker serve"}, True) if args.json else print(
            f"ERROR: 8901 服务不可达（{base_url}）：{exc}；请先启动 qed-tracker serve", file=sys.stderr
        )
        return 6
    if response.status_code >= 400:
        detail = response.json().get("detail", response.text)
        _print({"error": detail}, True) if args.json else print(f"ERROR: {detail}", file=sys.stderr)
        return 2
    _print(response.json(), args.json)
    return 0


def _ref_book_payload(knowledge_id: str, kind: str, ref: dict) -> dict:
    """课程 JSON 的 textbook/exercise ref → POST /books 幂等建册 payload。"""
    return {
        "knowledge_id": knowledge_id,
        "kind": kind,
        "roles": ref.get("roles") or (["textbook"] if kind == "textbook" else ["exercises"]),
        "title": str(ref.get("title", "")).strip(),
        "part": str(ref.get("part", "")),
        "authors": ref.get("authors") or [],
        "version": ref.get("version") or {},
        "language": str(ref.get("language", "")),
    }


def _knowledge_import(args, settings: Settings) -> int:
    """课程标准答案导入：本地校验 → 经 8901 A2（POST /courses/{id}/knowledge，source=manual）。

    导入即定稿（QED-050 手动轨，2026-08-31）：新建或仍为 draft 的套逐套
    POST /knowledge/{id}/confirm（显式回传 refs/intros——confirm 空 body 会以 {} 覆盖预填 refs），
    并按 refs 幂等建 candidate 册（POST /books，同套同书同卷不重复建行）；
    已确认/已完成套跳过确认、仍补册，重放可续。CLI 路径直达"已确认+候选册就绪"。
    """
    import httpx

    from qed_tracker.application.knowledge_import import KnowledgeImportError, validate_course

    try:
        with open(args.path, encoding="utf-8") as stream:
            data = json.load(stream)
    except OSError as exc:
        _print({"error": f"文件不可读：{args.path}（{exc}）"}, True) if args.json else print(
            f"ERROR: 文件不可读：{args.path}（{exc}）", file=sys.stderr
        )
        return 2
    except json.JSONDecodeError as exc:
        _print({"error": f"JSON 解析失败：{exc}"}, True) if args.json else print(
            f"ERROR: JSON 解析失败：{exc}", file=sys.stderr
        )
        return 2
    try:
        validate_course(data)
    except KnowledgeImportError as exc:
        _print({"error": f"校验失败：{exc}"}, True) if args.json else print(
            f"ERROR: 校验失败：{exc}", file=sys.stderr
        )
        return 2

    course_id = data["course"]["course_id"]
    base_url = (args.tracker_url or settings.tracker_url).rstrip("/")
    try:
        response = httpx.post(
            f"{base_url}/api/v1/courses/{course_id}/knowledge",
            json={"tutorials": data["tutorials"], "source": "manual"},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        _print({"error": f"8901 服务不可达（{base_url}）：{exc}；请先启动 qed-tracker serve"}, True) if args.json else print(
            f"ERROR: 8901 服务不可达（{base_url}）：{exc}；请先启动 qed-tracker serve", file=sys.stderr
        )
        return 6
    if response.status_code >= 400:
        detail = response.json().get("detail", response.text)
        _print({"error": detail}, True) if args.json else print(f"ERROR: {detail}", file=sys.stderr)
        return 2

    def _post(url: str, payload: dict) -> tuple[int, dict]:
        resp = httpx.post(url, json=payload, timeout=30.0)
        try:
            body = resp.json()
        except ValueError:
            body = {"detail": resp.text}
        return resp.status_code, body

    tutorials_by_set = {str(item.get("set_no", "")).strip(): item for item in data["tutorials"]}
    confirmed = 0
    skipped_confirm = 0
    books_ensured = 0
    errors: list[str] = []
    for item in response.json().get("created", []):
        knowledge_id = str(item.get("knowledge_id", ""))
        set_no = str(item.get("set_no", "")).strip()
        status = str(item.get("status", ""))
        tutorial = tutorials_by_set.get(set_no, {})
        textbook = tutorial.get("textbook") or {}
        exercise = tutorial.get("exercise")
        if not knowledge_id:
            errors.append(f"套 {set_no or '?'}：采纳结果缺 knowledge_id")
            continue
        if status == "draft":
            code, body = _post(
                f"{base_url}/api/v1/knowledge/{knowledge_id}/confirm",
                {
                    "textbook_ref": textbook,
                    "exercise_ref": exercise,
                    "textbook_intro": str(textbook.get("intro", "")),
                    "exercise_intro": str((exercise or {}).get("intro", "")),
                },
            )
            if code >= 400:
                errors.append(f"套 {set_no} 确认失败（{code}）：{body.get('detail', body)}")
            else:
                confirmed += 1
        else:
            skipped_confirm += 1
        for kind, ref in (("textbook", textbook), ("exercise", exercise)):
            if not ref:
                continue
            payload = _ref_book_payload(knowledge_id, kind, ref)
            if not payload["title"]:
                errors.append(f"套 {set_no} {kind} 建册失败：ref 缺 title")
                continue
            code, body = _post(f"{base_url}/api/v1/books", payload)
            if code >= 400:
                errors.append(f"套 {set_no} {kind} 建册失败（{code}）：{body.get('detail', body)}")
            else:
                books_ensured += 1

    summary = {
        "course_id": course_id,
        "sets": len(response.json().get("created", [])),
        "confirmed": confirmed,
        "confirm_skipped": skipped_confirm,
        "books_ensured": books_ensured,
        "errors": errors,
    }
    _print(summary, args.json)
    if not args.json and errors:
        for message in errors:
            print(f"WARN: {message}", file=sys.stderr)
    return 2 if errors else 0


def _llm_call_engine(settings: Settings):
    """local 模式调用记录写 qed_llm_calls 用（QED-037）：DB 未配置时返回 None 不落库。"""
    if not settings.db_configured:
        return None
    from qed_tracker.database import create_engine_for

    return create_engine_for(settings)


def _mainline_advisor(*, api_key: str, model: str, base_url: str, timeout: float, call_budget: int, max_tokens: int,
                      api_select: str = "local", gateway_url: str = "", engine=None):
    from qed_tracker.main_line.advisor import MainLineAdvisor

    return MainLineAdvisor(
        api_key=api_key,
        model=model,
        base_url=base_url,
        timeout=timeout,
        call_budget=call_budget,
        max_tokens=max_tokens,
        api_select=api_select,
        gateway_url=gateway_url,
        engine=engine,
    )


def _migrate(args, settings: Settings) -> int:
    if not settings.db_configured:
        _print({"error": "数据库未配置：迁移需要 qed 库连接"}, True) if args.json else print(
            "ERROR: 数据库未配置：迁移需要 qed 库连接", file=sys.stderr
        )
        return 2
    from qed_tracker.application.migrate_knowledge import migrate_curriculum, migrate_legacy_data
    from qed_tracker.database import create_engine_for, session_factory
    from qed_tracker.db.knowledge_repository import InvalidTransition

    engine = create_engine_for(settings)
    factory = session_factory(engine)
    try:
        migrate_curriculum(factory)
        stats = migrate_legacy_data(factory, drop_legacy=args.drop_legacy)
    except (KeyError, InvalidTransition, ValueError) as exc:
        _print({"error": str(exc)}, True) if args.json else print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - DB 故障兜底
        _print({"error": f"数据库错误：{exc}"}, True) if args.json else print(f"ERROR: 数据库错误：{exc}", file=sys.stderr)
        return 2
    finally:
        engine.dispose()
    _print({"seeded": True, **stats}, True) if args.json else print(
        f"迁移完成：knowledge={stats['knowledge']} books={stats['books']} sources={stats['sources']}"
    )
    if not args.drop_legacy:
        print("提示：确认无误后可再次运行 `qed-tracker migrate --drop-legacy` 删除旧表", file=sys.stderr)
    return 0


def _mainline(args, settings: Settings) -> int:
    from qed_tracker.courses import set_repository
    from qed_tracker.db.knowledge_repository import InvalidTransition, KnowledgeRepository

    if not settings.db_configured:
        _print({"error": "数据库未配置：主链路需 qt_knowledge/qt_books 表"}, True) if args.json else print(
            "ERROR: 数据库未配置：主链路需 qt_knowledge/qt_books 表", file=sys.stderr
        )
        return 2
    from qed_tracker.database import create_engine_for, session_factory

    engine = create_engine_for(settings)
    factory = session_factory(engine)
    repo = KnowledgeRepository(factory)
    try:
        set_repository(repo)
        return _mainline_impl(args, repo, settings)
    except (KeyError, InvalidTransition, ValueError) as exc:
        _print({"error": str(exc)}, True) if args.json else print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - DB 故障兜底
        _print({"error": f"数据库错误：{exc}"}, True) if args.json else print(f"ERROR: 数据库错误：{exc}", file=sys.stderr)
        return 2
    finally:
        engine.dispose()


def _raw_title_from_name(name: str) -> str:
    """从规范展示名回退原始书名（QED-036）：「教程1：数学分析（Rudin）」→「数学分析」。"""
    rest = name
    prefix = rest.split("：", 1)
    if len(prefix) == 2 and prefix[0].startswith("教程"):
        rest = prefix[1]
    if rest.endswith("）") and "（" in rest:
        rest = rest[: rest.rfind("（")]
    return rest.strip()


def _mainline_impl(args, repo: KnowledgeRepository, settings: Settings) -> int:
    from qed_tracker.courses import load_course
    from qed_tracker.db.knowledge_repository import InvalidTransition, tutorial_name

    if args.mainline_command == "list":
        items = repo.list_knowledge(course_id=args.course)
        if args.json:
            payload = [
                {
                    "knowledge_id": item.knowledge_id,
                    "course_id": item.course_id,
                    "kind": item.kind,
                    "set_no": item.set_no,
                    "name": item.name,
                    "status": item.status,
                    "books": [
                        {"book_id": book.book_id, "title": book.title, "part": book.part, "status": book.status}
                        for book in repo.list_books(item.knowledge_id)
                    ],
                }
                for item in items
            ]
            _print(payload, True)
        else:
            for item in items:
                books = repo.list_books(item.knowledge_id)
                summary = "、".join(f"{book.display_title}[{book.status}]" for book in books) or "-"
                print(f"{item.knowledge_id} [{item.status}] {item.name}（{item.kind} 套{item.set_no}）")
                print(f"    书籍: {summary}")
        return 0

    if args.mainline_command == "channels":
        stats: dict[str, dict[str, int]] = {}
        for item in repo.list_knowledge():
            for book in repo.list_books(item.knowledge_id):
                for source in repo.list_sources(book.book_id):
                    bucket = stats.setdefault(source.channel, {"ok": 0, "fail": 0})
                    if source.ok:
                        bucket["ok"] += 1
                    else:
                        bucket["fail"] += 1
        _print_channel_summary(stats, args.json)
        return 0

    if args.mainline_command == "new":
        try:
            curriculum = load_course("math")
            course = next(c for c in curriculum.courses if c.course_id == args.course)
        except (ValueError, StopIteration):
            _print({"error": f"未知课程：{args.course}"}, True) if args.json else print(
                f"ERROR: 未知课程：{args.course}", file=sys.stderr
            )
            return 2
        existing = [item for item in repo.list_knowledge(course_id=args.course) if item.name == args.title]
        if existing:
            _print({"error": f"教材条目已存在：{existing[0].knowledge_id}"}, True) if args.json else print(
                f"ERROR: 教材条目已存在：{existing[0].knowledge_id}", file=sys.stderr
            )
            return 2
        set_no = args.set_no or ""
        # QED-036：有 set_no 时 name 按「教程{set_no}：书名（作者）」规范生成；否则保持原始 title
        name = tutorial_name(set_no, args.title, args.author) if set_no else args.title
        knowledge = repo.create_knowledge(
            domain_id=curriculum.subject, course_id=args.course, kind="tutorial", set_no=set_no, name=name
        )
        advisor = _mainline_advisor(
            api_key=llm_api_key(),
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            call_budget=settings.llm_call_budget,
            max_tokens=settings.llm_max_tokens,
            api_select=settings.api_select,
            gateway_url=settings.llm_gateway_url,
            engine=_llm_call_engine(settings),
        )
        try:
            prefilled = advisor.prefill(
                course={"course_id": course.course_id, "name": course.name, "stage": course.stage},
                title=args.title,
                authors=list(args.author),
            )
        except ValueError as exc:
            print(f"WARN: LLM 预填失败（{exc}）；draft 已建，可在 review 时人工补简介", file=sys.stderr)
            prefilled = {}
        finally:
            advisor.close()
        _print(
            {"knowledge_id": knowledge.knowledge_id, "status": knowledge.status, "prefill": prefilled}, True
        ) if args.json else print(f"已创建条目 {knowledge.knowledge_id}（{knowledge.status}），请 review 定稿")
        if prefilled:
            evaluation = prefilled["evaluation"]
            advice = prefilled["advice"]
            print(f"LLM 预填评价：{evaluation['text']}（权威性 {evaluation['authority']}）")
            print(f"LLM 建议：{advice['download']} - {advice['reason']}")
        return 0

    if args.mainline_command == "review":
        knowledge = repo.get_knowledge(args.knowledge_id)
        if knowledge is None:
            _print({"error": f"知识行不存在：{args.knowledge_id}"}, True) if args.json else print(
                f"ERROR: 知识行不存在：{args.knowledge_id}", file=sys.stderr
            )
            return 2
        intro = args.intro or f"{knowledge.name}：教材与习题集配套资源（LLM 预填 + 人工审）。"
        # QED-036：决定引用 {title, version, authors}；title 优先取 --title，缺省从规范名回退
        title = (args.title or "").strip() or _raw_title_from_name(knowledge.name)
        try:
            updated = repo.confirm_knowledge(
                knowledge.knowledge_id,
                textbook_ref={
                    "title": title,
                    "version": args.version or "",
                    "authors": list(args.author),
                },
                textbook_intro=intro,
            )
        except InvalidTransition as exc:
            _print({"error": str(exc)}, True) if args.json else print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        _print(updated.to_dict(), True) if args.json else print(f"已定稿：{updated.knowledge_id} → {updated.status}")
        return 0

    if args.mainline_command == "reject":
        try:
            updated = repo.reject_knowledge(args.knowledge_id, reason=args.reason, by="cli")
        except (KeyError, InvalidTransition, ValueError) as exc:
            _print({"error": str(exc)}, True) if args.json else print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        _print(updated.to_dict(), True) if args.json else print(f"已否定：{updated.knowledge_id}（{args.reason}）")
        return 0

    if args.mainline_command == "download":
        knowledge = repo.get_knowledge(args.knowledge_id)
        if knowledge is None:
            _print({"error": f"知识行不存在：{args.knowledge_id}"}, True) if args.json else print(
                f"ERROR: 知识行不存在：{args.knowledge_id}", file=sys.stderr
            )
            return 2
        if knowledge.status != "confirmed":
            _print({"error": f"只有 confirmed 知识行可下载（当前 {knowledge.status}）"}, True) if args.json else print(
                f"ERROR: 只有 confirmed 知识行可下载（当前 {knowledge.status}）", file=sys.stderr
            )
            return 2
        books = repo.list_books(knowledge.knowledge_id)
        book = next((b for b in books if b.status in ("candidate", "decided", "failed")), None)
        if book is None:
            done = next((b for b in books if b.status in ("downloaded", "verified")), None)
            if done is not None:
                action = "approve（或 reject 重选）" if done.status == "verified" else "verify（或 reject 重选）"
                _print({"book_id": done.book_id, "status": done.status, "message": "已下载"}, True) if args.json else print(
                    f"已下载，请执行 {action}"
                )
                return 0
            book = repo.create_book(
                knowledge.knowledge_id, kind="textbook", roles=["textbook"], title=knowledge.name, authors=[]
            )
        try:
            if book.status == "candidate":
                book = repo.decide_book(book.book_id)
                book = repo.start_download(book.book_id)
            elif book.status == "decided":
                book = repo.start_download(book.book_id)
            elif book.status == "failed":
                book = repo.retry_download(book.book_id)
            service = _book_service(settings)
            try:
                query = f"{knowledge.name} {knowledge.kind}".strip()
                ranked = service.search(query, limit=8)
                candidates = [item.candidate for item in ranked]
                for name, error in service.failures:
                    print(f"WARN {name}: {error}", file=sys.stderr)
                downloadable = [c for c in candidates if c.availability == Availability.DOWNLOADABLE]
                if not downloadable:
                    for c in candidates:
                        if c.availability == Availability.METADATA_ONLY and c.links:
                            print(f"人工下载指引 [{c.provider}]: {c.title}")
                            for link in c.links:
                                print(f"  - {link.label}: {link.url}")
                    repo.add_source(book.book_id, channel="search", ok=False, note="无自动可下载候选")
                    try:
                        repo.fail_download(book.book_id)
                    except InvalidTransition:
                        pass
                    _print({"error": "无自动可下载候选，请人工下载后登记"}, True) if args.json else print(
                        "WARN: 无自动可下载候选，请人工下载后登记", file=sys.stderr
                    )
                    return 3
                candidate = downloadable[0]
                record = service.download(candidate, kind=ResourceKind.BOOK)
                repo.add_source(book.book_id, channel=candidate.provider, ok=True, note=record.resource_id)
                repo.complete_download(
                    book.book_id,
                    sha256=record.sha256,
                    relative_path=record.file["relative_path"],
                    page_count=record.file.get("page_count"),
                    absolute_path=str(record.absolute_path(settings.data_root)),
                    file_name=Path(record.file["relative_path"]).name,
                )
                _print(
                    {"book_id": book.book_id, "resource_id": record.resource_id, "path": record.file["relative_path"]},
                    True,
                ) if args.json else print(f"已下载：{record.file['relative_path']}")
                return 0
            finally:
                service.close()
        except Exception as exc:  # noqa: BLE001 - CLI 顶层兜底
            repo.add_source(book.book_id, channel="download", ok=False, note=str(exc)[:300])
            try:
                repo.fail_download(book.book_id)
            except InvalidTransition:
                pass
            _print({"error": f"下载失败：{exc}"}, True) if args.json else print(
                f"ERROR: 下载失败：{exc}", file=sys.stderr
            )
            return 2

    if args.mainline_command == "verify":
        knowledge = repo.get_knowledge(args.knowledge_id)
        if knowledge is None:
            _print({"error": f"知识行不存在：{args.knowledge_id}"}, True) if args.json else print(
                f"ERROR: 知识行不存在：{args.knowledge_id}", file=sys.stderr
            )
            return 2
        books = repo.list_books(knowledge.knowledge_id)
        if args.book:
            book = next((b for b in books if b.book_id == args.book), None)
            if book is None:
                _print({"error": f"书行不存在：{args.book}"}, True) if args.json else print(
                    f"ERROR: 书行不存在：{args.book}", file=sys.stderr
                )
                return 2
            if book.status != "downloaded":
                _print({"error": f"书行未下载（当前 {book.status}），无法校验"}, True) if args.json else print(
                    f"ERROR: 书行未下载（当前 {book.status}），无法校验", file=sys.stderr
                )
                return 2
        else:
            book = next((b for b in books if b.status == "downloaded"), None)
            if book is None:
                _print({"error": "没有已下载（downloaded）的书行，请先执行 download"}, True) if args.json else print(
                    "ERROR: 没有已下载（downloaded）的书行，请先执行 download", file=sys.stderr
                )
                return 2
        path = Path(book.absolute_path or "")
        if not path.is_file():
            path = settings.data_root / Path(book.relative_path)
        if not path.is_file():
            _print({"error": f"文件不存在：{path}"}, True) if args.json else print(
                f"ERROR: 文件不存在：{path}", file=sys.stderr
            )
            return 3
        try:
            from qed_tracker.downloader import inspect_pdf

            digest, size, pages = inspect_pdf(path)
        except Exception as exc:  # noqa: BLE001
            _print({"error": f"校验失败：{exc}"}, True) if args.json else print(
                f"ERROR: 校验失败：{exc}", file=sys.stderr
            )
            return 2
        verified = repo.verify_book(book.book_id)
        _print(
            {"book_id": verified.book_id, "path": str(path), "sha256": digest[:16], "size_bytes": size,
             "page_count": pages, "status": verified.status},
            True,
        ) if args.json else print(
            f"已校验：{verified.book_id} → {verified.status} | {path} | sha256={digest[:16]}... | {size} bytes | {pages} 页"
        )
        return 0

    if args.mainline_command == "approve":
        knowledge = repo.get_knowledge(args.knowledge_id)
        if knowledge is None:
            _print({"error": f"知识行不存在：{args.knowledge_id}"}, True) if args.json else print(
                f"ERROR: 知识行不存在：{args.knowledge_id}", file=sys.stderr
            )
            return 2
        verified = [b for b in repo.list_books(knowledge.knowledge_id) if b.status == "verified"]
        if not verified:
            _print({"error": "没有已验收（verified）的书行，请先执行 verify"}, True) if args.json else print(
                "ERROR: 没有已验收（verified）的书行，请先执行 verify", file=sys.stderr
            )
            return 2

        def _source(book) -> Path:
            path = Path(book.absolute_path or "")
            if not path.is_file():
                path = settings.data_root / Path(book.relative_path)
            return path

        def _target(book) -> Path:
            return (
                raw_course_dir(settings.data_root, knowledge.course_id, domain_id=knowledge.domain_id)
                / _source(book).name
            )

        if args.book:
            book = next((b for b in verified if b.book_id == args.book), None)
            if book is None:
                _print({"error": f"书行不存在或未验收：{args.book}"}, True) if args.json else print(
                    f"ERROR: 书行不存在或未验收：{args.book}", file=sys.stderr
                )
                return 2
        else:
            book = next(
                (b for b in verified if not _target(b).exists() or _target(b).resolve() == _source(b).resolve()),
                verified[0],
            )
        source = _source(book)
        if not source.is_file():
            _print({"error": f"文件不存在：{source}"}, True) if args.json else print(
                f"ERROR: 文件不存在：{source}", file=sys.stderr
            )
            return 3
        try:
            from qed_tracker.downloader import inspect_pdf

            inspect_pdf(source)  # 验收前校验 PDF 完整性
        except Exception as exc:  # noqa: BLE001
            _print({"error": f"PDF 校验失败：{exc}"}, True) if args.json else print(
                f"ERROR: PDF 校验失败：{exc}", file=sys.stderr
            )
            return 2
        # 移交：目标 = 数据根共享布局 raw/<domain>/<course>/
        try:
            target_dir = raw_course_dir(settings.data_root, knowledge.course_id, domain_id=knowledge.domain_id)
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / source.name
            if target.exists() and target.resolve() != source.resolve():
                _print({"error": f"移交目标已存在：{target}"}, True) if args.json else print(
                    f"ERROR: 移交目标已存在：{target}", file=sys.stderr
                )
                return 2
            import shutil

            shutil.copy2(source, target)
        except OSError as exc:
            _print({"error": f"移交失败：{exc}"}, True) if args.json else print(
                f"ERROR: 移交失败：{exc}", file=sys.stderr
            )
            return 2
        _print({"final_path": str(target), "status": "approved"}, True) if args.json else print(
            f"验收通过，已移交根仓库：{target}"
        )
        try:
            repo.complete_knowledge(knowledge.knowledge_id)
            _print({"knowledge_status": "completed"}, True) if args.json else print(
                f"知识行已完成：{knowledge.knowledge_id} → completed"
            )
        except InvalidTransition as exc:
            print(f"提示：{exc}（书行全 verified 后可再次 approve 完成知识行）", file=sys.stderr)
        print("提示：课程 related_targets 回填待二次确认评估后人工执行（qed_course 表）", file=sys.stderr)
        return 0

    print(f"ERROR: 未实现的 mainline 命令：{args.mainline_command}", file=sys.stderr)
    return 2


def _print_channel_summary(stats: dict[str, dict[str, int]], json_output: bool) -> None:
    """按渠道聚合成功/失败次数（qt_sources 运行时事实）。"""
    if json_output:
        _print({"channels": stats}, True)
    else:
        print(f"{'渠道':<20} 成功  失败")
        for name, counts in sorted(stats.items()):
            print(f"{name:<20} {counts['ok']:>3}  {counts['fail']:>3}")


def _configure_serve_logging(log_dir: Path) -> None:
    """serve 日志双通道：stderr + 仓库根 logs/qed-tracker.log（UTF-8）。

    幂等：root 已挂 FileHandler 时跳过（重复调用与 pytest 捕获 handler 均不干扰）；
    测试通过 monkeypatch 本函数隔离日志目录（不写仓库根 logs/）。
    """
    import logging

    root = logging.getLogger()
    if any(isinstance(handler, logging.FileHandler) for handler in root.handlers):
        return
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    log_dir.mkdir(parents=True, exist_ok=True)
    for handler in (logging.StreamHandler(), logging.FileHandler(log_dir / "qed-tracker.log", encoding="utf-8")):
        handler.setFormatter(formatter)
        root.addHandler(handler)


def _serve(args, settings: Settings) -> int:
    from qed_tracker.api.main import create_app

    _configure_serve_logging(Path(__file__).resolve().parents[2] / "logs")
    try:
        upgrade_database(settings)
    except Exception as exc:  # 数据库不可用时服务仍可启动（健康/浏览可用，任务明确报错）
        print(f"WARN 数据库迁移跳过：{exc}", file=sys.stderr)
    uvicorn.run(create_app(settings), host=args.host, port=args.port or settings.port, log_level="info", log_config=None)
    return 0


def _load_root_env(start: Path) -> Path | None:
    """从 start 向上查找根 `.env`，注入 `QED_*` 与供应商密钥（已有环境变量不覆盖）。

    独立启动 `qed-tracker serve` 时补上根仓库统一配置，保持与 `qed` 注入环境一致。
    """
    env_path = next(
        (candidate / ".env" for candidate in [start, *start.parents] if (candidate / ".env").is_file()), None
    )
    if env_path is None:
        return None
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("QED_") or key in ("QWEN_API_KEY", "DEEPSEEK_API_KEY", "GLM_API_KEY"):
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))
    return env_path


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command in ("serve", "mainline", "migrate"):
            # DB 系命令与 serve 一样注入根 .env（QED-031：mainline/migrate 依赖 qed 库）
            _load_root_env(Path.cwd())
        settings = _settings(args)
        handlers = {
            "books": _books,
            "papers": _papers,
            "catalog": _catalog,
            "inventory": _inventory,
            "axiom": _axiom,
            "config": _config,
            "courses": _courses,
            "domains": _domains,
            "knowledge": _knowledge_import,
            "mainline": _mainline,
            "migrate": _migrate,
            "serve": _serve,
        }
        return handlers[args.command](args, settings)
    except (ValueError, OSError, RuntimeError) as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
