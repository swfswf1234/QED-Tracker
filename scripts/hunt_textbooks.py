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

from app.core.config import settings
from app.core.utils import setup_console_utf8
from app.core.database import get_conn, init_tables
from app.collectors.textbook_hunter import DownloadAttempt, DownloadStatus, TextbookHunter
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
            notes = r.get("_confidence", "")
            if r.get("_status"):
                notes = " | ".join(part for part in [notes, r.get("_status"), r.get("_reason", "")] if part)
            repo.create(Textbook(
                id=None,
                course=r.get("course", ""),
                title=r.get("title", "")[:200],
                author=r.get("author", "")[:100],
                language=r.get("language", "en"),
                source=r.get("source", "libgen"),
                source_url=r.get("download_url", ""),
                local_pdf_path=r.get("local_path", ""),
                notes=notes,
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
    parser.add_argument("--one-click", action="store_true", help="严格一键补缺：已有跳过，找不到 PASS，继续下一项")
    parser.add_argument("--missing-only", action="store_true", help="只处理本地缺失目标；和 --one-click 搭配时默认启用")
    parser.add_argument("--report", type=str, default="", help="写入 Markdown 下载报告")
    return parser.parse_args(argv)


def _attempts_to_markdown(attempts: list[DownloadAttempt]) -> str:
    lines = [
        "# Textbook Download Report",
        "",
        "| Course | Target | Source | Status | Local Path | Reason |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for a in attempts:
        target = f"{a.target_title} ({a.target_author})" if a.target_author else a.target_title
        lines.append(
            f"| {a.course} | {target} | {a.source} | {a.status.value} | "
            f"{a.local_path or '-'} | {a.reason or '-'} |"
        )
    return "\n".join(lines) + "\n"


def write_report(attempts: list[DownloadAttempt], report_path: str):
    path = Path(report_path)
    if not path.is_absolute():
        path = settings.project_root / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_attempts_to_markdown(attempts), encoding="utf-8")
    print(f"报告: {path}")


def print_attempt_summary(attempts: list[DownloadAttempt]):
    for a in attempts:
        target = f"{a.target_title} / {a.target_author}" if a.target_author else a.target_title
        path = f" -> {a.local_path}" if a.local_path else ""
        print(f"[{a.status.value}] {a.course} | {target} | {a.source}{path} | {a.reason}")
    counts = {}
    for a in attempts:
        counts[a.status.value] = counts.get(a.status.value, 0) + 1
    print("\n汇总: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))


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

    if args.one_click:
        attempts = hunter.one_click_all(courses, missing_only=True)
        hunter.close()
        print_attempt_summary(attempts)
        all_results = [a.as_result() for a in attempts if a.status == DownloadStatus.SUCCESS]
        if args.report:
            write_report(attempts, args.report)
    else:
        for course in courses:
            if args.auto:
                results = hunter.hunt_course(course, auto=True)
            else:
                results = hunter.hunt_course(course, auto=False)
            all_results.extend(results)

        hunter.close()

    if not args.one_click:
        print(f"\n{'='*60}")
        print(f"总计下载: {len(all_results)} 个文件")
    else:
        print(f"\n总计下载: {len(all_results)} 个文件")

    if all_results and not args.no_db:
        print(f"\n写入数据库...")
        save_to_db(all_results)


if __name__ == "__main__":
    main()
