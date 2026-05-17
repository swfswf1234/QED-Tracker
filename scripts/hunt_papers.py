"""arXiv 论文检索入口 — 手动运行

用法:
    python scripts/hunt_papers.py --domain math.CA --max 10
    python scripts/hunt_papers.py --domain math.FA --max 20
    python scripts/hunt_papers.py --all-domains     # 遍历所有数学领域
    python scripts/hunt_papers.py --llm             # 遍历 LLM 领域
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
from loguru import logger

from app.core.config import settings
from app.core.database import get_conn, init_tables
from app.collectors.paper_collector import PaperCollector
from app.repository.paper_repo import PaperRepo
from app.models.paper import Paper


def save_to_db(papers: list[dict]):
    db = get_conn()
    try:
        init_tables()
        repo = PaperRepo(db)
        imported = 0
        for p in papers:
            if repo.exists_by_arxiv_id(p.get("arxiv_id", "")):
                print(f"  [已存在] {p.get('arxiv_id')}")
                continue
            repo.create(Paper(
                id=None,
                arxiv_id=p.get("arxiv_id", ""),
                title=p.get("title", ""),
                authors=p.get("authors", []),
                categories=p.get("categories", []),
                published_date=p.get("published_date"),
                source_url=p.get("source_url", ""),
                local_path=p.get("local_path", ""),
            ))
            imported += 1
        print(f"  入库: {imported} 篇")
    except Exception as e:
        db.rollback()
        print(f"  [数据库错误] {e}")
    finally:
        db.close()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="arXiv 论文检索")
    parser.add_argument("--domain", type=str, help=f"数学分类 (e.g. math.CA)")
    parser.add_argument("--max", type=int, default=10, help="最大检索数量")
    parser.add_argument("--all-domains", action="store_true", help="遍历所有已配置数学领域")
    parser.add_argument("--llm", action="store_true", help="遍历 LLM 领域 (cs.LG/CL/CV/AI)")
    parser.add_argument("--no-db", action="store_true", help="跳过数据库写入")
    return parser.parse_args(argv)


def main():
    args = parse_args()

    collector = PaperCollector()
    domains = []

    if args.all_domains:
        domains = settings.arxiv_math_domains
    elif args.llm:
        domains = settings.arxiv_llm_domains
    elif args.domain:
        domains = [args.domain]
    else:
        print(f"请指定 --domain, --all-domains 或 --llm")
        print(f"数学领域: {', '.join(settings.arxiv_math_domains)}")
        print(f"LLM 领域: {', '.join(settings.arxiv_llm_domains)}")
        return

    all_downloaded = []
    for domain in domains:
        print(f"\n{'='*60}")
        print(f"检索: {domain}")
        print(f"{'='*60}")
        downloaded = collector.interactive_search(domain, args.max)
        all_downloaded.extend(downloaded)

    print(f"\n{'='*60}")
    print(f"总计: 下载 {len(all_downloaded)} 篇")

    if all_downloaded and not args.no_db:
        print(f"\n写入数据库...")
        save_to_db(all_downloaded)


if __name__ == "__main__":
    main()
