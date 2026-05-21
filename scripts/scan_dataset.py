"""扫描已有 dataset 文件 → 录入 PostgreSQL

用法:
    python scripts/scan_dataset.py            # 扫描并写入数据库
    python scripts/scan_dataset.py --dry-run  # 仅预览，不写入
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
from datetime import date
from loguru import logger

from app.core.config import settings
from app.core.database import get_conn, init_tables, check_db
from app.repository.textbook_repo import TextbookRepo
from app.repository.paper_repo import PaperRepo
from app.repository.doc_repo import OfficialDocRepo
from app.models.textbook import Textbook
from app.models.paper import Paper
from app.models.official_doc import OfficialDoc


COURSE_NAMES = {
    "01_math_analysis": "数学分析",
    "02_linear_algebra": "线性代数",
    "03_topology": "点集拓扑",
    "04_real_analysis": "实分析",
    "05_complex_analysis": "复分析",
    "06_functional_analysis": "泛函分析",
    "07_ode": "常微分方程",
    "08_pde": "偏微分方程",
    "09_abstract_algebra": "抽象代数",
    "10_qe_prep": "QE冲刺",
}

STAGE_MAP = {
    "01": "地基", "02": "地基", "03": "地基",
    "04": "核心", "05": "核心", "06": "核心",
    "07": "广度", "08": "广度", "09": "广度",
    "10": "冲刺",
}


def scan_textbooks(dry_run: bool) -> list[Textbook]:
    textbooks_dir = settings.dataset_path / "textbooks"
    if not textbooks_dir.exists():
        print(f"[教材目录不存在] {textbooks_dir}")
        return []

    found = []
    for course_dir in sorted(textbooks_dir.iterdir()):
        if not course_dir.is_dir():
            continue
        course_code = course_dir.name
        course_name = COURSE_NAMES.get(course_code, course_code)

        pdfs = sorted(course_dir.glob("*.pdf"))
        if not pdfs:
            continue

        print(f"\n  {course_code} ({course_name}): {len(pdfs)} 个 PDF")
        for pdf in pdfs:
            rel_path = pdf.relative_to(settings.dataset_path)
            rel_str = str(rel_path.as_posix())

            has_solution = "习题" in pdf.stem or "solution" in pdf.stem.lower()

            t = Textbook(
                id=None,
                course=course_code,
                title=pdf.stem,
                author="",
                language="zh" if "中" in pdf.stem or any(c > '\u4e00' for c in pdf.stem) else "en",
                source="已有",
                local_pdf_path=rel_str,
                local_solution_path=rel_str if has_solution else None,
                stage=STAGE_MAP.get(course_code[:2], ""),
            )
            found.append(t)
            print(f"    {'[习题]' if has_solution else '[教材]'} {pdf.name}")

    return found


def scan_papers(dry_run: bool) -> list[Paper]:
    papers_dir = settings.dataset_path / "papers"
    if not papers_dir.exists():
        return []
    found = []
    for year_dir in sorted(papers_dir.iterdir()):
        if not year_dir.is_dir():
            continue
        for pdf in year_dir.glob("*.pdf"):
            local_path = str(pdf.relative_to(settings.dataset_path).as_posix())
            arxiv_id = pdf.stem.split("_")[0] if "_" in pdf.stem else pdf.stem
            found.append(Paper(
                id=None, arxiv_id=arxiv_id, title=pdf.stem,
                local_path=local_path,
            ))
    return found


def scan_official_docs(dry_run: bool) -> list[OfficialDoc]:
    docs_dir = settings.dataset_path / "official_docs"
    if not docs_dir.exists():
        return []
    found = []
    for sub in sorted(docs_dir.iterdir()):
        if not sub.is_dir():
            continue
        file_count = sum(1 for _ in sub.rglob("*") if _.is_file())
        local_path = str(sub.relative_to(settings.dataset_path).as_posix())
        found.append(OfficialDoc(
            id=None, name=sub.name, local_path=local_path,
            pages_count=file_count,
        ))
    return found


def main():
    parser = argparse.ArgumentParser(description="扫描 dataset 文件入库")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不写入数据库")
    args = parser.parse_args()

    print(f"数据集路径: {settings.dataset_path}")
    print(f"模式: {'预览 (dry-run)' if args.dry_run else '写入数据库'}")

    # 扫描
    textbooks = scan_textbooks(args.dry_run)
    papers = scan_papers(args.dry_run)
    docs = scan_official_docs(args.dry_run)

    print(f"\n总计: {len(textbooks)} 教材, {len(papers)} 论文, {len(docs)} 文档")

    # 写入
    if not args.dry_run and (textbooks or papers or docs):
        if not check_db():
            print("\n[数据库未连接] 请先运行 init_db.py")
            return

        db = get_conn()
        try:
            init_tables()
            tr = TextbookRepo(db)
            pr = PaperRepo(db)
            dr = OfficialDocRepo(db)

            imported = {"textbooks": 0, "papers": 0, "docs": 0}

            for t in textbooks:
                if not tr.exists_by_path(t.local_pdf_path):
                    tr.create(t)
                    imported["textbooks"] += 1

            for p in papers:
                if not pr.exists_by_arxiv_id(p.arxiv_id):
                    pr.create(p)
                    imported["papers"] += 1

            for d in docs:
                dr.create(d)
                imported["docs"] += 1

            print(f"\n已导入: {imported['textbooks']} 教材, {imported['papers']} 论文, {imported['docs']} 文档")
        except Exception as e:
            db.rollback()
            print(f"\n[错误] 导入失败: {e}")
        finally:
            db.close()


if __name__ == "__main__":
    main()
