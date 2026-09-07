"""知识/书库/渠道（qt_knowledge / qt_books / qt_sources）数据访问与状态机。

结构（docs/architecture/database-private-tables.md）：
qed_domain → qed_course → qt_knowledge（一行=一套教程/一组延展资料归类）→ qt_books
（一行=域级书库一册）→ qt_sources（渠道尝试）。

状态机：
- qt_knowledge：draft → confirmed。confirmed 为终态。
- qt_books：candidate → decided / parallel；candidate/decided/parallel → retired。
  retired 为终态。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable
from typing import Any

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from qed_tracker.db.engine import utc_now
from qed_tracker.db.models import BookStatus, KnowledgeStatus, QedCourse, QedDomain, QtBook, QtKnowledge, QtSource


class InvalidTransition(RuntimeError):
    """状态机迁移非法。"""


class DomainNotEmpty(RuntimeError):
    """删除非空领域（仍有课程）。"""


class CourseHasKnowledge(RuntimeError):
    """删除有教程的课程。"""


class AdoptionConflict(RuntimeError):
    """A2 采纳冲突：同课程套号已被不同教程占用。"""


class InvalidExplorationTransition(RuntimeError):
    """探索状态迁移非法：当前态不允许执行该操作（REQ-067-B12）。"""


# Sentinel to distinguish "not provided" from "explicitly set to None".
_MISSING = object()
# Special value to explicitly clear explore_pending to NULL.
CLEAR = "__CLEAR__"

_KNOWLEDGE_TRANSITIONS: dict[KnowledgeStatus, set[KnowledgeStatus]] = {
    KnowledgeStatus.DRAFT: {KnowledgeStatus.CONFIRMED},
    KnowledgeStatus.CONFIRMED: set(),
}

_BOOK_TRANSITIONS: dict[BookStatus, set[BookStatus]] = {
    BookStatus.CANDIDATE: {BookStatus.DECIDED, BookStatus.PARALLEL, BookStatus.RETIRED},
    BookStatus.DECIDED: {BookStatus.RETIRED},
    BookStatus.PARALLEL: {BookStatus.RETIRED},
    BookStatus.RETIRED: set(),
}


def _id(prefix: str, *parts: Any) -> str:
    key = json.dumps(parts, ensure_ascii=False, sort_keys=True)
    return f"{prefix}_{hashlib.md5(key.encode('utf-8')).hexdigest()}"


_KNOWLEDGE_ID_RE = re.compile(r"^kt-[0-9a-z]+-[0-9a-z]{1,4}$")
"""数据文件版 knowledge_id 格式：kt-{abbr}-{set_no}（D4，2026-09-03 裁决）。"""

_BOOK_ID_RE = re.compile(r"^[0-9a-z]+-b\d{2,}$")
"""数据文件版 book_id 格式：{abbr}-b{NN}（NN 两位起，域内全局递增）。"""


def _tutorial_knowledge_id(course_id: str, set_no: str) -> str:
    """LLM 采纳路径 knowledge_id：kt-{course_id 去下划线}-{set_no}（D4 裁决，不维护人工映射表）。

    set_no 为空（资料归类行）时退回 md5 后缀避免同课程多行冲突。
    """
    if set_no:
        return f"kt-{course_id.replace('_', '')}-{set_no}"
    return _id("kt", course_id)


def _refs_book_ids(*ref_lists: list[dict[str, Any]] | None) -> list[str]:
    """从 refs 数组（textbook_ref/exercise_ref/parallel_ref）聚合 book_id，保序去重。

    书库化后 QtBook 无 knowledge_id 列，教程与书的归属由 refs 承载。
    """
    ids: list[str] = []
    for refs in ref_lists:
        for ref in refs or []:
            book_id = str(ref.get("book_id") or "")
            if book_id and book_id not in ids:
                ids.append(book_id)
    return ids


def tutorial_name(set_no: str, title: str, authors: Iterable[str] = ()) -> str:
    """教程行规范命名（QED-036/REQ-041）：「教程{set_no}：书名（作者）」。

    - `set_no` "1"~"4" 中文套 → `教程{set_no}：…`；`en` 英文对照套 → `教程en：…`；
      '' 空（资料/异常行兜底）→ `教程：…`；
    - 作者取决定引用 `textbook_ref.authors`，无作者时省略（`教程{set_no}：书名`）；
    - 书名已含同名「（作者）」后缀（如存量 `数学分析（陈纪修）`）时不重复拼接；
    - `other_material` 归类名不加前缀，不适用本函数。
    """
    joined = "、".join(author for author in authors if author)
    prefix = f"教程{set_no}" if set_no else "教程"
    if joined:
        if title.endswith(f"（{joined}）"):
            return f"{prefix}：{title}"
        return f"{prefix}：{title}（{joined}）"
    return f"{prefix}：{title}"


def _touch(row, *, created: bool = False) -> None:
    now = utc_now()
    if created:
        row.created_at = now
    row.updated_at = now


class KnowledgeRepository:
    """五表数据访问；session_factory 注入以便单元测试用 SQLite mock。"""

    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    @property
    def session_factory(self) -> Callable[[], Session]:
        """公开只读访问：探索域组合操作需与教程共享同一事务工厂。"""
        return self._session_factory

    # ---------------- 共享表只读（qed_domain / qed_course 所有权在建表与种子脚本） ----------------

    def list_domains(self) -> list[QedDomain]:
        with self._session_factory() as session:
            return list(session.scalars(select(QedDomain).order_by(QedDomain.domain_id)))

    def list_courses(self, domain_id: str = "") -> list[QedCourse]:
        with self._session_factory() as session:
            statement = select(QedCourse).order_by(QedCourse.sort_order)
            if domain_id:
                statement = statement.where(QedCourse.domain_id == domain_id)
            return list(session.scalars(statement))

    def get_domain(self, domain_id: str) -> QedDomain | None:
        with self._session_factory() as session:
            return session.get(QedDomain, domain_id)

    def get_course(self, course_id: str) -> QedCourse | None:
        with self._session_factory() as session:
            return session.get(QedCourse, course_id)

    def create_domain(
        self,
        *,
        domain_id: str,
        name: str,
        description: str = "",
        stages: list[str] | None = None,
        level: str = "",
        scope: str = "",
        classic_tracks: list[dict[str, Any]] | None = None,
    ) -> QedDomain:
        """幂等插入：已存在则返回既有行（对齐 create_knowledge 模式）。"""
        with self._session_factory() as session:
            existing = session.get(QedDomain, domain_id)
            if existing is not None:
                return existing
            row = QedDomain(
                domain_id=domain_id,
                name=name,
                description=description,
                stages=stages or [],
                level=level,
                scope=scope,
                classic_tracks=classic_tracks or [],
                created_by="api",
                updated_by="api",
            )
            _touch(row, created=True)
            session.add(row)
            session.commit()
            return row

    def create_course(
        self,
        *,
        course_id: str,
        domain_id: str,
        name: str,
        stage: str = "",
        sort_order: int = 0,
        prerequisites: list[str] | None = None,
        aliases: list[str] | None = None,
        description: str = "",
        track: str = "",
    ) -> QedCourse:
        """幂等插入：已存在则返回既有行（对齐 create_knowledge 模式）。"""
        with self._session_factory() as session:
            existing = session.get(QedCourse, course_id)
            if existing is not None:
                return existing
            row = QedCourse(
                course_id=course_id,
                domain_id=domain_id,
                name=name,
                stage=stage,
                sort_order=sort_order,
                prerequisites=prerequisites or [],
                aliases=aliases or [],
                related_targets=[],
                description=description,
                track=track,
                created_by="api",
                updated_by="api",
            )
            _touch(row, created=True)
            session.add(row)
            session.commit()
            return row

    def update_domain(self, domain_id: str, *, description: str | None = None,
                      stages: list[str] | None = None, level: str | None = None,
                      scope: str | None = None,
                      classic_tracks: list[dict[str, Any]] | None = None,
                      path_results: dict[str, Any] | None = None,
                      exploration_stage: str | None = None,
                      explore_pending: dict[str, Any] | None = _MISSING) -> QedDomain:
        """更新领域（name 不可变；path_results/exploration_stage/explore_pending 属探索产物，本仓库写方）。"""
        with self._session_factory() as session:
            row = session.get(QedDomain, domain_id)
            if row is None:
                raise KeyError(f"领域不存在：{domain_id}")
            if description is not None:
                row.description = description
            if stages is not None:
                row.stages = stages
            if level is not None:
                row.level = level
            if scope is not None:
                row.scope = scope
            if classic_tracks is not None:
                row.classic_tracks = classic_tracks
            if path_results is not None:
                row.path_results = path_results
            if exploration_stage is not None:
                row.exploration_stage = exploration_stage
            if explore_pending is not _MISSING:
                row.explore_pending = None if explore_pending == CLEAR else explore_pending
            row.updated_at = utc_now()
            session.commit()
            session.refresh(row)
            return row

    def update_course(self, course_id: str, *, stage: str | None = None,
                      sort_order: int | None = None, description: str | None = None,
                      aliases: list[str] | None = None, track: str | None = None,
                      prerequisites: list[str] | None = None,
                      exploration_stage: str | None = None,
                      explore_pending: dict[str, Any] | None = _MISSING) -> QedCourse:
        """更新课程（name 不可变；exploration_stage/explore_pending 由探索流程管理）。"""
        with self._session_factory() as session:
            row = session.get(QedCourse, course_id)
            if row is None:
                raise KeyError(f"课程不存在：{course_id}")
            if stage is not None:
                row.stage = stage
            if sort_order is not None:
                row.sort_order = sort_order
            if description is not None:
                row.description = description
            if aliases is not None:
                row.aliases = aliases
            if track is not None:
                row.track = track
            if prerequisites is not None:
                row.prerequisites = prerequisites
            if exploration_stage is not None:
                row.exploration_stage = exploration_stage
            if explore_pending is not _MISSING:
                row.explore_pending = None if explore_pending == CLEAR else explore_pending
            row.updated_at = utc_now()
            session.commit()
            session.refresh(row)
            return row

    # --- REQ-067-B12: apply-results / re-explore ---

    @staticmethod
    def _delete_knowledge_rows(session: Session, rows: list[QtKnowledge]) -> None:
        """删除教程行并级联清理失去全部引用的书（书库化：refs 反查，qt_sources 手动级联）。

        书库化语义：QtBook 无 knowledge_id 列，待删书 = 被删教程 refs 引用、且不再被
        任何存留教程 refs 引用的行；从未被 refs 引用的独立候选书不受影响。被清理的
        已持有书仅删登记行，数据根内 PDF 不动（重导入按 sha256 复用）。
        """
        doomed: set[str] = set()
        for row in rows:
            doomed.update(_refs_book_ids(row.textbook_ref, row.exercise_ref, row.parallel_ref))
        if doomed:
            deleted_ids = {row.knowledge_id for row in rows}
            still_referenced: set[str] = set()
            for other in session.scalars(select(QtKnowledge)):
                if other.knowledge_id in deleted_ids:
                    continue
                still_referenced.update(
                    _refs_book_ids(other.textbook_ref, other.exercise_ref, other.parallel_ref)
                )
            orphaned = doomed - still_referenced
            if orphaned:
                session.execute(sa.delete(QtSource).where(QtSource.book_id.in_(orphaned)))
                session.execute(sa.delete(QtBook).where(QtBook.book_id.in_(orphaned)))
        for row in rows:
            session.delete(row)

    def apply_domain_results(self, domain_id: str, selected_courses: list[str]) -> int:
        """确认领域探索结果：exploration_stage -> 已完成，清空 explore_pending，删除未选课程。

        返回保留课程数。仅 当 exploration_stage == '待确认' 时可调用。
        """
        with self._session_factory() as session:
            domain = session.get(QedDomain, domain_id)
            if domain is None:
                raise KeyError(f"领域不存在：{domain_id}")
            if domain.exploration_stage != "待确认":
                raise InvalidExplorationTransition(
                    f"当前状态 {domain.exploration_stage}，需要 待确认"
                )
            domain.exploration_stage = "已完成"
            domain.explore_pending = None
            domain.updated_at = utc_now()
            # 删除未选课程及其教程行（书按 refs 反查级联，见 _delete_knowledge_rows）
            all_courses = list(session.scalars(
                select(QedCourse).where(QedCourse.domain_id == domain_id)
            ))
            kept = 0
            doomed_rows: list[QtKnowledge] = []
            for course in all_courses:
                if course.course_id in selected_courses:
                    kept += 1
                    continue
                doomed_rows.extend(session.scalars(
                    select(QtKnowledge).where(QtKnowledge.course_id == course.course_id)
                ))
                session.delete(course)
            self._delete_knowledge_rows(session, doomed_rows)
            session.commit()
            return kept

    def apply_course_results(self, course_id: str, selected_tutorials: list[str]) -> int:
        """确认课程探索结果：exploration_stage -> 已完成，清空 explore_pending，删除未选教程。

        返回保留教程数。仅 当 exploration_stage == '待确认' 时可调用。
        """
        with self._session_factory() as session:
            course = session.get(QedCourse, course_id)
            if course is None:
                raise KeyError(f"课程不存在：{course_id}")
            if course.exploration_stage != "待确认":
                raise InvalidExplorationTransition(
                    f"当前状态 {course.exploration_stage}，需要 待确认"
                )
            course.exploration_stage = "已完成"
            course.explore_pending = None
            course.updated_at = utc_now()
            # 删除未选教程（书按 refs 反查级联，见 _delete_knowledge_rows）
            all_kn = list(session.scalars(
                select(QtKnowledge).where(QtKnowledge.course_id == course_id)
            ))
            kept = len(all_kn)
            doomed_rows = [kn for kn in all_kn if kn.knowledge_id not in set(selected_tutorials)]
            kept -= len(doomed_rows)
            self._delete_knowledge_rows(session, doomed_rows)
            session.commit()
            return kept

    def delete_course(self, course_id: str) -> None:
        """删除课程：有教程 → CourseHasKnowledge。"""
        with self._session_factory() as session:
            row = session.get(QedCourse, course_id)
            if row is None:
                raise KeyError(f"课程不存在：{course_id}")
            kn_count = session.scalar(
                select(func.count()).select_from(QtKnowledge).where(QtKnowledge.course_id == course_id)
            )
            if kn_count:
                raise CourseHasKnowledge(f"课程 {course_id} 仍有 {kn_count} 条教程，禁止删除")
            session.delete(row)
            session.commit()

    def delete_domain(self, domain_id: str) -> None:
        """删除领域：有课程 → DomainNotEmpty。"""
        with self._session_factory() as session:
            row = session.get(QedDomain, domain_id)
            if row is None:
                raise KeyError(f"领域不存在：{domain_id}")
            course_count = session.scalar(
                select(func.count()).select_from(QedCourse).where(QedCourse.domain_id == domain_id)
            )
            if course_count:
                raise DomainNotEmpty(f"领域 {domain_id} 仍有 {course_count} 门课程，禁止删除")
            session.delete(row)
            session.commit()

    # ---------------- qt_knowledge ----------------

    def create_knowledge(
        self,
        *,
        course_id: str,
        set_no: str = "",
        name: str = "",
        kind: str = "tutorial",
        position: str = "",
        intro: str = "",
        knowledge_id: str = "",
    ) -> QtKnowledge:
        """幂等插入：knowledge_id = kt-{course_id 去下划线}-{set_no}（D4 裁决，服务端机械生成）。"""
        knowledge_id = knowledge_id or _tutorial_knowledge_id(course_id, set_no)
        with self._session_factory() as session:
            row = session.get(QtKnowledge, knowledge_id)
            if row is None:
                row = QtKnowledge(
                    knowledge_id=knowledge_id,
                    course_id=course_id,
                    kind=kind,
                    set_no=set_no,
                    name=name,
                    position=position,
                    intro=intro,
                )
                _touch(row, created=True)
                session.add(row)
            session.commit()
            return row

    @staticmethod
    def build_tutorial_row(
        *, course_id: str, set_no: str = "", name: str = "",
        position: str = "", intro: str = "", knowledge_id: str = "",
    ) -> QtKnowledge:
        """构造未落库的 draft 教程行：探索采纳单事务复用（id 规则与 create_knowledge 一致）。"""
        row = QtKnowledge(
            knowledge_id=knowledge_id or _tutorial_knowledge_id(course_id, set_no),
            course_id=course_id,
            kind="tutorial",
            set_no=set_no,
            name=name,
            position=position,
            intro=intro,
        )
        _touch(row, created=True)
        return row

    def adopt_tutorials(self, course_id: str, tutorials: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """A2 课程知识采纳：按新契约批量建 draft 教程 + 域级书库书行（书库化语义）。

        输入格式：tutorials 数组含 set_no/name/position/intro/textbook_ref[]/exercise_ref[]/
        parallel_ref[]；数据文件版可显式携带 knowledge_id（kt-{abbr}-{set_no}）与
        ref.book_id（{abbr}-b{NN}），服务端校验格式并做重复检测。

        幂等（2026-09-03 裁决）：教程 = (course_id, kind=tutorial, set_no) 命中复用；
        书 = (title, part, language, edition) 域内命中复用。同 set_no 被不同教程占用
        → AdoptionConflict（端点映射 409）；显式 id 格式错误 → ValueError（端点映射 422）。
        textbook_ref/exercise_ref → status=decided；parallel_ref → status=parallel；
        ref 可选 original_title 随建行回填。单事务批量提交，逐套返回
        {knowledge_id, set_no, name, status, existing, books_created}。
        """
        with self._session_factory() as session:
            course = session.get(QedCourse, course_id)
            if course is None:
                raise KeyError(f"课程不存在：{course_id}")
            domain_id = course.domain_id
            course_abbr = course_id.replace("_", "")

            existing_rows = list(session.scalars(
                select(QtKnowledge).where(
                    QtKnowledge.course_id == course_id, QtKnowledge.kind == "tutorial"
                )
            ))
            by_set = {r.set_no: r for r in existing_rows}
            by_kid = {r.knowledge_id: r for r in existing_rows}

            # 域级书库既有行索引：书幂等键 (title, part, language, edition) → 行；NN 取域内最大值
            book_index: dict[tuple[str, str, str, str], QtBook] = {}
            max_nn = 0
            for book in session.scalars(select(QtBook).where(QtBook.domain_id == domain_id)):
                book_index.setdefault(
                    (book.title, book.part, book.language or "", book.edition or ""), book
                )
                match = re.search(r"-b(\d+)$", book.book_id)
                if match:
                    max_nn = max(max_nn, int(match.group(1)))

            def _ensure_book(ref: dict[str, Any], *, roles: list[str], status: str) -> tuple[QtBook | None, bool]:
                """按书幂等键复用或新建书行；显式 book_id 优先按 id 幂等。返回 (书行, 是否新建)。"""
                nonlocal max_nn
                title = str(ref.get("title", "")).strip()
                if not title:
                    raise ValueError(f"ref 缺 title：{ref}")
                key = (title, str(ref.get("part", "")), str(ref.get("language", "")), str(ref.get("edition", "")))
                book: QtBook | None = book_index.get(key)
                if book is not None:
                    return book, False
                explicit_id = str(ref.get("book_id") or "").strip()
                if explicit_id:
                    if not _BOOK_ID_RE.match(explicit_id):
                        raise ValueError(f"book_id 格式错误（应为 {{abbr}}-b{{NN}}）：{explicit_id}")
                    book = session.get(QtBook, explicit_id)
                    if book is not None:
                        book_index.setdefault(key, book)
                        return book, False
                max_nn += 1
                book = QtBook(
                    book_id=explicit_id or f"{course_abbr}-b{max_nn:02d}",
                    title=title,
                    part=str(ref.get("part", "")),
                    original_title=str(ref.get("original_title", "") or "") or None,
                    authors=list(ref.get("authors") or []),
                    publisher=str(ref.get("publisher", "")),
                    edition=str(ref.get("edition", "")),
                    year=ref.get("year"),
                    language=str(ref.get("language", "")),
                    roles=list(roles),
                    status=status,
                    domain_id=domain_id,
                )
                _touch(book, created=True)
                session.add(book)
                book_index[key] = book
                return book, True

            pending: list[tuple[QtKnowledge, bool, int]] = []

            for item in tutorials:
                set_no = str(item.get("set_no", "")).strip()
                name = str(item.get("name", "")).strip()

                # 幂等：同 course_id+kind+set_no 且同名命中复用；
                # 同 set_no 被不同教程（不同 name）占用 → AdoptionConflict（API 409）
                hit = by_set.get(set_no)
                if hit is not None:
                    if name != hit.name:
                        raise AdoptionConflict(
                            f"set_no 已被其他教程占用：{set_no}（既有：{hit.name}）"
                        )
                    pending.append((hit, True, 0))
                    continue

                knowledge_id = str(item.get("knowledge_id") or "").strip()
                if knowledge_id:
                    if not _KNOWLEDGE_ID_RE.match(knowledge_id) or not knowledge_id.endswith(f"-{set_no}"):
                        raise ValueError(
                            f"knowledge_id 格式错误（应为 kt-{{abbr}}-{set_no}）：{knowledge_id}"
                        )
                    if knowledge_id in by_kid:
                        raise AdoptionConflict(f"knowledge_id 已被其他教程占用：{knowledge_id}")
                row = self.build_tutorial_row(
                    course_id=course_id, set_no=set_no, name=name,
                    position=str(item.get("position", "")),
                    intro=str(item.get("intro", "")),
                    knowledge_id=knowledge_id,
                )
                row.textbook_ref = list(item.get("textbook_ref") or [])
                row.exercise_ref = list(item.get("exercise_ref") or [])
                row.parallel_ref = list(item.get("parallel_ref") or [])

                # 先建书并回填 book_id，行再入 session：JSON 列原地变更不会被 UPDATE，
                # 必须保证首次 INSERT 即携带回填后的 refs。
                books_created = 0
                plan = (
                    [(ref, ["textbook"], BookStatus.DECIDED.value) for ref in row.textbook_ref]
                    + [(ref, ["exercises"], BookStatus.DECIDED.value) for ref in (row.exercise_ref or [])]
                    + [(ref, [], BookStatus.PARALLEL.value) for ref in (row.parallel_ref or [])]
                )
                for ref, roles, status in plan:
                    book, created = _ensure_book(ref, roles=roles, status=status)
                    ref["book_id"] = book.book_id  # type: ignore[union-attr]
                    if created:
                        books_created += 1
                row.textbook_ref = list(row.textbook_ref)
                row.exercise_ref = list(row.exercise_ref) if row.exercise_ref is not None else None
                row.parallel_ref = list(row.parallel_ref) if row.parallel_ref is not None else None

                session.add(row)
                by_set[set_no] = row
                by_kid[row.knowledge_id] = row

                pending.append((row, False, books_created))

            session.commit()
            results: list[dict[str, Any]] = []
            for row, existing, books_created in pending:
                session.refresh(row)
                results.append({
                    "knowledge_id": row.knowledge_id,
                    "set_no": row.set_no,
                    "name": row.name,
                    "status": row.status,
                    "existing": existing,
                    "books_created": books_created,
                })
            return results

    def list_knowledge(
        self,
        *,
        course_id: str | None = None,
        kind: str | None = None,
        status: str | None = None,
    ) -> list[QtKnowledge]:
        with self._session_factory() as session:
            statement = select(QtKnowledge).order_by(QtKnowledge.created_at)
            if course_id:
                statement = statement.where(QtKnowledge.course_id == course_id)
            if kind:
                statement = statement.where(QtKnowledge.kind == kind)
            if status:
                statement = statement.where(QtKnowledge.status == status)
            return list(session.scalars(statement))

    def get_knowledge(self, knowledge_id: str) -> QtKnowledge | None:
        with self._session_factory() as session:
            return session.get(QtKnowledge, knowledge_id)

    def _transition_knowledge(self, knowledge_id: str, target: KnowledgeStatus, **fields: Any) -> QtKnowledge:
        with self._session_factory() as session:
            row = session.get(QtKnowledge, knowledge_id)
            if row is None:
                raise KeyError(f"教程不存在：{knowledge_id}")
            current = KnowledgeStatus(row.status)
            if target not in _KNOWLEDGE_TRANSITIONS[current]:
                raise InvalidTransition(f"教程状态迁移非法：{current.value} → {target.value}")
            row.status = target.value
            for key, value in fields.items():
                setattr(row, key, value)
            row.updated_at = utc_now()
            session.commit()
            return row

    def confirm_knowledge(self, knowledge_id: str) -> QtKnowledge:
        """draft → confirmed（定稿：状态转换 + confirmed_at）。"""
        return self._transition_knowledge(
            knowledge_id,
            KnowledgeStatus.CONFIRMED,
            confirmed_at=utc_now(),
        )

    # ---------------- qt_books ----------------

    def create_book(
        self,
        book_id: str,
        *,
        title: str,
        part: str = "",
        original_title: str | None = None,
        authors: list[dict[str, Any]] | None = None,
        publisher: str = "",
        edition: str = "",
        year: int | None = None,
        language: str = "",
        roles: list[str] | None = None,
        status: str = BookStatus.CANDIDATE.value,
        domain_id: str = "",
        notes: str | None = None,
    ) -> QtBook:
        """幂等插入：book_id 由调用者传入（服务端生成 {abbr}-b{NN}，域内递增）。"""
        with self._session_factory() as session:
            row = session.get(QtBook, book_id)
            if row is None:
                row = QtBook(
                    book_id=book_id,
                    title=title,
                    part=part,
                    original_title=original_title or None,
                    authors=authors or [],
                    publisher=publisher,
                    edition=edition,
                    year=year,
                    language=language,
                    roles=roles or [],
                    status=status,
                    domain_id=domain_id,
                )
                if notes:
                    row.notes = notes
                _touch(row, created=True)
                session.add(row)
            session.commit()
            return row

    def list_books(self, knowledge_id: str | None = None) -> list[QtBook]:
        """列书库行：无 knowledge_id → 域级书库全量；给定 → 该教程 refs 聚合的书
        （textbook_ref/exercise_ref/parallel_ref 的 book_id 去重；书库化多对多，
        归属由 refs 承载，QtBook 无 knowledge_id 列）。"""
        with self._session_factory() as session:
            statement = select(QtBook).order_by(QtBook.created_at)
            if knowledge_id:
                row = session.get(QtKnowledge, knowledge_id)
                if row is None:
                    return []
                book_ids = _refs_book_ids(row.textbook_ref, row.exercise_ref, row.parallel_ref)
                if not book_ids:
                    return []
                statement = statement.where(QtBook.book_id.in_(book_ids))
            return list(session.scalars(statement))

    def get_book(self, book_id: str) -> QtBook | None:
        with self._session_factory() as session:
            return session.get(QtBook, book_id)

    def _transition_book(self, book_id: str, target: BookStatus, **fields: Any) -> QtBook:
        with self._session_factory() as session:
            row = session.get(QtBook, book_id)
            if row is None:
                raise KeyError(f"书籍不存在：{book_id}")
            current = BookStatus(row.status)
            if target not in _BOOK_TRANSITIONS[current]:
                raise InvalidTransition(f"书籍状态迁移非法：{current.value} → {target.value}")
            row.status = target.value
            for key, value in fields.items():
                setattr(row, key, value)
            row.updated_at = utc_now()
            session.commit()
            return row

    def decide_book(self, book_id: str) -> QtBook:
        """candidate → decided（人工决定选用）。"""
        return self._transition_book(book_id, BookStatus.DECIDED)

    def retire_book(self, book_id: str, *, reason: str = "") -> QtBook:
        """decided/parallel → retired（退役：版本换代或不再选用）。"""
        return self._transition_book(book_id, BookStatus.RETIRED, retire_reason=reason.strip())

    # ---------------- 登记服务（QED-050 阶段5：唯一写 holding/file_path 入口） ----------------

    def mark_owned(self, book_id: str, *, file_path: str) -> QtBook:
        """登记持有：holding=owned + file_path 回填（数据根相对路径）。

        下载成功（机器验收通过落盘）与人工导入共用此唯一写入口；LLM 判断不参与任何
        字段取值（download-pipeline.md 事实落点表）。幂等：同路径重复登记
        直接返回；已 owned 换路径按重新登记处理（人工替换文件）。
        """
        file_path = file_path.strip()
        if not file_path:
            raise ValueError("file_path 必填（数据根相对路径）")
        with self._session_factory() as session:
            row = session.get(QtBook, book_id)
            if row is None:
                raise KeyError(f"书籍不存在：{book_id}")
            if row.holding == "owned" and row.file_path == file_path:
                return row
            row.holding = "owned"
            row.file_path = file_path
            row.updated_at = utc_now()
            session.commit()
            return row

    def first_course_for_book(self, book_id: str) -> str:
        """refs 反查归属课程（书库化 QtBook 无 course_id 列）：引用该书的教程的课程。

        多教程引用取 course_id 最小者（确定性）；独立登记书返回空串。
        """
        with self._session_factory() as session:
            rows = session.scalars(
                select(QtKnowledge).order_by(QtKnowledge.course_id, QtKnowledge.set_no)
            )
            for row in rows:
                if book_id in _refs_book_ids(row.textbook_ref, row.exercise_ref, row.parallel_ref):
                    return row.course_id
        return ""

    def course_closure(self, course_id: str) -> dict[str, Any]:
        """课程闭环派生查询（只读，不写任何表）：该课程 refs 聚合书集中 decided 全 owned。

        parallel/candidate/retired 书不参与判定（download-pipeline.md 阶段5）；
        exploration_stage 不动。
        """
        with self._session_factory() as session:
            rows = list(session.scalars(
                select(QtKnowledge).where(QtKnowledge.course_id == course_id)
            ))
            book_ids: list[str] = []
            for row in rows:
                for book_id in _refs_book_ids(row.textbook_ref, row.exercise_ref, row.parallel_ref):
                    if book_id not in book_ids:
                        book_ids.append(book_id)
            books = [session.get(QtBook, book_id) for book_id in book_ids]
            books = [book for book in books if book is not None]
        decided = [book for book in books if book.status == BookStatus.DECIDED.value]
        missing = [book.book_id for book in decided if book.holding != "owned"]
        return {
            "course_id": course_id,
            "total_books": len(book_ids),
            "decided_count": len(decided),
            "owned_count": len(decided) - len(missing),
            "missing_book_ids": missing,
            "closed": not missing,
        }

    # ---------------- qt_sources ----------------

    def add_source(
        self,
        book_id: str,
        *,
        channel: str,
        provider_id: str = "",
        page_url: str = "",
        download_url: str = "",
        file_keywords: str = "",
        ok: bool = False,
        note: str = "",
        attempted_at=None,
    ) -> QtSource:
        attempted_at = attempted_at or utc_now()
        source_id = _id("src", book_id, channel, provider_id, str(attempted_at))
        with self._session_factory() as session:
            row = session.get(QtSource, source_id)
            if row is None:
                row = QtSource(source_id=source_id, book_id=book_id, channel=channel, attempted_at=attempted_at)
                session.add(row)
            row.provider_id = provider_id
            row.page_url = page_url
            row.download_url = download_url
            row.file_keywords = file_keywords
            row.ok = ok
            row.note = note
            session.commit()
            return row

    def list_sources(self, book_id: str, *, ok_only: bool = False) -> list[QtSource]:
        with self._session_factory() as session:
            statement = select(QtSource).where(QtSource.book_id == book_id).order_by(QtSource.attempted_at)
            if ok_only:
                from sqlalchemy import true

                statement = statement.where(QtSource.ok == true())
            return list(session.scalars(statement))
