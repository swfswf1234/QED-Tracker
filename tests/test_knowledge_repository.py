"""五层模型（qt_knowledge/qt_books/qt_sources）状态机与隐藏过滤定向测试（SQLite 内存）。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.database import utc_now
from qed_tracker.db.knowledge_repository import InvalidTransition, KnowledgeRepository
from qed_tracker.db.models import Base, BookStatus, KnowledgeStatus, QedCourse, QedDomain


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    now = utc_now()
    session.add(QedDomain(domain_id="math", name="数学", description="d", stages=["本科基础"],
                          created_at=now, updated_at=now))
    session.add(QedCourse(course_id="01_math_analysis", domain_id="math", sort_order=1, name="数学分析",
                          aliases=[], stage="本科基础", prerequisites=[], related_targets=[],
                          created_at=now, updated_at=now))
    session.commit()
    yield KnowledgeRepository(factory)
    engine.dispose()


def _knowledge(repo: KnowledgeRepository, *, name: str = "数学分析 套一", set_no: str = "1"):
    return repo.create_knowledge(
        domain_id="math", course_id="01_math_analysis", kind="tutorial",
        set_no=set_no, name=name,
    )


def _book(repo: KnowledgeRepository, knowledge_id: str, *, title: str = "微积分学教程",
          part: str = "", kind: str = "textbook", roles: list[str] | None = None):
    return repo.create_book(
        knowledge_id=knowledge_id, kind=kind, title=title, part=part,
        roles=roles or ["textbook"], authors=["菲赫金哥尔茨"],
        version={"edition": "第8版", "language": "zh"},
    )


# --- 知识行状态机 ---


def test_knowledge_default_status_draft(repo):
    row = _knowledge(repo)
    assert row.status == KnowledgeStatus.DRAFT.value
    assert row.set_no == "1"
    assert row.knowledge_id.startswith("kn_")


def test_knowledge_idempotent_create(repo):
    first = _knowledge(repo)
    second = _knowledge(repo)
    assert first.knowledge_id == second.knowledge_id


def test_knowledge_confirm_sets_refs(repo):
    row = _knowledge(repo)
    confirmed = repo.confirm_knowledge(
        row.knowledge_id,
        textbook_ref={"title": "微积分学教程", "version": "第8版"},
        exercise_ref={"title": "数学分析习题集", "version": "第3版"},
        textbook_intro="菲赫金哥尔茨三卷本，经典教材。",
        exercise_intro="配套习题集。",
    )
    assert confirmed.status == KnowledgeStatus.CONFIRMED.value
    assert confirmed.confirmed_at is not None
    assert confirmed.textbook_ref["title"] == "微积分学教程"


def test_knowledge_reject_requires_reason(repo):
    row = _knowledge(repo)
    with pytest.raises(ValueError):
        repo.reject_knowledge(row.knowledge_id, reason=" ", by="cli")


def test_knowledge_hidden_after_reject(repo):
    row = _knowledge(repo)
    repo.reject_knowledge(row.knowledge_id, reason="版本旧", by="cli")
    assert repo.get_knowledge(row.knowledge_id) is None
    assert repo.get_knowledge(row.knowledge_id, include_hidden=True) is not None
    assert repo.list_knowledge(course_id="01_math_analysis") == []


def test_knowledge_invalid_transition(repo):
    row = _knowledge(repo)
    repo.confirm_knowledge(row.knowledge_id, textbook_ref={}, exercise_ref={})
    with pytest.raises(InvalidTransition):
        repo.complete_knowledge(row.knowledge_id)  # completed 需所辖书行全 verified，此处无书行


def test_knowledge_supersede_from_confirmed(repo):
    row = _knowledge(repo)
    repo.confirm_knowledge(row.knowledge_id, textbook_ref={}, exercise_ref={})
    updated = repo.supersede_knowledge(row.knowledge_id, reason="新版换代", by="cli")
    assert updated.status == KnowledgeStatus.SUPERSEDED.value
    assert updated.superseded_at is not None


# --- 书行状态机 ---


def test_book_default_status_candidate(repo):
    knowledge = _knowledge(repo)
    book = _book(repo, knowledge.knowledge_id)
    assert book.status == BookStatus.CANDIDATE.value
    assert book.book_id.startswith("bk_")


def test_book_decide_then_download_verify(repo):
    knowledge = _knowledge(repo)
    book = _book(repo, knowledge.knowledge_id)
    repo.decide_book(book.book_id)
    repo.start_download(book.book_id)
    repo.complete_download(book.book_id, sha256="a" * 64, relative_path="raw/books/x.pdf", page_count=100)
    verified = repo.verify_book(book.book_id)
    assert verified.status == BookStatus.VERIFIED.value
    assert verified.verified_at is not None


def test_book_complete_requires_sha256(repo):
    knowledge = _knowledge(repo)
    book = _book(repo, knowledge.knowledge_id)
    with pytest.raises(InvalidTransition):
        repo.complete_download(book.book_id, sha256="", relative_path="")


def test_book_fail_and_retry(repo):
    knowledge = _knowledge(repo)
    book = _book(repo, knowledge.knowledge_id)
    repo.decide_book(book.book_id)
    repo.start_download(book.book_id)
    failed = repo.fail_download(book.book_id)
    assert failed.status == BookStatus.FAILED.value
    retried = repo.retry_download(book.book_id)
    assert retried.status == BookStatus.DOWNLOADING.value


def test_book_candidate_to_failed_forbidden(repo):
    knowledge = _knowledge(repo)
    book = _book(repo, knowledge.knowledge_id)
    with pytest.raises(InvalidTransition):
        repo.fail_download(book.book_id)


def test_book_reject_and_supersede_terminal(repo):
    knowledge = _knowledge(repo)
    book = _book(repo, knowledge.knowledge_id)
    rejected = repo.reject_book(book.book_id, reason="版本旧", by="cli")
    assert rejected.status == BookStatus.REJECTED.value
    with pytest.raises(InvalidTransition):
        repo.decide_book(book.book_id)
    other = _book(repo, knowledge.knowledge_id, title="另一本书")
    repo.decide_book(other.book_id)
    superseded = repo.supersede_book(other.book_id, reason="换代", by="cli")
    assert superseded.status == BookStatus.SUPERSEDED.value


def test_book_hidden_default(repo):
    knowledge = _knowledge(repo)
    book = _book(repo, knowledge.knowledge_id)
    repo.reject_book(book.book_id, reason="不适用", by="cli")
    assert repo.list_books(knowledge.knowledge_id) == []
    assert len(repo.list_books(knowledge.knowledge_id, include_hidden=True)) == 1


# --- 知识行 completed 聚合 ---


def test_knowledge_completed_when_all_books_verified(repo):
    knowledge = _knowledge(repo)
    repo.confirm_knowledge(
        knowledge.knowledge_id,
        textbook_ref={"title": "微积分学教程", "version": "第8版"},
        exercise_ref={"title": "数学分析习题集", "version": "第3版"},
        textbook_intro="教材简介。",
        exercise_intro="习题集简介。",
    )
    book = _book(repo, knowledge.knowledge_id)
    repo.decide_book(book.book_id)
    repo.start_download(book.book_id)
    repo.complete_download(book.book_id, sha256="b" * 64, relative_path="raw/books/y.pdf")
    repo.verify_book(book.book_id)
    completed = repo.complete_knowledge(knowledge.knowledge_id)
    assert completed.status == KnowledgeStatus.COMPLETED.value
    assert completed.completed_at is not None


def test_complete_knowledge_requires_all_verified(repo):
    knowledge = _knowledge(repo)
    book = _book(repo, knowledge.knowledge_id)
    repo.decide_book(book.book_id)
    with pytest.raises(InvalidTransition):
        repo.complete_knowledge(knowledge.knowledge_id)


def test_book_idempotent_create_same_title_part(repo):
    knowledge = _knowledge(repo)
    first = _book(repo, knowledge.knowledge_id)
    second = _book(repo, knowledge.knowledge_id)
    assert first.book_id == second.book_id
    different = _book(repo, knowledge.knowledge_id, title="微积分学教程", part="第一册")
    assert different.book_id != first.book_id


# --- 渠道 ---


def test_add_and_list_sources(repo):
    knowledge = _knowledge(repo)
    book = _book(repo, knowledge.knowledge_id)
    repo.add_source(book.book_id, channel="manual", ok=True, download_url="http://x")
    rows = repo.list_sources(book.book_id)
    assert len(rows) == 1
    assert rows[0].channel == "manual"


def test_book_same_sha256_reuses_existing(repo):
    """同 sha256 幂等：新行登记同 sha256 时复用既有行并删除新行。"""
    knowledge = _knowledge(repo)
    first = _book(repo, knowledge.knowledge_id)
    repo.decide_book(first.book_id)
    repo.start_download(first.book_id)
    repo.complete_download(first.book_id, sha256="d" * 64, relative_path="raw/books/a.pdf")
    second = _book(repo, knowledge.knowledge_id, title="另一本同名书")
    repo.decide_book(second.book_id)
    repo.start_download(second.book_id)
    reused = repo.complete_download(second.book_id, sha256="d" * 64, relative_path="raw/books/b.pdf")
    assert reused.book_id == first.book_id
    assert repo.get_book(second.book_id, include_hidden=True) is None


def test_book_failed_visible_and_blocks_completion(repo):
    knowledge = _knowledge(repo)
    repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref={}, exercise_ref={})
    book = _book(repo, knowledge.knowledge_id)
    repo.decide_book(book.book_id)
    repo.start_download(book.book_id)
    repo.fail_download(book.book_id)
    assert len(repo.list_books(knowledge.knowledge_id)) == 1  # failed 可见
    with pytest.raises(InvalidTransition):
        repo.complete_knowledge(knowledge.knowledge_id)  # failed 阻塞 completed


def test_create_book_unknown_knowledge_raises(repo):
    with pytest.raises(KeyError):
        repo.create_book("kn_nonexistent", kind="textbook", title="书")


def test_list_sources_ok_only(repo):
    knowledge = _knowledge(repo)
    book = _book(repo, knowledge.knowledge_id)
    repo.add_source(book.book_id, channel="manual", ok=True, download_url="http://a")
    repo.add_source(book.book_id, channel="internet_archive", ok=False, download_url="http://b")
    assert len(repo.list_sources(book.book_id)) == 2
    assert len(repo.list_sources(book.book_id, ok_only=True)) == 1


# --- 领域探索状态（REQ-067 B8，2026-08-30） ---


def test_update_domain_supports_name(repo):
    """name 仅探索名确认路径可写：update_domain(name=...) 生效。"""
    row = repo.update_domain("math", name="数学（高等数学）")
    assert row.name == "数学（高等数学）"
    assert repo.get_domain("math").name == "数学（高等数学）"


def test_update_domain_supports_explore_pending(repo):
    """explore_pending 写入/清空（None=无挂起）。"""
    row = repo.update_domain("math", exploration_stage="已生成",
                             explore_pending={"kind": "name_confirm",
                                              "name_check": {"suggested_name": "高等数学"}})
    assert row.explore_pending["kind"] == "name_confirm"
    row = repo.update_domain("math", exploration_stage="已完成", explore_pending=None)
    assert row.explore_pending is None


def test_update_domain_unknown_raises(repo):
    with pytest.raises(KeyError):
        repo.update_domain("nope", name="x")