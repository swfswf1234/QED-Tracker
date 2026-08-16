"""五层模型一次性存量迁移（QED-031）：math.json → qed_domain/qed_course；三表 → 新表族。

流程（docs/design/database-schema.md §一次性存量迁移）：
1. migrate_curriculum：courses/math.json → qed_domain + qed_course（sort_order=数组序，幂等 upsert；
   重跑会用 math.json 覆盖 name/aliases/stage/note —— 该数据由 math.json 拥有）；
2. migrate_legacy_data：qt_selections → qt_knowledge + 拆书行；qt_downloads → qt_books
   （vol → part，旧 approved → verified，sha256 幂等）；qt_sources 改名 qt_sources_legacy 重建挂 book_id；
3. 旧表（qt_selections / qt_downloads / qt_sources_legacy）默认保留为备份快照，
   确认无误后用户显式 drop_legacy=True 才 drop。

幂等键：knowledge_id = kn_<md5(domain, course, kind, set_no, name)>；book_id = bk_<md5(knowledge_id, title, part)>。
迁移前全量备份快照（服务端脚本执行时由 CLI 提示用户自行 mysqldump，本模块只保证幂等重放）。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.orm import Session

from qed_tracker.database import utc_now
from qed_tracker.db.knowledge_repository import KnowledgeRepository
from qed_tracker.db.models import BookStatus, KnowledgeStatus, QtSource

_VOL_MAP = {"v1": "第一册", "v2": "第二册", "v3": "第三册", "v4": "第四册"}


def _json_or(value: Any, default: Any) -> Any:
    """SQLite 上 JSON 列读回是 TEXT：尝试解析；已解析（list/dict）或解析失败原样返回。"""
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    return value


def _dt_or(value: Any) -> Any:
    """SQLite 上 DATETIME 列读回是 ISO 字符串：转 datetime；已是 datetime/None 原样返回。"""
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    return value


def _table_has_column(session: Session, table_name: str, column_name: str) -> bool:
    """表存在且含指定列（SQLite PRAGMA / MySQL information_schema）。"""
    if session.bind.dialect.name == "mysql":
        return bool(session.execute(text(
            "SELECT COUNT(*) FROM information_schema.columns"
            " WHERE table_schema=DATABASE() AND table_name=:t AND column_name=:c"
        ), {"t": table_name, "c": column_name}).scalar())
    rows = session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(row[1] == column_name for row in rows)


def _domain_for_course(session_factory: Callable[[], Session], course_id: str) -> str:
    """查询 qed_course.domain_id；课程表不存在/为空（未跑 migrate_curriculum）时兜底 math。"""
    with session_factory() as session:
        if not _table_has_column(session, "qed_course", "domain_id"):
            return "math"
        row = session.execute(
            text("SELECT domain_id FROM qed_course WHERE course_id=:c"), {"c": course_id}
        ).fetchone()
        return row[0] if row else "math"


def migrate_curriculum(session_factory: Callable[[], Session], courses_dir: Path | None = None) -> None:
    """courses/math.json → qed_domain + qed_course（幂等 upsert；目录不存在时跳过）。

    courses_dir 默认取包内 courses 目录（`files("qed_tracker").joinpath("courses")`）。
    """
    if courses_dir is None:
        from importlib.resources import files

        courses_dir = Path(str(files("qed_tracker").joinpath("courses")))
    math_json = Path(courses_dir) / "math.json"
    if not math_json.is_file():
        return
    value = json.loads(math_json.read_text(encoding="utf-8"))
    now = utc_now()
    with session_factory() as session:
        domain = session.execute(
            text("SELECT domain_id FROM qed_domain WHERE domain_id=:d"), {"d": value["subject"]}
        ).fetchone()
        if domain is None:
            session.execute(
                text("INSERT INTO qed_domain (domain_id, name, description, stages, created_by,"
                     " updated_by, created_at, updated_at) VALUES (:d, :n, :desc, :stages, '', '', :t, :t)"),
                {"d": value["subject"], "n": value["name"], "desc": value.get("description", ""),
                 "stages": json.dumps(value["stages"], ensure_ascii=False), "t": now},
            )
        else:
            session.execute(
                text("UPDATE qed_domain SET name=:n, description=:desc, stages=:stages, updated_at=:t"
                     " WHERE domain_id=:d"),
                {"d": value["subject"], "n": value["name"], "desc": value.get("description", ""),
                 "stages": json.dumps(value["stages"], ensure_ascii=False), "t": now},
            )
        for index, item in enumerate(value["courses"]):
            existing = session.execute(
                text("SELECT course_id FROM qed_course WHERE course_id=:c"), {"c": item["course_id"]}
            ).fetchone()
            if existing is None:
                session.execute(
                    text("INSERT INTO qed_course (course_id, domain_id, sort_order, name, aliases, stage,"
                         " prerequisites, related_targets, note, created_by, updated_by, created_at, updated_at)"
                         " VALUES (:c, :d, :s, :n, :aliases, :stage, :pre, :rel, :note, '', '', :t, :t)"),
                    {"c": item["course_id"], "d": value["subject"], "s": index, "n": item["name"],
                     "aliases": json.dumps(item.get("aliases", []), ensure_ascii=False),
                     "stage": item["stage"],
                     "pre": json.dumps(item.get("prerequisites", []), ensure_ascii=False),
                     "rel": json.dumps(item.get("related_targets", []), ensure_ascii=False),
                     "note": item.get("note", ""), "t": now},
                )
            else:
                session.execute(
                    text("UPDATE qed_course SET sort_order=:s, name=:n, aliases=:aliases, stage=:stage,"
                         " prerequisites=:pre, related_targets=:rel, note=:note, updated_at=:t"
                         " WHERE course_id=:c"),
                    {"c": item["course_id"], "s": index, "n": item["name"],
                     "aliases": json.dumps(item.get("aliases", []), ensure_ascii=False),
                     "stage": item["stage"],
                     "pre": json.dumps(item.get("prerequisites", []), ensure_ascii=False),
                     "rel": json.dumps(item.get("related_targets", []), ensure_ascii=False),
                     "note": item.get("note", ""), "t": now},
                )
        session.commit()


def _split_title(title: str) -> tuple[str, str]:
    """拆分卷名 → (title, part)：'微积分学教程 第一册' → ('微积分学教程', '第一册')。"""
    for token in ("第一册", "第二册", "第三册", "第四册", "上册", "下册"):
        if token in title:
            return title.replace(token, "").strip(), token
    return title.strip(), ""


def _ensure_qt_sources(session_factory: Callable[[], Session]) -> None:
    """确保新结构 qt_sources 表存在：0006 迁移故意不建（改挂 book_id 由本脚本重建），
    全新库也要补建，否则后续 repo.add_source 会因表缺失失败。"""
    with session_factory() as session:
        if not sa.inspect(session.bind).has_table("qt_sources"):
            QtSource.__table__.create(session.bind)


def migrate_legacy_data(session_factory: Callable[[], Session], *, drop_legacy: bool = False) -> dict[str, int]:
    """三表存量 → 五表（幂等重放）；drop_legacy=True 时确认后 drop 旧表。返回统计。"""
    repo = KnowledgeRepository(session_factory)
    stats = {"knowledge": 0, "books": 0, "sources": 0}
    with session_factory() as session:
        has_legacy = _table_has_column(session, "qt_selections", "selection_id")
    if not has_legacy:
        # 全新库（无旧表）：无数据可迁，仍要补建新结构 qt_sources（0006 未建）供 add_source 使用。
        _ensure_qt_sources(session_factory)
        return stats
    with session_factory() as session:
        dialect = session.bind.dialect.name
        selections = session.execute(
            text("SELECT * FROM qt_selections ORDER BY created_at")
        ).mappings().all()
        downloads = session.execute(
            text("SELECT * FROM qt_downloads ORDER BY created_at")
        ).mappings().all()
        # sources 阶段选源：改名后中断时旧行留在 qt_sources_legacy，续跑直接读它（改名步骤为 no-op）；
        # 否则旧结构 qt_sources 仍可读 → 读后改名；两者都没有 → 已迁移/无源可迁。
        if _table_has_column(session, "qt_sources_legacy", "download_id"):
            sources_rows: list[dict[str, Any]] = [dict(row) for row in session.execute(
                text("SELECT * FROM qt_sources_legacy")).mappings().all()]
            rename_needed = False
        elif _table_has_column(session, "qt_sources", "download_id"):
            sources_rows = [dict(row) for row in session.execute(
                text("SELECT * FROM qt_sources")).mappings().all()]
            rename_needed = True
        else:
            sources_rows = []
            rename_needed = False

    book_rows: dict[str, dict[str, Any]] = {dl["download_id"]: dict(dl) for dl in downloads}

    for selection in selections:
        title = selection["title"]
        base_title, part = _split_title(title)
        if base_title != title:
            title = base_title
        knowledge = repo.create_knowledge(
            domain_id=_domain_for_course(session_factory, selection["course_id"]),
            course_id=selection["course_id"],
            kind="tutorial",
            set_no=selection.get("set_no") or "",
            name=f"{title} 套{selection.get('set_no', '')}" if selection.get("set_no") else title,
        )
        stats["knowledge"] += 1
        # 旧 confirmed → confirmed（简介留空待 LLM 预填）；已确认行跳过（幂等重放，不触发状态机异常）
        if selection["status"] == KnowledgeStatus.CONFIRMED.value and knowledge.status == KnowledgeStatus.DRAFT.value:
            repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref={}, exercise_ref={})
        for dl in [v for v in book_rows.values() if v["selection_id"] == selection["selection_id"]]:
            vol_part = _VOL_MAP.get(dl["vol"] or "", "") or part
            book = repo.create_book(
                knowledge.knowledge_id,
                kind="textbook",
                roles=_json_or(dl.get("roles"), None) or _json_or(selection.get("roles"), None) or ["textbook"],
                title=title,
                part=vol_part,
                authors=_json_or(selection.get("authors"), []),
                version=_json_or(selection.get("version"), {}),
            )
            stats["books"] += 1
            if dl["sha256"] and book.sha256 is None:
                book = repo.complete_download(
                    book.book_id,
                    sha256=dl["sha256"],
                    relative_path=dl.get("relative_path") or "",
                    page_count=dl.get("page_count"),
                )
            if dl["status"] == "approved" and book.status == BookStatus.DOWNLOADED.value:
                repo.verify_book(book.book_id)
            if dl["status"] == "rejected" and dl.get("reject_reason") and book.status not in (
                BookStatus.REJECTED.value, BookStatus.SUPERSEDED.value, BookStatus.VERIFIED.value
            ):
                repo.reject_book(book.book_id, reason=dl["reject_reason"], by=dl.get("rejected_by") or "migrate")
            book_rows[dl["download_id"]]["new_book_id"] = book.book_id

    # qt_sources：旧表改名留档 → 建新结构表（0006 未建，MySQL/SQLite 统一处理）→ 按
    # download_id → new_book_id 映射重挂。qt_sources_legacy 默认保留为备份快照，只有
    # drop_legacy=True 才 drop。幂等：续跑从 qt_sources_legacy 读旧行重放，改名步骤 no-op。
    if rename_needed:
        with session_factory() as session:
            if dialect == "mysql":
                session.execute(text("RENAME TABLE qt_sources TO qt_sources_legacy"))
            else:
                session.execute(text("ALTER TABLE qt_sources RENAME TO qt_sources_legacy"))
            session.commit()
    _ensure_qt_sources(session_factory)
    for src in sources_rows:
        new_book_id = book_rows.get(src["download_id"], {}).get("new_book_id")
        if not new_book_id:
            continue
        repo.add_source(
            new_book_id,
            channel=src["channel"],
            provider_id=src.get("provider_id", ""),
            page_url=src.get("page_url", ""),
            download_url=src.get("download_url", ""),
            file_keywords=src.get("file_keywords", ""),
            ok=bool(src.get("ok")),
            note=src.get("note", ""),
            attempted_at=_dt_or(src.get("attempted_at")),
        )
        stats["sources"] += 1
    if drop_legacy:
        with session_factory() as session:
            session.execute(text("DROP TABLE IF EXISTS qt_sources_legacy"))
            session.execute(text("DROP TABLE IF EXISTS qt_downloads"))
            session.execute(text("DROP TABLE IF EXISTS qt_selections"))
            session.commit()
    return stats