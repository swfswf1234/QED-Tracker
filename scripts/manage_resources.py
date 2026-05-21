"""Manage resources stored in the resources table.

Usage:
    python scripts/manage_resources.py list --type article --limit 20
    python scripts/manage_resources.py search probability
    python scripts/manage_resources.py favorite <resource_id>
    python scripts/manage_resources.py export --format markdown --output resources.md
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.database import get_conn, init_tables
from app.models.resource import Resource
from app.repository.resource_repo import ResourceRepo


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="管理 resources 表中的资料")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出资料")
    list_parser.add_argument("--type", type=str, help="按 resource_type 过滤")
    list_parser.add_argument("--limit", type=int, default=50, help="最多显示数量")
    list_parser.add_argument("--favorites", action="store_true", help="只显示收藏")

    search_parser = subparsers.add_parser("search", help="搜索资料")
    search_parser.add_argument("keyword", type=str, help="搜索关键词")
    search_parser.add_argument("--type", type=str, help="按 resource_type 过滤")

    favorite_parser = subparsers.add_parser("favorite", help="收藏或取消收藏")
    favorite_parser.add_argument("resource_id", type=str, help="资源 ID")
    favorite_parser.add_argument("--unset", action="store_true", help="取消收藏")

    export_parser = subparsers.add_parser("export", help="导出资料")
    export_parser.add_argument("--format", choices=["markdown"], default="markdown")
    export_parser.add_argument("--output", type=str, help="输出文件；不填则打印到 stdout")

    return parser.parse_args(argv)


def format_resource(resource: Resource) -> str:
    marker = "*" if resource.is_favorite else " "
    platform = resource.platform or "-"
    return f"[{marker}] {resource.id} | {resource.resource_type} | {resource.title} | {platform}\n    {resource.url}"


def render_markdown(resources: list[Resource]) -> str:
    grouped: dict[str, list[Resource]] = {}
    for resource in resources:
        grouped.setdefault(resource.resource_type, []).append(resource)

    lines = ["# QED Resources", ""]
    for resource_type in sorted(grouped):
        lines.append(f"## {resource_type}")
        lines.append("")
        for resource in sorted(grouped[resource_type], key=lambda r: r.title.lower()):
            favorite = " ⭐" if resource.is_favorite else ""
            description = f" — {resource.description}" if resource.description else ""
            lines.append(f"- [{resource.title}]({resource.url}){favorite}{description}")
            meta = ", ".join(part for part in [resource.platform, resource.author] if part)
            if meta:
                lines.append(f"  - {meta}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def list_resources(repo: ResourceRepo, resource_type: str | None, limit: int, favorites: bool) -> list[Resource]:
    if favorites:
        resources = repo.list_favorites()
    elif resource_type:
        resources = repo.get_by_type(resource_type)
    else:
        resources = repo.list(limit=limit)
    return resources[:limit]


def run(args) -> int:
    db = get_conn()
    try:
        init_tables()
        repo = ResourceRepo(db)

        if args.command == "list":
            resources = list_resources(repo, args.type, args.limit, args.favorites)
            for resource in resources:
                print(format_resource(resource))
            return len(resources)

        if args.command == "search":
            resources = repo.search(args.keyword, resource_type=args.type)
            for resource in resources:
                print(format_resource(resource))
            return len(resources)

        if args.command == "favorite":
            resource = repo.set_favorite(args.resource_id, value=not args.unset)
            if resource is None:
                print(f"未找到资源: {args.resource_id}")
                return -1
            state = "取消收藏" if args.unset else "已收藏"
            print(f"{state}: {resource.title}")
            return 0

        if args.command == "export":
            resources = repo.list(limit=10000)
            output = render_markdown(resources)
            if args.output:
                Path(args.output).write_text(output, encoding="utf-8")
                print(f"导出: {args.output}")
            else:
                print(output)
            return len(resources)

    finally:
        db.close()

    return 0


def main():
    result = run(parse_args())
    raise SystemExit(0 if isinstance(result, int) and result >= 0 else 1)


if __name__ == "__main__":
    main()
