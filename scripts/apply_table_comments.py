"""注释同步工具：按 migrations/data/table_comments.json 幂等应用表/列注释。

用途：迁移加列（如 0011/0012）不会自动应用注释文件中的新列注释；本工具对
真实库做注释级校正（information_schema 对比，仅不一致列 ALTER，列类型/可空/默认
原样保留）。可重复执行；表/列不存在时跳过。

用法（conda qed_env）：
    conda run -n qed_env python scripts/apply_table_comments.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from qed_tracker.config import load_settings

sys.stdout.reconfigure(encoding="utf-8")

COMMENTS_PATH = Path(__file__).resolve().parent.parent / "src" / "qed_tracker" / "migrations" / "data" / "table_comments.json"


def _default_sql(value, col_type: str) -> str:
    if value is None:
        return ""
    low = col_type.lower()
    if str(value) == "0" and low.startswith(
        ("int", "tinyint", "bigint", "smallint", "float", "double", "decimal", "numeric")
    ):
        return f"DEFAULT {value}"
    if isinstance(value, str):
        return f"DEFAULT '{value.replace(chr(39), chr(39) * 2)}'"
    return f"DEFAULT {value}"


def main() -> int:
    comments = json.loads(COMMENTS_PATH.read_text(encoding="utf-8"))
    s = load_settings()
    url = f"mysql+pymysql://{s.db_user}:{s.db_password}@{s.db_host}:{s.db_port}/{s.db_name}"
    eng = create_engine(url)
    insp = inspect(eng)
    existing_tables = set(insp.get_table_names())
    altered_tables, altered_cols, skipped = 0, 0, []

    with eng.begin() as conn:
        for table, meta in comments.items():
            if table not in existing_tables:
                skipped.append(f"{table}(表不存在)")
                continue
            want_table_comment = (meta.get("table") or "").replace("'", "''")
            conn.execute(text(f"ALTER TABLE `{table}` COMMENT = '{want_table_comment}'"))
            altered_tables += 1
            cols = {
                r["COLUMN_NAME"]: r
                for r in conn.execute(text(
                    "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_COMMENT "
                    "FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
                ), {"t": table}).mappings()
            }
            for col, want in meta.get("columns", {}).items():
                if col not in cols:
                    skipped.append(f"{table}.{col}(列不存在)")
                    continue
                info = cols[col]
                if (info["COLUMN_COMMENT"] or "") == want:
                    continue
                null_sql = "NULL" if info["IS_NULLABLE"] == "YES" else "NOT NULL"
                want_sql = want.replace("'", "''")
                conn.execute(text(
                    f"ALTER TABLE `{table}` MODIFY COLUMN `{col}` {info['COLUMN_TYPE']} "
                    f"{null_sql} {_default_sql(info['COLUMN_DEFAULT'], info['COLUMN_TYPE'])} "
                    f"COMMENT '{want_sql}'"
                ))
                altered_cols += 1

    print(f"表注释已校正：{altered_tables} 张；列注释已更新：{altered_cols} 列")
    if skipped:
        print("跳过：", ", ".join(skipped))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
