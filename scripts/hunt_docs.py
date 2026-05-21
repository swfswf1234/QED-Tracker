"""官方文档爬取入口 — 一次性运行

用法:
    python scripts/hunt_docs.py --name pytorch       # 爬取单个文档
    python scripts/hunt_docs.py --name scikit_learn  # 爬取 sklearn
    python scripts/hunt_docs.py --all                # 爬取全部
    python scripts/hunt_docs.py --no-db              # 跳过数据库写入
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
from loguru import logger

from app.core.config import settings
from app.core.database import get_conn, init_tables, check_db
from app.collectors.doc_scraper import DocScraper, DOC_SOURCES
from app.repository.doc_repo import OfficialDocRepo
from app.models.official_doc import OfficialDoc


def save_to_db(results: list[dict]):
    if not results:
        return
    db = get_conn()
    try:
        init_tables()
        repo = OfficialDocRepo(db)
        imported = 0
        for r in results:
            existing = repo.get_by_name(r["name"])
            if existing:
                existing.version = str(r.get("elapsed_seconds", ""))
                existing.pages_count = r.get("file_count", 0)
                repo.update(existing)
                print(f"  [更新] {r['name']}")
            else:
                repo.create(OfficialDoc(
                    id=None,
                    name=r["name"],
                    source_url=r["url"],
                    local_path=r.get("local_path", ""),
                    pages_count=r.get("file_count", 0),
                ))
                imported += 1
        print(f"  入库: {imported} 新文档")
    except Exception as e:
        db.rollback()
        print(f"  [数据库错误] {e}")
    finally:
        db.close()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="官方文档爬取")
    parser.add_argument("--name", type=str, help=f"文档名: {', '.join(DOC_SOURCES.keys())}")
    parser.add_argument("--all", action="store_true", help="爬取全部文档")
    parser.add_argument("--no-db", action="store_true", help="跳过数据库写入")
    return parser.parse_args(argv)


def main():
    args = parse_args()

    scraper = DocScraper()
    targets = []

    if args.all:
        targets = list(DOC_SOURCES.items())
    elif args.name:
        if args.name in DOC_SOURCES:
            targets = [(args.name, DOC_SOURCES[args.name])]
        else:
            print(f"未知文档: {args.name}")
            print(f"可选: {', '.join(DOC_SOURCES.keys())}")
            return
    else:
        print(f"请指定 --name 或 --all")
        print(f"可选: {', '.join(DOC_SOURCES.keys())}")
        return

    results = []
    for item in targets:
        name, info = item
        url, wait = info if isinstance(info, tuple) else (info, 2.0)
        print(f"\n{'='*60}")
        print(f"爬取: {name} <- {url} (wait={wait}s)")
        print(f"{'='*60}")
        r = scraper.scrape(name, url, wait=wait)
        results.append(r)
        print(f"完成: {r['file_count']} 文件, {r['elapsed_seconds']}s")

    if results and not args.no_db:
        print(f"\n写入数据库...")
        save_to_db(results)


if __name__ == "__main__":
    main()
