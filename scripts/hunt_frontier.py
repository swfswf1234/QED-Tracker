"""前沿资讯采集入口 — 手动/定时运行

用法:
    python scripts/hunt_frontier.py                   # 增量采集新文章
    python scripts/hunt_frontier.py --dry-run          # 预览新文章，不入库
    python scripts/hunt_frontier.py --seed             # 种子数据首次入库
    python scripts/hunt_frontier.py --seed --dry-run   # 预览种子
    python scripts/hunt_frontier.py --summary          # 采集 + LLM 摘要 (预留)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import argparse

from app.core.config import settings
from app.collectors.frontier_collector import FrontierCollector


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="前沿资讯采集")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不入库")
    parser.add_argument("--seed", action="store_true", help="种子数据首次入库")
    parser.add_argument("--summary", action="store_true", help="采集后生成 LLM 摘要 (预留)")
    parser.add_argument("--no-db", action="store_true", help="跳过数据库写入")
    return parser.parse_args(argv)


def main():
    args = parse_args()

    proxy = settings.http_proxy
    collector = FrontierCollector(proxy=proxy)

    no_db = args.no_db

    if args.seed:
        print(f"\n{'='*60}")
        print("种子数据首次入库")
        print(f"{'='*60}")
        n = collector.run(dry_run=args.dry_run, seed=True, no_db=no_db)
        tag = "[DRY RUN] " if args.dry_run else ""
        print(f"{tag}种子: {n} 篇")
    else:
        print(f"\n{'='*60}")
        print("增量采集前沿文章")
        print(f"{'='*60}")
        n = collector.run(dry_run=args.dry_run, seed=False, no_db=no_db)
        tag = "[DRY RUN] " if args.dry_run else ""
        tag2 = " (跳过入库)" if args.no_db else ""
        print(f"{tag}采集: {n} 篇{tag2}")

    if args.summary:
        print("\n[LLM 摘要] 功能预留，待后续实现")


if __name__ == "__main__":
    main()
