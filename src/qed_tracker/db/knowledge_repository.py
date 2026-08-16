"""五层模型（qt_knowledge / qt_books / qt_sources）数据访问与状态机（QED-031）。

结构（docs/design/database-schema.md）：
qed_domain → qed_course → qt_knowledge（一行=一套教程/一组延展资料归类）→ qt_books
（一行=一册/一卷/一个快照）→ qt_sources（渠道尝试）。

状态机：
- qt_knowledge：draft → confirmed → completed；draft/confirmed → rejected；
  confirmed/completed → superseded。rejected/superseded 为终态（彻底隐藏）。
- qt_books：candidate → decided → downloading → downloaded → verified；
  candidate/decided/downloaded → rejected；downloading → failed（→downloading 重试）；
  candidate → downloaded 仅人工 register 直转（需 sha256+path）；candidate/decided/downloaded → superseded。
  verified/rejected/superseded 为终态（彻底隐藏）。

彻底隐藏语义在数据层实现（列表/详情接口默认过滤），前端不依赖展示层过滤。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from qed_tracker.database import utc_now
from qed_tracker.db.models import BookStatus, KnowledgeStatus, QedCourse, QedDomain, QtBook, QtKnowledge, QtSource


class InvalidTransition(RuntimeError):
    """状态机迁移非法。"""


_HIDDEN_KNOWLEDGE_STATUSES = {KnowledgeStatus.REJECTED.value, KnowledgeStatus.SUPERSEDED.value}
_HIDDEN_BOOK_STATUSES = {BookStatus.REJECTED.value, BookStatus.SUPERSEDED.value, BookStatus.FAILED.value}

_KNOWLEDGE_TRANSITIONS: dict[KnowledgeStatus, set[KnowledgeStatus]] = {
    KnowledgeStatus.DRAFT: {KnowledgeStatus.CONFIRMED, KnowledgeStatus.REJECTED},
    KnowledgeStatus.CONFIRMED: {KnowledgeStatus.COMPLETED, KnowledgeStatus.REJECTED, KnowledgeStatus.SUPERSEDED},
    KnowledgeStatus.COMPLETED: {KnowledgeStatus.SUPERSEDED},
    KnowledgeStatus.REJECTED: set(),
    KnowledgeStatus.SUPERSEDED: set(),
}

_BOOK_TRANSITIONS: dict[BookStatus, set[BookStatus]] = {
    BookStatus.CANDIDATE: {
        BookStatus.DECIDED, BookStatus.DOWNLOADED, BookStatus.REJECTED, BookStatus.SUPERSEDED
    },
    BookStatus.DECIDED: {BookStatus.DOWNLOADING, BookStatus.REJECTED, BookStatus.SUPERSEDED},
    BookStatus.DOWNLOADING: {BookStatus.DOWNLOADED, BookStatus.FAILED, BookStatus.REJECTED},
    BookStatus.DOWNLOADED: {BookStatus.VERIFIED, BookStatus.REJECTED, BookStatus.SUPERSEDED},
    BookStatus.FAILED: {BookStatus.DOWNLOADING, BookStatus.REJECTED},
    BookStatus.VERIFIED: set(),
    BookStatus.REJECTED: set(),
    BookStatus.SUPERSEDED: set(),
}


def _id(prefix: str, *parts: Any) -> str:
    key = json.dumps(parts, ensure_ascii=False, sort_keys=True)
    return f"{prefix}_{hashlib.md5(key.encode('utf-8')).hexdigest()}"


def _touch(row, *, created: bool = False) -> None:
    now = utc_now()
    if created:
        row.created_at = now
    row.updated_at = now


class KnowledgeRepository:
    """五表数据访问；session_factory 注入以便单元测试用 SQLite mock。"""

    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

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

    # ---------------- qt_knowledge ----------------

    def create_knowledge(
        self,
        *,
        domain_id: str,
        course_id: str,
        kind: str = "tutorial",
        set_no: str = "",
        name: str = "",
        knowledge_id: str = "",
    ) -> QtKnowledge:
        """幂等插入：候选期 knowledge_id = kn_<md5(domain, course, kind, set_no, name)>，定稿后保持稳定。"""
        knowledge_id = knowledge_id or _id("kn", domain_id, course_id, kind, set_no, name)
        with self._session_factory() as session:
            row = session.get(QtKnowledge, knowledge_id)
            if row is None:
                row = QtKnowledge(
                    knowledge_id=knowledge_id,
                    domain_id=domain_id,
                    course_id=course_id,
                    kind=kind,
                    set_no=set_no,
                    name=name,
                    textbook_intro="",
                    exercise_intro="",
                    materials_intro="",
                )
                _touch(row, created=True)
                session.add(row)
            session.commit()
            return row

    def list_knowledge(
        self,
        *,
        course_id: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        include_hidden: bool = False,
    ) -> list[QtKnowledge]:
        with self._session_factory() as session:
            statement = select(QtKnowledge).order_by(QtKnowledge.created_at)
            if course_id:
                statement = statement.where(QtKnowledge.course_id == course_id)
            if kind:
                statement = statement.where(QtKnowledge.kind == kind)
            if status:
                statement = statement.where(QtKnowledge.status == status)
            if not include_hidden:
                statement = statement.where(QtKnowledge.status.not_in(_HIDDEN_KNOWLEDGE_STATUSES))
            return list(session.scalars(statement))

    def get_knowledge(self, knowledge_id: str, *, include_hidden: bool = False) -> QtKnowledge | None:
        with self._session_factory() as session:
            row = session.get(QtKnowledge, knowledge_id)
            if row is None:
                return None
            if not include_hidden and row.status in _HIDDEN_KNOWLEDGE_STATUSES:
                return None
            return row

    def _transition_knowledge(self, knowledge_id: str, target: KnowledgeStatus, **fields: Any) -> QtKnowledge:
        with self._session_factory() as session:
            row = session.get(QtKnowledge, knowledge_id)
            if row is None:
                raise KeyError(f"知识行不存在：{knowledge_id}")
            current = KnowledgeStatus(row.status)
            if target not in _KNOWLEDGE_TRANSITIONS[current]:
                raise InvalidTransition(f"知识行状态迁移非法：{current.value} → {target.value}")
            row.status = target.value
            for key, value in fields.items():
                setattr(row, key, value)
            row.updated_at = utc_now()
            session.commit()
            return row

    def confirm_knowledge(
        self,
        knowledge_id: str,
        *,
        textbook_ref: dict[str, Any] | None = None,
        exercise_ref: dict[str, Any] | None = None,
        textbook_intro: str = "",
        exercise_intro: str = "",
    ) -> QtKnowledge:
        """draft → confirmed（探索定稿：决定引用 + 简介，简介 LLM 预填后人工审）。"""
        return self._transition_knowledge(
            knowledge_id,
            KnowledgeStatus.CONFIRMED,
            confirmed_at=utc_now(),
            textbook_ref=textbook_ref or {},
            exercise_ref=exercise_ref or {},
            textbook_intro=textbook_intro.strip(),
            exercise_intro=exercise_intro.strip(),
        )

    def complete_knowledge(self, knowledge_id: str) -> QtKnowledge:
        """confirmed → completed（所辖非隐藏书行全部 verified 聚合触发；无书行或全隐藏则不允许）。"""
        with self._session_factory() as session:
            row = session.get(QtKnowledge, knowledge_id)
            if row is None:
                raise KeyError(f"知识行不存在：{knowledge_id}")
            if row.status != KnowledgeStatus.CONFIRMED.value:
                raise InvalidTransition(f"知识行状态迁移非法：{row.status} → completed")
            visible = session.scalar(
                select(func.count())
                .select_from(QtBook)
                .where(QtBook.knowledge_id == knowledge_id)
                .where(QtBook.status.not_in(_HIDDEN_BOOK_STATUSES))
            )
            if not visible:
                raise InvalidTransition("知识行没有非隐藏书行，不能完成")
            pending = session.scalar(
                select(func.count())
                .select_from(QtBook)
                .where(QtBook.knowledge_id == knowledge_id)
                .where(QtBook.status != BookStatus.VERIFIED.value)
                .where(QtBook.status.not_in(_HIDDEN_BOOK_STATUSES))
            )
            if pending:
                raise InvalidTransition("存在未验证（verified）的书行，不能完成知识行")
            row.status = KnowledgeStatus.COMPLETED.value
            row.completed_at = utc_now()
            row.updated_at = utc_now()
            session.commit()
            return row

    def reject_knowledge(self, knowledge_id: str, *, reason: str, by: str) -> QtKnowledge:
        if not reason.strip():
            raise ValueError("拒绝必须提供原因（reject_reason 必填）")
        return self._transition_knowledge(
            knowledge_id,
            KnowledgeStatus.REJECTED,
            rejected_at=utc_now(),
            reject_reason=reason.strip(),
            updated_by=by,
        )

    def supersede_knowledge(self, knowledge_id: str, *, reason: str, by: str) -> QtKnowledge:
        if not reason.strip():
            raise ValueError("过时必须提供原因（supersede_reason 必填）")
        return self._transition_knowledge(
            knowledge_id,
            KnowledgeStatus.SUPERSEDED,
            superseded_at=utc_now(),
            supersede_reason=reason.strip(),
            updated_by=by,
        )

    # ---------------- qt_books ----------------

    def create_book(
        self,
        knowledge_id: str,
        *,
        kind: str = "textbook",
        roles: Iterable[str] = (),
        title: str,
        part: str = "",
        display_title: str = "",
        authors: Iterable[str] = (),
        language: str = "",
        version: dict[str, Any] | None = None,
        source: dict[str, Any] | None = None,
        original_url: str = "",
        book_id: str = "",
    ) -> QtBook:
        """幂等插入：book_id = bk_<md5(knowledge_id, title, part)>；同套同书同卷不重复建行。"""
        display_title = display_title or f"{title} {part}".strip()
        book_id = book_id or _id("bk", knowledge_id, title, part)
        with self._session_factory() as session:
            row = session.get(QtBook, book_id)
            if row is None:
                row = QtBook(
                    book_id=book_id,
                    knowledge_id=knowledge_id,
                    kind=kind,
                    roles=list(roles),
                    title=title,
                    part=part,
                    display_title=display_title,
                    authors=list(authors),
                    language=language,
                    version=version or {},
                    source=source,
                    original_url=original_url,
                )
                _touch(row, created=True)
                session.add(row)
            session.commit()
            return row

    def list_books(self, knowledge_id: str | None = None, *, include_hidden: bool = False) -> list[QtBook]:
        with self._session_factory() as session:
            statement = select(QtBook).order_by(QtBook.created_at)
            if knowledge_id:
                statement = statement.where(QtBook.knowledge_id == knowledge_id)
            if not include_hidden:
                statement = statement.where(QtBook.status.not_in(_HIDDEN_BOOK_STATUSES))
            return list(session.scalars(statement))

    def get_book(self, book_id: str, *, include_hidden: bool = False) -> QtBook | None:
        with self._session_factory() as session:
            row = session.get(QtBook, book_id)
            if row is None:
                return None
            if not include_hidden and row.status in _HIDDEN_BOOK_STATUSES:
                return None
            return row

    def _transition_book(
        self, book_id: str, target: BookStatus, *, require_filed: bool = False, **fields: Any
    ) -> QtBook:
        with self._session_factory() as session:
            row = session.get(QtBook, book_id)
            if row is None:
                raise KeyError(f"书行不存在：{book_id}")
            current = BookStatus(row.status)
            if target not in _BOOK_TRANSITIONS[current]:
                raise InvalidTransition(f"书行状态迁移非法：{current.value} → {target.value}")
            if require_filed and not (row.sha256 and row.relative_path):
                raise InvalidTransition("进入 downloaded 前必须已登记 sha256 + relative_path")
            row.status = target.value
            for key, value in fields.items():
                setattr(row, key, value)
            row.updated_at = utc_now()
            session.commit()
            return row

    def decide_book(self, book_id: str) -> QtBook:
        """candidate → decided（人工决定下载，录 decided_at）。"""
        return self._transition_book(book_id, BookStatus.DECIDED, decided_at=utc_now())

    def start_download(self, book_id: str) -> QtBook:
        """decided → downloading（任务发起）；failed → downloading（重试）。"""
        return self._transition_book(book_id, BookStatus.DOWNLOADING)

    def fail_download(self, book_id: str) -> QtBook:
        """downloading → failed（仅下载中可失败；candidate→failed 不允许）。"""
        return self._transition_book(book_id, BookStatus.FAILED)

    def retry_download(self, book_id: str) -> QtBook:
        """failed → downloading（重试）。"""
        return self._transition_book(book_id, BookStatus.DOWNLOADING)

    def complete_download(
        self,
        book_id: str,
        *,
        sha256: str,
        relative_path: str,
        page_count: int | None = None,
        absolute_path: str = "",
        file_name: str = "",
    ) -> QtBook:
        """downloading → downloaded（自动任务）或 candidate → downloaded（人工 register 直转）。

        两者均要求已提供 sha256 + relative_path。同 sha256 幂等：已存在同 sha256 行则复用。
        """
        if not sha256 or not relative_path:
            raise InvalidTransition("进入 downloaded 前必须已登记 sha256 + relative_path")
        with self._session_factory() as session:
            existing = session.scalar(select(QtBook).where(QtBook.sha256 == sha256))
            if existing is not None and existing.book_id != book_id:
                row = session.get(QtBook, book_id)
                if row is not None:
                    session.delete(row)
                session.commit()
                return existing
            row = session.get(QtBook, book_id)
            if row is None:
                raise KeyError(f"书行不存在：{book_id}")
            current = BookStatus(row.status)
            if current not in (BookStatus.DOWNLOADING, BookStatus.CANDIDATE, BookStatus.DECIDED):
                raise InvalidTransition(f"书行状态迁移非法：{current.value} → downloaded")
            row.sha256 = sha256
            row.relative_path = relative_path
            row.absolute_path = absolute_path
            row.file_name = file_name
            if page_count is not None:
                row.page_count = page_count
            row.status = BookStatus.DOWNLOADED.value
            row.downloaded_at = utc_now()
            row.updated_at = utc_now()
            session.commit()
            return row

    def verify_book(self, book_id: str) -> QtBook:
        """downloaded → verified（人工验收确认正确）。"""
        return self._transition_book(book_id, BookStatus.VERIFIED, verified_at=utc_now())

    def reject_book(self, book_id: str, *, reason: str, by: str, note: str = "") -> QtBook:
        """candidate/decided/downloading/downloaded → rejected（必填原因；文件硬删由调用方执行）。"""
        if not reason.strip():
            raise ValueError("拒绝必须提供原因（reject_reason 必填）")
        return self._transition_book(
            book_id,
            BookStatus.REJECTED,
            rejected_at=utc_now(),
            reject_reason=reason.strip(),
            rejected_by=by,
            review_note=note.strip(),
        )

    def supersede_book(self, book_id: str, *, reason: str, by: str) -> QtBook:
        """candidate/decided/downloaded → superseded（版本换代留痕，原因必填）。"""
        if not reason.strip():
            raise ValueError("过时必须提供原因（supersede_reason 必填）")
        return self._transition_book(
            book_id,
            BookStatus.SUPERSEDED,
            superseded_at=utc_now(),
            supersede_reason=reason.strip(),
            updated_by=by,
        )

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