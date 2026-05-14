"""教材检索入口 — 一次性运行

遍历所有课程，搜索目标教材 PDF，下载到 dataset/textbooks/。

用法:
    python scripts/hunt_textbooks.py                  # 遍历所有课程
    python scripts/hunt_textbooks.py --course 03      # 仅检索第3门课
    python scripts/hunt_textbooks.py --no-db          # 跳过数据库写入
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import re
from loguru import logger

from app.core.config import settings
from app.core.database import get_conn, init_tables, check_db
from app.collectors.textbook_hunter import TextbookHunter, TEXTBOOK_TARGETS
from app.repository.textbook_repo import TextbookRepo
from app.models.textbook import Textbook


COURSE_LIST = sorted(TEXTBOOK_TARGETS.keys())


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
                stage="",
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
    parser.add_argument("--course", type=str, help=f"课程编号 (如 03, 04)，不传则遍历全部")
    parser.add_argument("--no-db", action="store_true", help="跳过数据库写入")
    return parser.parse_args(argv)


def main():
    args = parse_args()

    hunter = TextbookHunter(proxy=settings.http_proxy)
    all_results = []

    if args.course:
        prefix = args.course.zfill(2)
        courses = [c for c in COURSE_LIST if c.startswith(prefix)]
        if not courses:
            print(f"未找到课程编号 '{args.course}'")
            print(f"可用: {', '.join(COURSE_LIST)}")
            return
    else:
        courses = COURSE_LIST

    for course in courses:
        targets = TEXTBOOK_TARGETS.get(course, {})
        zh_q = targets.get("zh", "")
        en_q = targets.get("en", "").split(";")[0].strip() if targets.get("en") else ""
        zh_ex = targets.get("zh_exercise", "")

        # 1. 搜索中文教材
        if zh_q:
            print(f"\n{'='*60}")
            print(f"课程: {course} (中文教材: {zh_q})")
            print(f"{'='*60}")
            all_results.extend(hunter.interactive_search(course, zh_q))

        # 2. 搜索英文教材
        if en_q:
            print(f"\n{'='*60}")
            print(f"课程: {course} (英文教材: {en_q})")
            print(f"{'='*60}")
            all_results.extend(hunter.interactive_search(course, en_q))

        # 3. 搜索习题集
        if zh_ex:
            print(f"\n{'='*60}")
            print(f"课程: {course} (习题集: {zh_ex})")
            print(f"{'='*60}")
            all_results.extend(hunter.interactive_search(course, zh_ex))

    hunter.libgen.close()
    hunter.anna.close()

    print(f"\n{'='*60}")
    print(f"总计下载: {len(all_results)} 个文件")

    if all_results and not args.no_db:
        print(f"\n写入数据库...")
        save_to_db(all_results)


if __name__ == "__main__":
    main()
