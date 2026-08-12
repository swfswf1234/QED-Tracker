"""`qed-tracker` 统一命令行入口。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

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
from qed_tracker.inventory import Inventory
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

    mainline = commands.add_parser("mainline", help="主链路教材条目（课程梳理→下载→验收）")
    mainline_commands = mainline.add_subparsers(dest="mainline_command", required=True)
    mainline_list = mainline_commands.add_parser("list", help="列出课程教材条目")
    mainline_list.add_argument("--course", required=True)
    mainline_new = mainline_commands.add_parser("new", help="新建条目（LLM 预填评价）")
    mainline_new.add_argument("--course", required=True)
    mainline_new.add_argument("--title", required=True)
    mainline_new.add_argument("--author", action="append", default=[])
    mainline_review = mainline_commands.add_parser("review", help="人工评审定稿（版本/评价/建议）")
    mainline_review.add_argument("course_id")
    mainline_review.add_argument("entry_id")
    mainline_download = mainline_commands.add_parser("download", help="触发渠道下载")
    mainline_download.add_argument("course_id")
    mainline_download.add_argument("entry_id")
    mainline_verify = mainline_commands.add_parser("verify", help="校验已下载文件")
    mainline_verify.add_argument("course_id")
    mainline_verify.add_argument("entry_id")
    mainline_approve = mainline_commands.add_parser("approve", help="验收通过 → 移交根仓库")
    mainline_approve.add_argument("course_id")
    mainline_approve.add_argument("entry_id")
    mainline_reject = mainline_commands.add_parser("reject", help="验收不通过（填原因）")
    mainline_reject.add_argument("course_id")
    mainline_reject.add_argument("entry_id")
    mainline_reject.add_argument("--reason", required=True)
    mainline_commands.add_parser("channels", help="渠道有效性汇总")

    serve = commands.add_parser("serve", help="启动工作台 API 服务（8901）")
    serve.add_argument("--host", default="127.0.0.1", help="监听地址")
    serve.add_argument("--port", type=int, default=None, help="监听端口（默认取配置 port）")
    return parser


def _settings(args) -> Settings:
    return load_settings(data_root=args.data_root, proxy=args.proxy)


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
    providers = create_book_providers(names or settings.sources, proxy=settings.proxy, timeout=settings.timeout_seconds, tls_verify=settings.tls_verify)
    downloader = DownloadManager(proxy=settings.proxy, timeout=settings.timeout_seconds, retries=settings.retries, tls_verify=settings.tls_verify)
    return BookService(providers, ResourceService(Inventory(settings.data_root), downloader))


def _paper_service(settings: Settings, *, with_advisor: bool = False) -> PaperService:
    provider = ArxivProvider(retries=settings.retries)
    manager = DownloadManager(proxy=settings.proxy, timeout=max(settings.timeout_seconds, 120), retries=settings.retries, tls_verify=settings.tls_verify)
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
    if args.books_command == "fetch-url":
        manager = DownloadManager(proxy=settings.proxy, timeout=settings.timeout_seconds, retries=settings.retries, tls_verify=settings.tls_verify)
        resources = ResourceService(inventory, manager)
        try:
            candidate = Candidate("url", args.url, args.title, tuple(args.author), args.language, page_url=args.url, download_url=args.url)
            record = resources.download_candidate(candidate, kind=ResourceKind(args.kind), destination_dir=settings.data_root / "raw" / "books" / "inbox")
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
            _print([_candidate_dict(item) for item in candidates], True) if args.json else _display_candidates(candidates)
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
            _print(asdict(profile), True) if args.json else print(json.dumps(asdict(profile), ensure_ascii=False, indent=2))
            return 0
        except ValueError as exc:
            _print({"error": str(exc)}, True) if args.json else print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    service = _paper_service(settings, with_advisor=args.papers_command == "recommend")
    try:
        if args.papers_command == "selections":
            if args.selections_command == "list":
                reports = service.list_selections()
                summaries = [{"selection_id": item["selection_id"], "status": item["status"], "created_at": item["created_at"], "profile": item["profile"]["id"]} for item in reports]
                _print(summaries, args.json) if args.json else print("\n".join(f"{item['selection_id']} | {item['status']} | {item['profile']}" for item in summaries))
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
            report = service.recommend(profile, goal=args.goal, categories=args.categories, limit=args.limit, top=args.top)
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
        value = {"id": catalog.id, "name": catalog.name, "description": catalog.description, "status": catalog.status, "targets": [asdict(target) for target in catalog.targets]}
        _print(value, True) if args.json else print("\n".join(f"{target.id}: {target.course_name} | {target.kind.value} | {target.title}" for target in catalog.targets))
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
            _print([{"target": asdict(item.target), "status": item.status, "reason": item.reason, "resource": item.record.to_dict() if item.record else None} for item in attempts], True)
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
        _print([record.to_dict() for record in records], args.json) if args.json else print("\n".join(f"{record.resource_id} | {record.kind} | {record.title} | {record.file['relative_path']}" for record in records))
        return 0
    if args.inventory_command == "scan":
        roots = args.roots or [settings.data_root]
        records, errors = inventory.scan(roots)
        value = {"registered": len(records), "errors": [{"path": str(path), "error": error} for path, error in errors]}
        _print(value, args.json)
        return 4 if errors else 0
    if args.inventory_command == "verify":
        results = inventory.verify()
        _print([{"resource_id": record.resource_id, "status": status} for record, status in results], True) if args.json else print("\n".join(f"[{status}] {record.resource_id} {record.title}" for record, status in results))
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
    client = AxiomClient(args.axiom_url or settings.axiom_url, timeout=max(settings.timeout_seconds, 120), tls_verify=settings.tls_verify)
    try:
        result = client.push(resource, inventory, parse=args.parse, page_start=args.page_start, page_end=args.page_end)
        _print(result, True if args.json else False)
        return 0
    finally:
        client.close()


def _config(args, settings: Settings) -> int:
    if args.config_command == "show":
        _print({
            "data_root": str(settings.data_root), "proxy": settings.proxy, "timeout_seconds": settings.timeout_seconds,
            "retries": settings.retries, "sources": list(settings.sources), "axiom_url": settings.axiom_url,
            "tls_verify": settings.tls_verify, "llm_model": settings.llm_model, "llm_base_url": settings.llm_base_url,
            "llm_timeout_seconds": settings.llm_timeout_seconds, "llm_call_budget": settings.llm_call_budget,
            "llm_max_tokens": settings.llm_max_tokens, "port": settings.port, "tracker_url": settings.tracker_url,
            "db_host": settings.db_host, "db_port": settings.db_port, "db_name": settings.db_name,
            "db_user": settings.db_user, "db_configured": settings.db_configured,
        }, True)
        return 0
    raise ValueError(f"未知 config 命令：{args.config_command}")


def _courses(args, settings: Settings) -> int:
    from qed_tracker.courses import list_courses

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
            print(f"{prefix} {course.course_id} {course.name} [{course.stage}] 前置: {', '.join(course.prerequisites) or '-'}")
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


def _mainline_advisor(*, api_key: str, model: str, base_url: str, timeout: float, call_budget: int, max_tokens: int):
    from qed_tracker.main_line.advisor import MainLineAdvisor
    return MainLineAdvisor(
        api_key=api_key,
        model=model,
        base_url=base_url,
        timeout=timeout,
        call_budget=call_budget,
        max_tokens=max_tokens,
    )


def _entry_slug(title: str) -> str:
    """从标题生成稳定 ASCII slug（课程前缀由调用方拼）。"""
    import re
    text = re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-").lower()
    if not text:
        text = "entry"
    return text[:48]


def _mainline(args, settings: Settings) -> int:
    from qed_tracker.courses import load_course
    from qed_tracker.main_line.store import EntryStore, MainLineStatus

    store = EntryStore(settings.data_root)

    if args.mainline_command == "list":
        entries = store.list_course(args.course)
        if args.json:
            _print([e.to_dict() for e in entries], True)
        else:
            for entry in entries:
                print(f"{entry.entry_id} [{entry.status}] {entry.title}（{entry.evaluation.get('authority', '-')}）")
        return 0

    if args.mainline_command == "channels":
        _print_channel_summary(store, args.json)
        return 0

    if args.mainline_command == "new":
        try:
            curriculum = load_course("math")
            course = next(c for c in curriculum.courses if c.course_id == args.course)
        except (ValueError, StopIteration):
            _print({"error": f"未知课程：{args.course}"}, True) if args.json else print(f"ERROR: 未知课程：{args.course}", file=sys.stderr)
            return 2
        advisor = _mainline_advisor(
            api_key=llm_api_key(),
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            call_budget=settings.llm_call_budget,
            max_tokens=settings.llm_max_tokens,
        )
        try:
            prefilled = advisor.prefill(
                course={"course_id": course.course_id, "name": course.name, "stage": course.stage},
                title=args.title,
                authors=args.author,
            )
        except ValueError as exc:
            _print({"error": f"LLM 预填失败：{exc}"}, True) if args.json else print(f"ERROR: LLM 预填失败：{exc}", file=sys.stderr)
            return 2
        finally:
            advisor.close()
        entry_id = _entry_slug(args.title)
        data = {
            "entry_id": entry_id,
            "course_id": args.course,
            "title": args.title,
            "authors": tuple(args.author),
            "evaluation": prefilled["evaluation"],
            "advice": prefilled["advice"],
        }
        try:
            entry = store.create(data)
        except ValueError as exc:
            _print({"error": str(exc)}, True) if args.json else print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        _print(entry.to_dict(), True) if args.json else print(f"已创建条目 {entry.entry_id}（{entry.status}），请 review 定稿")
        return 0

    if args.mainline_command == "review":
        entry = store.get(args.course_id, args.entry_id)
        if entry is None:
            _print({"error": f"条目不存在：{args.entry_id}"}, True) if args.json else print(f"ERROR: 条目不存在：{args.entry_id}", file=sys.stderr)
            return 2
        try:
            updated = store.transition(args.course_id, args.entry_id, MainLineStatus.REVIEWED)
        except ValueError as exc:
            _print({"error": str(exc)}, True) if args.json else print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        _print(updated.to_dict(), True) if args.json else print(f"已评审定稿：{updated.entry_id} → {updated.status}")
        return 0

    if args.mainline_command == "reject":
        try:
            updated = store.transition(args.course_id, args.entry_id, MainLineStatus.REJECTED)
        except ValueError as exc:
            _print({"error": str(exc)}, True) if args.json else print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        _print(updated.to_dict(), True) if args.json else print(f"已否定：{updated.entry_id}（{args.reason}）")
        return 0

    print(f"ERROR: 未实现的 mainline 命令：{args.mainline_command}", file=sys.stderr)
    return 2


def _print_channel_summary(store, json_output: bool) -> None:
    """按渠道聚合 success/fail（实现见任务 6；先输出空汇总）。"""
    if json_output:
        _print({"channels": {}}, True)
    else:
        print("渠道有效性汇总（实现中）")


def _serve(args, settings: Settings) -> int:
    import logging

    from qed_tracker.api.main import create_app

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        upgrade_database(settings)
    except Exception as exc:  # 数据库不可用时服务仍可启动（健康/浏览可用，任务明确报错）
        print(f"WARN 数据库迁移跳过：{exc}", file=sys.stderr)
    uvicorn.run(create_app(settings), host=args.host, port=args.port or settings.port, log_level="info")
    return 0


def _load_root_env(start: Path) -> Path | None:
    """从 start 向上查找根 `.env`，注入 `QED_*` 与供应商密钥（已有环境变量不覆盖）。

    独立启动 `qed-tracker serve` 时补上根仓库统一配置，保持与 `qed` 注入环境一致。
    """
    env_path = next((candidate / ".env" for candidate in [start, *start.parents] if (candidate / ".env").is_file()), None)
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
        if args.command == "serve":
            _load_root_env(Path.cwd())
        settings = _settings(args)
        handlers = {"books": _books, "papers": _papers, "catalog": _catalog, "inventory": _inventory, "axiom": _axiom, "config": _config, "courses": _courses, "mainline": _mainline, "serve": _serve}
        return handlers[args.command](args, settings)
    except (ValueError, OSError, RuntimeError) as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
