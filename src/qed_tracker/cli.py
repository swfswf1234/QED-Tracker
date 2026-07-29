"""`qed-tracker` 统一命令行入口。"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from qed_tracker import __version__
from qed_tracker.axiom import AxiomClient
from qed_tracker.catalog import list_catalogs, load_catalog
from qed_tracker.config import Settings, example_config, load_settings
from qed_tracker.downloader import DownloadManager
from qed_tracker.inventory import Inventory
from qed_tracker.models import Availability, Candidate, ResourceKind
from qed_tracker.providers import ArxivProvider, create_book_providers
from qed_tracker.services import BookService, ResourceService, attempts_markdown


def _add_limit(parser: argparse.ArgumentParser, default: int = 10) -> None:
    parser.add_argument("--limit", type=int, default=default, help="每个来源的最大结果数")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qed-tracker", description="教材、习题集与 arXiv 论文下载工具")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", type=Path, help="显式 TOML 配置路径")
    parser.add_argument("--data-root", type=Path, help="覆盖数据根目录")
    parser.add_argument("--proxy", help="覆盖 HTTP 代理")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    commands = parser.add_subparsers(dest="command", required=True)

    books = commands.add_parser("books", help="教材和习题集")
    books_commands = books.add_subparsers(dest="books_command", required=True)
    books_search = books_commands.add_parser("search", help="搜索所有已启用来源")
    books_search.add_argument("query")
    books_search.add_argument("--source", action="append", dest="sources")
    _add_limit(books_search)
    books_get = books_commands.add_parser("get", help="搜索、选择并下载")
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
    inventory_export = inventory_commands.add_parser("export", help="确定性导出 JSONL")
    inventory_export.add_argument("--output", type=Path)

    axiom = commands.add_parser("axiom", help="交付给 Axiom-Flow")
    axiom_commands = axiom.add_subparsers(dest="axiom_command", required=True)
    axiom_push = axiom_commands.add_parser("push", help="显式上传一个已登记 PDF")
    axiom_push.add_argument("resource")
    axiom_push.add_argument("--url", dest="axiom_url")
    axiom_push.add_argument("--parse", action="store_true")
    axiom_push.add_argument("--page-start", type=int)
    axiom_push.add_argument("--page-end", type=int)

    config = commands.add_parser("config", help="本地配置")
    config_commands = config.add_subparsers(dest="config_command", required=True)
    config_init = config_commands.add_parser("init", help="创建本地配置")
    config_init.add_argument("--path", type=Path, default=Path("qed-tracker.local.toml"))
    config_init.add_argument("--data-root", default="E:/qed/dataset")
    config_init.add_argument("--force", action="store_true")
    config_commands.add_parser("show", help="显示生效配置")
    return parser


def _settings(args) -> Settings:
    return load_settings(args.config, data_root=args.data_root, proxy=args.proxy)


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


def _books(args, settings: Settings) -> int:
    inventory = Inventory(settings.data_root)
    if args.books_command == "fetch-url":
        manager = DownloadManager(proxy=settings.proxy, timeout=settings.timeout_seconds, retries=settings.retries, tls_verify=settings.tls_verify)
        try:
            candidate = Candidate("url", args.url, args.title, tuple(args.author), args.language, page_url=args.url, download_url=args.url)
            record = ResourceService(inventory, manager).download_candidate(candidate, kind=ResourceKind(args.kind), destination_dir=settings.data_root / "books" / "inbox")
            _print(record.to_dict(), args.json)
            return 0
        finally:
            manager.close()
    service = _book_service(settings, tuple(args.sources) if args.sources else None)
    try:
        ranked = service.search(args.query, limit=args.limit)
        candidates = [item.candidate for item in ranked]
        if args.books_command == "search":
            _print([_candidate_dict(item) for item in candidates], True) if args.json else _display_candidates(candidates)
            for name, error in service.failures:
                print(f"WARN {name}: {error}", file=sys.stderr)
            return 0 if candidates else 3
        if not candidates:
            print("没有搜索结果", file=sys.stderr)
            return 3
        _display_candidates(candidates)
        pick = args.pick
        if pick is None:
            if not sys.stdin.isatty():
                print("非交互环境必须提供 --pick", file=sys.stderr)
                return 2
            raw = input("选择下载序号（留空取消）：").strip()
            if not raw:
                return 0
            pick = int(raw)
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
        service.resources.downloader.close()
        service.close()


def _papers(args, settings: Settings) -> int:
    provider = ArxivProvider(retries=settings.retries)
    manager = DownloadManager(proxy=settings.proxy, timeout=max(settings.timeout_seconds, 120), retries=settings.retries, tls_verify=settings.tls_verify)
    resources = ResourceService(Inventory(settings.data_root), manager)
    try:
        if args.papers_command == "get":
            candidates = [provider.get(identifier) for identifier in args.identifiers]
            picks = range(len(candidates))
        else:
            candidates = provider.search(args.query, category=args.category, author=args.author, limit=args.limit)
            if args.json and not args.download:
                _print([_candidate_dict(item) for item in candidates], True)
            elif not args.download:
                _display_candidates(candidates)
            picks = [index - 1 for index in args.download]
        records = []
        for index in picks:
            if index < 0 or index >= len(candidates):
                raise ValueError(f"论文序号超出范围：{index + 1}")
            candidate = candidates[index]
            destination = settings.data_root / "papers" / (candidate.year or "unknown")
            records.append(resources.download_candidate(candidate, kind=ResourceKind.PAPER, destination_dir=destination))
        if records:
            _print([record.to_dict() for record in records], args.json)
        return 0 if candidates else 3
    finally:
        provider.close()
        manager.close()


def _catalog(args, settings: Settings) -> int:
    if args.catalog_command == "list":
        _print(list(list_catalogs()), args.json)
        return 0
    catalog = load_catalog(args.catalog_id)
    if args.catalog_command == "show":
        value = {"id": catalog.id, "name": catalog.name, "description": catalog.description, "status": catalog.status, "targets": [asdict(target) for target in catalog.targets]}
        _print(value, True) if args.json else print("\n".join(f"{target.id}: {target.course_name} | {target.kind.value} | {target.title}" for target in catalog.targets))
        return 0
    service = _book_service(settings)
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
        service.resources.downloader.close()
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
    path = inventory.export_jsonl(args.output)
    _print(str(path), args.json)
    return 0


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
        _print({"data_root": str(settings.data_root), "proxy": settings.proxy, "timeout_seconds": settings.timeout_seconds, "retries": settings.retries, "sources": list(settings.sources), "axiom_url": settings.axiom_url, "tls_verify": settings.tls_verify}, True)
        return 0
    path = args.path
    if path.exists() and not args.force:
        print(f"配置已存在：{path}（使用 --force 覆盖）", file=sys.stderr)
        return 2
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(example_config(args.data_root), encoding="utf-8")
    print(path.resolve())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        settings = _settings(args)
        handlers = {"books": _books, "papers": _papers, "catalog": _catalog, "inventory": _inventory, "axiom": _axiom, "config": _config}
        return handlers[args.command](args, settings)
    except (ValueError, OSError, RuntimeError) as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
