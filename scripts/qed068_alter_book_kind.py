"""QED-068 A 步：给 qt_books 加 kind / course_id 两列（先备份后 ALTER，幂等）。

红线顺序见 docs/architecture/database-private-tables.md「论文书本化列契约」节：
① 备份 qt_books → ② ALTER 磁盘表 → ③ 才改 models.py → ④ ensure_schema 返回 (0, 0)。
本脚本承担 ①②④（④ 为只读核验）；③ 是同批代码改动，不在脚本内。

备份落点：默认仓库 ``tmp/backups/<日期>-qed068-paper-kind/qt_books.sql``（本机联调库）；
生产窗口按 B 轮惯例用 ``--backup-dir`` 指到 ``<data_root>/backups/<日期>-qed068-paper-kind/``。

用法::

    python scripts/qed068_alter_book_kind.py --dry-run   # 只看现状与待执行 SQL
    python scripts/qed068_alter_book_kind.py             # 备份 + ALTER + 核验
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import sqlalchemy as sa  # noqa: E402

from qed_tracker.config import load_settings  # noqa: E402
from qed_tracker.db.engine import create_engine_for  # noqa: E402

TABLE = "qt_books"
NEW_COLUMNS: dict[str, str] = {
    "kind": (
        "VARCHAR(16) NOT NULL DEFAULT 'book' COMMENT "
        "'书目类别：book=教材/习题集/题解等书本；paper=发现论文（QED-068 068-6b 书本化采纳）'"
    ),
    "course_id": (
        "VARCHAR(64) NOT NULL DEFAULT '' COMMENT "
        "'落位课程标识：空串=领域级（归属见 domain_id）；论文 pick 逐条落位（068-6b）'"
    ),
}
NEW_INDEXES: dict[str, str] = {
    "ix_qt_books_kind": "kind",
    "ix_qt_books_course_id": "course_id",
}


def _quote(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime):
        return "'" + value.strftime("%Y-%m-%d %H:%M:%S") + "'"
    text = str(value).replace("\\", "\\\\").replace("'", "''")
    return f"'{text}'"


def backup_table(engine: sa.Engine, backup_dir: Path) -> Path:
    """把 qt_books 全表导出为可重放的 INSERT 脚本，返回文件路径。"""
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"{TABLE}.sql"
    inspector = sa.inspect(engine)
    columns = [c["name"] for c in inspector.get_columns(TABLE)]
    lines = [
        "-- qt_books 备份（QED-068 A 步 ALTER 前）",
        f"-- 生成时间：{datetime.now(UTC).isoformat(timespec='seconds')}",
        f"-- 库：{engine.url.database}；列数：{len(columns)}",
        "",
    ]
    with engine.connect() as conn:
        rows = conn.execute(sa.text(f"SELECT * FROM {TABLE}")).mappings().all()
    for row in rows:
        values = ", ".join(_quote(row[col]) for col in columns)
        lines.append(
            f"INSERT INTO {TABLE} ({', '.join(columns)}) VALUES ({values});"
        )
    lines.append(f"-- 共 {len(rows)} 行")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def existing_indexes(engine: sa.Engine) -> set[str]:
    return {ix["name"] for ix in sa.inspect(engine).get_indexes(TABLE)}


def run(*, dry_run: bool, backup_dir: Path) -> int:
    settings = load_settings()
    if not settings.db_configured:
        print("数据库未配置（QED_DB_PASSWORD 缺失），拒绝执行。")
        return 2
    engine = create_engine_for(settings)
    try:
        inspector = sa.inspect(engine)
        if not inspector.has_table(TABLE):
            print(f"库 {settings.db_name} 无 {TABLE} 表；先启动一次服务建表再执行本脚本。")
            return 2
        columns = {c["name"] for c in inspector.get_columns(TABLE)}
        missing_cols = [name for name in NEW_COLUMNS if name not in columns]
        indexes = existing_indexes(engine)
        missing_idx = [name for name in NEW_INDEXES if name not in indexes]
        with engine.connect() as conn:
            total = conn.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE}")).scalar()

        print(f"目标库：{settings.db_name}；{TABLE} 现有 {len(columns)} 列 / {total} 行")
        print(f"待加列：{missing_cols or '（无，已存在）'}")
        print(f"待加索引：{missing_idx or '（无，已存在）'}")
        if not missing_cols and not missing_idx:
            print("幂等：无需改动。")
            return 0

        statements = [
            f"ALTER TABLE {TABLE} ADD COLUMN {name} {ddl}" for name, ddl in NEW_COLUMNS.items()
            if name in missing_cols
        ] + [
            f"CREATE INDEX {name} ON {TABLE} ({col})"
            for name, col in NEW_INDEXES.items() if name in missing_idx
        ]
        if dry_run:
            print("\n--dry-run：不执行，仅列出 SQL")
            for statement in statements:
                print(statement + ";")
            return 0

        target = backup_table(engine, backup_dir)
        print(f"① 备份完成：{target}（{total} 行）")
        with engine.begin() as conn:
            for statement in statements:
                print(f"② 执行：{statement}")
                conn.execute(sa.text(statement))

        after = {c["name"] for c in sa.inspect(engine).get_columns(TABLE)}
        with engine.connect() as conn:
            rows_after = conn.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE}")).scalar()
        ok = set(NEW_COLUMNS) <= after and set(NEW_INDEXES) <= existing_indexes(engine)
        print(
            f"④ 核验：列数 {len(after)}、行数 {rows_after}（改前 {total}）、"
            f"两列两索引齐备={ok}"
        )
        if rows_after != total or not ok:
            print("核验失败：请立刻用备份文件回滚并排查。")
            return 1
        print("完成。下一步：改 models.py 后启动服务，确认 ensure_schema 返回 (0, 0)。")
        return 0
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="只报告现状与待执行 SQL")
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=None,
        help="备份目录（默认 仓库 tmp/backups/<日期>-qed068-paper-kind/）",
    )
    args = parser.parse_args()
    default_dir = (
        REPO_ROOT / "tmp" / "backups"
        / f"{datetime.now(UTC).strftime('%Y-%m-%d')}-qed068-paper-kind"
    )
    return run(dry_run=args.dry_run, backup_dir=args.backup_dir or default_dir)


if __name__ == "__main__":
    raise SystemExit(main())
