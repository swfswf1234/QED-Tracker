"""知识/书库/渠道（qt_knowledge / qt_books / qt_sources）数据访问与状态机。

结构（docs/design/database-schema.md）：
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
from collections.abc import Callable, Iterable
from typing import Any

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from qed_tracker.database import utc_now
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
            # 删除未选课程（QtKnowledge/QtBook/QtSource 由数据库 ON DELETE CASCADE 或手动清理）
            all_courses = list(session.scalars(
                select(QedCourse).where(QedCourse.domain_id == domain_id)
            ))
            kept = 0
            for course in all_courses:
                if course.course_id in selected_courses:
                    kept += 1
                else:
                    # 手动级联删除子表
                    kn_ids = [
                        kn.knowledge_id for kn in session.scalars(
                            select(QtKnowledge).where(QtKnowledge.course_id == course.course_id)
                        )
                    ]
                    for kid in kn_ids:
                        session.execute(
                            sa.delete(QtSource).where(QtSource.book_id.in_(
                                sa.select(QtBook.book_id).where(QtBook.knowledge_id == kid)
                            ))
                        )
                        session.execute(sa.delete(QtBook).where(QtBook.knowledge_id == kid))
                    session.execute(sa.delete(QtKnowledge).where(QtKnowledge.course_id == course.course_id))
                    session.delete(course)
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
            # 删除未选教程
            all_kn = list(session.scalars(
                select(QtKnowledge).where(QtKnowledge.course_id == course_id)
            ))
            kept = 0
            for kn in all_kn:
                if kn.knowledge_id in selected_tutorials:
                    kept += 1
                else:
                    # 手动级联删除子表
                    session.execute(
                        sa.delete(QtSource).where(QtSource.book_id.in_(
                            sa.select(QtBook.book_id).where(QtBook.knowledge_id == kn.knowledge_id)
                        ))
                    )
                    session.execute(sa.delete(QtBook).where(QtBook.knowledge_id == kn.knowledge_id))
                    session.delete(kn)
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
        course_abbr: str,
        set_no: str = "",
        name: str = "",
        kind: str = "tutorial",
        position: str = "",
        intro: str = "",
        knowledge_id: str = "",
    ) -> QtKnowledge:
        """幂等插入：knowledge_id = kt_{course_abbr}_{set_no}，调用者负责传入 course_abbr。"""
        knowledge_id = knowledge_id or _id("kt", course_abbr, set_no)
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
        *, course_id: str, course_abbr: str, set_no: str = "", name: str = "",
        position: str = "", intro: str = "",
    ) -> QtKnowledge:
        """构造未落库的 draft 教程行：探索采纳单事务复用（id 规则与 create_knowledge 一致）。"""
        row = QtKnowledge(
            knowledge_id=_id("kt", course_abbr, set_no),
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
        """A2 课程知识采纳：按新契约批量建 draft 教程 + 关联书行。

        输入格式：
            tutorials 数组含 set_no/name/position/intro/textbook_ref[]/exercise_ref[]/parallel_ref[]

        幂等：同 course_id+kind+set_no 命中 → 返回既有行（existing=True）；
        同 set_no 被不同教程占用 → AdoptionConflict（端点映射 409）。
        单事务批量提交，逐套返回 {knowledge_id, set_no, name, status, existing, books_created}。
        """
        with self._session_factory() as session:
            course = session.get(QedCourse, course_id)
            if course is None:
                raise KeyError(f"课程不存在：{course_id}")
            domain_id = course.domain_id

            existing_rows = list(session.scalars(
                select(QtKnowledge).where(
                    QtKnowledge.course_id == course_id, QtKnowledge.kind == "tutorial"
                )
            ))
            by_set = {r.set_no: r for r in existing_rows}
            by_kid = {r.knowledge_id: r for r in existing_rows}

            pending: list[tuple[QtKnowledge, bool, int]] = []

            for item in tutorials:
                set_no = str(item.get("set_no", "")).strip()
                name = str(item.get("name", "")).strip()

                # 幂等：同 course_id+kind+set_no 命中
                hit = by_set.get(set_no)
                if hit is not None:
                    pending.append((hit, True, 0))
                    continue

                # 构造 draft 教程行
                course_abbr = course_id.split("-")[-1] if "-" in course_id else course_id
                row = self.build_tutorial_row(
                    course_id=course_id, course_abbr=course_abbr,
                    set_no=set_no, name=name,
                    position=str(item.get("position", "")),
                    intro=str(item.get("intro", "")),
                )
                row.textbook_ref = list(item.get("textbook_ref") or [])
                row.exercise_ref = list(item.get("exercise_ref") or [])
                row.parallel_ref = list(item.get("parallel_ref") or [])
                session.add(row)
                by_set[set_no] = row
                by_kid[row.knowledge_id] = row
                session.flush()

                books_created = 0

                # textbook_ref → status=decided
                for ref in row.textbook_ref:
                    book_id = ref.get("book_id") or _id("bk", row.knowledge_id, ref.get("title", ""))
                    book = QtBook(
                        book_id=book_id,
                        title=ref.get("title", ""),
                        part=ref.get("part", ""),
                        authors=ref.get("authors", []),
                        publisher=ref.get("publisher", ""),
                        edition=ref.get("edition", ""),
                        year=ref.get("year"),
                        language=ref.get("language", ""),
                        roles=["textbook"],
                        status=BookStatus.DECIDED.value,
                        domain_id=domain_id,
                        file_path=ref.get("file_path"),
                    )
                    _touch(book, created=True)
                    session.add(book)
                    ref["book_id"] = book_id
                    books_created += 1

                # exercise_ref → status=decided
                for ref in (row.exercise_ref or []):
                    book_id = ref.get("book_id") or _id("bk", row.knowledge_id, ref.get("title", ""))
                    book = QtBook(
                        book_id=book_id,
                        title=ref.get("title", ""),
                        part=ref.get("part", ""),
                        authors=ref.get("authors", []),
                        publisher=ref.get("publisher", ""),
                        edition=ref.get("edition", ""),
                        year=ref.get("year"),
                        language=ref.get("language", ""),
                        roles=["exercises"],
                        status=BookStatus.DECIDED.value,
                        domain_id=domain_id,
                        file_path=ref.get("file_path"),
                    )
                    _touch(book, created=True)
                    session.add(book)
                    ref["book_id"] = book_id
                    books_created += 1

                # parallel_ref → status=parallel
                for ref in (row.parallel_ref or []):
                    book_id = ref.get("book_id") or _id("bk", row.knowledge_id, ref.get("title", ""))
                    book = QtBook(
                        book_id=book_id,
                        title=ref.get("title", ""),
                        part=ref.get("part", ""),
                        authors=ref.get("authors", []),
                        publisher=ref.get("publisher", ""),
                        edition=ref.get("edition", ""),
                        year=ref.get("year"),
                        language=ref.get("language", ""),
                        roles=[],
                        status=BookStatus.PARALLEL.value,
                        domain_id=domain_id,
                        file_path=ref.get("file_path"),
                    )
                    _touch(book, created=True)
                    session.add(book)
                    ref["book_id"] = book_id
                    books_created += 1

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
        authors: list[dict[str, Any]] | None = None,
        publisher: str = "",
        edition: str = "",
        year: int | None = None,
        language: str = "",
        roles: list[str] | None = None,
        status: str = BookStatus.CANDIDATE.value,
        domain_id: str = "",
        file_path: str | None = None,
        notes: str | None = None,
    ) -> QtBook:
        """幂等插入：book_id 由调用者传入（服务端生成 {abbr}-b{NN}）。"""
        with self._session_factory() as session:
            row = session.get(QtBook, book_id)
            if row is None:
                row = QtBook(
                    book_id=book_id,
                    title=title,
                    part=part,
                    authors=authors or [],
                    publisher=publisher,
                    edition=edition,
                    year=year,
                    language=language,
                    roles=roles or [],
                    status=status,
                    domain_id=domain_id,
                    file_path=file_path,
                )
                _touch(row, created=True)
                session.add(row)
            session.commit()
            return row

    def list_books(self, knowledge_id: str | None = None) -> list[QtBook]:
        with self._session_factory() as session:
            statement = select(QtBook).order_by(QtBook.created_at)
            if knowledge_id:
                statement = statement.where(QtBook.knowledge_id == knowledge_id)
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
