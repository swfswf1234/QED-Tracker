"""五层模型（qt_knowledge/qt_books/qt_sources）状态机与渠道定向测试（SQLite 内存）。

覆盖当前契约（QED-050-D 书库化 + QED-060 下载生命周期）：
- qt_knowledge 两态 draft→confirmed；
- qt_books 选用四态 + 下载生命周期八态 + holding；
- mark_owned 唯一登记入口；course_closure 派生闭环；
- QED-062 course_abbr（全名 + 超长缩略）。
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.db.engine import utc_now
from qed_tracker.db.knowledge_repository import (
    InvalidTransition,
    KnowledgeRepository,
    _tutorial_knowledge_id,
)
from qed_tracker.db.models import Base, BookStatus, KnowledgeStatus, QedCourse, QedDomain


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    now = utc_now()
    session.add(QedDomain(domain_id="math", name="数学", description="d",
                          stages=["基础", "主干", "分支", "前沿"],
                          created_at=now, updated_at=now))
    session.add(QedCourse(course_id="math_analysis", domain_id="math", sort_order=1, name="数学分析",
                          aliases=[], stage="基础", prerequisites=[], related_targets=[],
                          created_at=now, updated_at=now))
    session.commit()
    yield KnowledgeRepository(factory)
    engine.dispose()


def _knowledge(repo: KnowledgeRepository, *, set_no: str = "1", name: str = "数学分析 套一",
               course_id: str = "math_analysis"):
    return repo.create_knowledge(course_id=course_id, set_no=set_no, name=name)


def _book(repo: KnowledgeRepository, *, book_id: str = "mathanalysis-b01", title: str = "微积分学教程",
          part: str = "", roles: list[str] | None = None, domain_id: str = "math"):
    return repo.create_book(
        book_id, title=title, part=part, roles=roles or ["textbook"],
        authors=[{"name": "菲赫金哥尔茨", "role": "author"}], language="zh", domain_id=domain_id,
    )


# --- 教程状态机（两态） ---


def test_knowledge_default_status_draft(repo):
    row = _knowledge(repo)
    assert row.status == KnowledgeStatus.DRAFT.value
    assert row.set_no == "1"
    assert row.knowledge_id == "kt-mathanalysis-1"


def test_knowledge_idempotent_create(repo):
    first = _knowledge(repo)
    second = _knowledge(repo)
    assert first.knowledge_id == second.knowledge_id


def test_knowledge_confirm_sets_confirmed_at(repo):
    row = _knowledge(repo)
    confirmed = repo.confirm_knowledge(row.knowledge_id)
    assert confirmed.status == KnowledgeStatus.CONFIRMED.value
    assert confirmed.confirmed_at is not None


def test_knowledge_confirm_twice_invalid(repo):
    row = _knowledge(repo)
    repo.confirm_knowledge(row.knowledge_id)
    with pytest.raises(InvalidTransition):
        repo.confirm_knowledge(row.knowledge_id)


# --- 教程 update / delete（L-15/L-16） ---


def test_knowledge_update_fields():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    repo = KnowledgeRepository(factory)
    kn = repo.create_knowledge(course_id="c_test", set_no="1", name="原始名称", position="beginner")
    updated = repo.update_knowledge(kn.knowledge_id, name="新名称", position="intermediate")
    assert updated.name == "新名称"
    assert updated.position == "intermediate"
    assert updated.knowledge_id == kn.knowledge_id
    engine.dispose()


def test_knowledge_update_nonexistent_raises():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    repo = KnowledgeRepository(factory)
    with pytest.raises(KeyError, match="教程不存在"):
        repo.update_knowledge("nonexistent-id", name="新名称")
    engine.dispose()


def test_knowledge_update_preserves_other_fields():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    repo = KnowledgeRepository(factory)
    kn = repo.create_knowledge(course_id="c_test", set_no="1", name="原始名称", position="beginner", intro="简介")
    updated = repo.update_knowledge(kn.knowledge_id, name="新名称")
    assert updated.name == "新名称"
    assert updated.position == "beginner"
    assert updated.intro == "简介"
    engine.dispose()


def test_knowledge_delete():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    repo = KnowledgeRepository(factory)
    kn = repo.create_knowledge(course_id="c_test", set_no="1", name="待删除")
    repo.delete_knowledge(kn.knowledge_id)
    assert repo.get_knowledge(kn.knowledge_id) is None
    engine.dispose()


def test_knowledge_delete_nonexistent_raises():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    repo = KnowledgeRepository(factory)
    with pytest.raises(KeyError, match="教程不存在"):
        repo.delete_knowledge("nonexistent-id")
    engine.dispose()


def test_knowledge_delete_cascades_orphaned_books():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    repo = KnowledgeRepository(factory)
    kn = repo.create_knowledge(course_id="c_test", set_no="1", name="带书教程")
    repo.create_book("test-b01", title="测试书", domain_id="d_test")
    kn.textbook_ref = [{"book_id": "test-b01", "title": "测试书"}]
    session = factory()
    session.merge(kn)
    session.commit()
    session.close()
    repo.delete_knowledge(kn.knowledge_id)
    assert repo.get_book("test-b01") is None
    engine.dispose()


def test_knowledge_delete_preserves_referenced_books():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    repo = KnowledgeRepository(factory)
    kn1 = repo.create_knowledge(course_id="c_test", set_no="1", name="教程1")
    kn2 = repo.create_knowledge(course_id="c_test", set_no="2", name="教程2")
    repo.create_book("test-b01", title="测试书", domain_id="d_test")
    kn1.textbook_ref = [{"book_id": "test-b01", "title": "测试书"}]
    kn2.textbook_ref = [{"book_id": "test-b01", "title": "测试书"}]
    session = factory()
    session.merge(kn1)
    session.merge(kn2)
    session.commit()
    session.close()
    repo.delete_knowledge(kn1.knowledge_id)
    assert repo.get_book("test-b01") is not None
    repo.delete_knowledge(kn2.knowledge_id)
    assert repo.get_book("test-b01") is None
    engine.dispose()


# --- 书籍状态机（选用四态 + 下载生命周期） ---


def test_book_default_status_candidate(repo):
    book = _book(repo)
    assert book.status == BookStatus.CANDIDATE.value
    assert book.holding == "missing"
    assert book.book_id == "mathanalysis-b01"


def test_book_decide_then_download_verify(repo):
    book = _book(repo)
    repo.decide_book(book.book_id)
    repo.start_download(book.book_id)
    repo.mark_owned(book.book_id, file_path="raw/math/math_analysis/x.pdf", status="downloaded")
    owned = repo.get_book(book.book_id)
    assert owned.status == BookStatus.DOWNLOADED.value
    assert owned.holding == "owned"
    verified = repo.verify_book(book.book_id)
    assert verified.status == BookStatus.VERIFIED.value


def test_book_fail_and_retry(repo):
    book = _book(repo)
    repo.decide_book(book.book_id)
    repo.start_download(book.book_id)
    failed = repo.fail_download(book.book_id)
    assert failed.status == BookStatus.FAILED.value
    retried = repo.start_download(book.book_id)
    assert retried.status == BookStatus.DOWNLOADING.value


def test_book_candidate_to_failed_forbidden(repo):
    book = _book(repo)
    with pytest.raises(InvalidTransition):
        repo.fail_download(book.book_id)


def test_book_cancel_resets_to_decided(repo):
    book = _book(repo)
    repo.decide_book(book.book_id)
    repo.start_download(book.book_id)
    cancelled = repo.cancel_download(book.book_id)
    assert cancelled.status == BookStatus.DECIDED.value


def test_book_retire_terminal(repo):
    book = _book(repo)
    repo.decide_book(book.book_id)
    retired = repo.retire_book(book.book_id, reason="版本旧")
    assert retired.status == BookStatus.RETIRED.value
    with pytest.raises(InvalidTransition):
        repo.decide_book(book.book_id)


def test_mark_owned_idempotent(repo):
    book = _book(repo)
    repo.decide_book(book.book_id)
    repo.start_download(book.book_id)
    first = repo.mark_owned(book.book_id, file_path="raw/math/math_analysis/x.pdf", status="downloaded")
    second = repo.mark_owned(book.book_id, file_path="raw/math/math_analysis/x.pdf", status="downloaded")
    assert first.file_path == second.file_path
    assert second.holding == "owned"


# --- 渠道 ---


def test_add_and_list_sources(repo):
    book = _book(repo)
    repo.add_source(book.book_id, channel="manual", ok=True, download_url="http://x")
    rows = repo.list_sources(book.book_id)
    assert len(rows) == 1
    assert rows[0].channel == "manual"


def test_list_sources_ok_only(repo):
    book = _book(repo)
    repo.add_source(book.book_id, channel="manual", ok=True, download_url="http://a")
    repo.add_source(book.book_id, channel="internet_archive", ok=False, download_url="http://b")
    assert len(repo.list_sources(book.book_id)) == 2
    assert len(repo.list_sources(book.book_id, ok_only=True)) == 1


def test_add_source_appends_even_with_same_timestamp(repo):
    """渠道留痕按尝试追加：同一时间戳的两次尝试不得互相覆盖（Windows 时钟精度回归）。"""
    from qed_tracker.db.engine import utc_now

    book = _book(repo)
    same = utc_now()
    repo.add_source(book.book_id, channel="internet_archive", ok=True, attempted_at=same)
    repo.add_source(book.book_id, channel="internet_archive", ok=False, attempted_at=same)
    rows = repo.list_sources(book.book_id)
    assert len(rows) == 2
    assert {row.ok for row in rows} == {True, False}


# --- 课程闭环（派生只读） ---


def test_course_closure_not_closed_until_decided_owned(repo):
    kn = repo.create_knowledge(course_id="math_analysis", set_no="1", name="教程1")
    book = _book(repo)
    kn.textbook_ref = [{"book_id": book.book_id, "title": book.title}]
    session = repo.session_factory()
    session.merge(kn)
    session.commit()
    session.close()
    repo.decide_book(book.book_id)
    closure = repo.course_closure("math_analysis")
    assert closure["closed"] is False
    assert book.book_id in closure["missing_book_ids"]

    repo.mark_owned(book.book_id, file_path="raw/math/math_analysis/x.pdf", status="downloaded")
    closure = repo.course_closure("math_analysis")
    assert closure["closed"] is True


# --- QED-062：course_abbr（全名 + 超长缩略） ---


def test_tutorial_knowledge_id_full_name_abbr():
    assert _tutorial_knowledge_id("math_analysis", "1") == "kt-mathanalysis-1"
    assert _tutorial_knowledge_id("linear_algebra", "2") == "kt-linearalgebra-2"
    assert _tutorial_knowledge_id("probability", "en") == "kt-probability-en"


def test_tutorial_knowledge_id_long_name_acronym():
    assert _tutorial_knowledge_id("ordinary_differential_equations", "1") == "kt-ode-1"
    assert _tutorial_knowledge_id("partial_differential_equations", "3") == "kt-pde-3"


def test_adopt_tutorials_book_id_uses_course_abbr(repo):
    results = repo.adopt_tutorials("math_analysis", [{
        "set_no": "1", "name": "教程1", "position": "beginner", "intro": "x" * 120,
        "textbook_ref": [{"title": "微积分及其应用", "authors": [{"name": "比廷杰", "role": "author"}],
                          "language": "zh", "roles": ["textbook"]}],
        "exercise_ref": None, "parallel_ref": None,
    }])
    assert results[0]["knowledge_id"] == "kt-mathanalysis-1"
    books = repo.list_books(results[0]["knowledge_id"])
    assert books[0].book_id == "mathanalysis-b01"
