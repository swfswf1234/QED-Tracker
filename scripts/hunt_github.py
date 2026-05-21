"""Collect GitHub repository metadata into resources.

Usage:
    python scripts/hunt_github.py pytorch/pytorch vllm-project/vllm
    python scripts/hunt_github.py --file repos.txt
    python scripts/hunt_github.py --file repos.txt --no-db
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.collectors.github_collector import GitHubCollector


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="采集 GitHub 仓库元数据")
    parser.add_argument("repos", nargs="*", help="GitHub 仓库，如 pytorch/pytorch")
    parser.add_argument("--file", type=str, help="从文本文件读取仓库列表，每行一个 repo")
    parser.add_argument("--no-db", action="store_true", help="只预览，不写入数据库")
    return parser.parse_args(argv)


def load_repos(args) -> list[str]:
    repos = list(args.repos)
    if args.file:
        path = Path(args.file)
        for line in path.read_text(encoding="utf-8").splitlines():
            item = line.strip()
            if item and not item.startswith("#"):
                repos.append(item)
    seen = set()
    unique = []
    for repo in repos:
        if repo not in seen:
            seen.add(repo)
            unique.append(repo)
    return unique


def main():
    args = parse_args()
    repos = load_repos(args)
    if not repos:
        print("未提供 GitHub 仓库。示例: python scripts/hunt_github.py pytorch/pytorch")
        raise SystemExit(1)

    collector = GitHubCollector()
    imported = collector.collect_repos(repos, no_db=args.no_db)
    tag = "预览" if args.no_db else "入库"
    print(f"{tag}: {imported}/{len(repos)}")


if __name__ == "__main__":
    main()
