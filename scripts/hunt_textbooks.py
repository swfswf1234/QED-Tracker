"""教材检索入口 — 一次性运行

遍历所有课程，搜索目标教材 PDF，下载到 dataset/textbooks/（路径由 setting.ini 中 dataset_dir 配置）。

用法:
    python scripts/hunt_textbooks.py                  # 遍历全部，交互式
    python scripts/hunt_textbooks.py --auto           # 自动模式
    python scripts/hunt_textbooks.py --course 03      # 仅检索第3门课
    python scripts/hunt_textbooks.py --no-db          # 跳过数据库写入
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
from loguru import logger

from app.core.config import settings
from app.core.utils import setup_console_utf8
from app.core.database import get_conn, init_tables, check_db
from app.collectors.textbook_hunter import TextbookHunter
from app.curricula.math_qe import MATH_QE
from app.repository.textbook_repo import TextbookRepo
from app.models.textbook import Textbook


def save_to_db(results: list[dict]):
    if not results:
        return
    db = get_conn()
    try:
        init_tables()
        repo = TextbookRepo(db)
        imported = 0
        for r in results:
            if repo.exists_by_path(r.get("local_path", "")):
                continue
            repo.create(Textbook(
                id=None,
                course=r.get("course", ""),
                title=r.get("title", "")[:200],
                author=r.get("author", "")[:100],
                language=r.get("language", "en"),
                source="libgen",
                source_url=r.get("download_url", ""),
                local_pdf_path=r.get("local_path", ""),
                notes=r.get("_confidence", ""),
            ))
            imported += 1
        print(f"  入库: {imported} 条")
    except Exception as e:
        db.rollback()
        print(f"  [数据库错误] {e}")
    finally:
        db.close()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="教材检索")
    parser.add_argument("--course", type=str, help="课程编号 (如 03, 04)，不传则遍历全部")
    parser.add_argument("--no-db", action="store_true", help="跳过数据库写入")
    parser.add_argument("--auto", action="store_true", help="自动模式：自动选择第一个 PDF，跳过交互")
    return parser.parse_args(argv)


def main():
    setup_console_utf8()
    args = parse_args()

    hunter = TextbookHunter(proxy=settings.http_proxy)
    all_results = []

    if args.course:
        prefix = args.course.zfill(2)
        courses = [c for c in MATH_QE.courses if c.id.startswith(prefix)]
        if not courses:
            print(f"未找到课程编号 '{args.course}'")
            print(f"可用: {', '.join(c.id for c in MATH_QE.courses)}")
            return
    else:
        courses = MATH_QE.courses

    for course in courses:
        if args.auto:
            results = hunter.hunt_course(course, auto=True)
        else:
            results = hunter.hunt_course(course, auto=False)
        all_results.extend(results)

    hunter.close()

    print(f"\n{'='*60}")
    print(f"总计下载: {len(all_results)} 个文件")

    if all_results and not args.no_db:
        print(f"\n写入数据库...")
        save_to_db(all_results)


if __name__ == "__main__":
    main()
