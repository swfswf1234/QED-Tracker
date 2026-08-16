"""课程体系读取（qed_course 共享表）定向测试（SQLite 内存）。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.courses import list_courses, load_course, set_repository
from qed_tracker.db.knowledge_repository import KnowledgeRepository
from qed_tracker.db.models import Base, QedCourse, QedDomain


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    from qed_tracker.database import utc_now

    now = utc_now()
    session.add(QedDomain(domain_id="math", name="数学", description="d", stages=["本科基础", "QE冲刺"],
                          created_at=now, updated_at=now))
    session.add(QedCourse(course_id="01_math_analysis", domain_id="math", sort_order=0, name="数学分析",
                          aliases=["高等数学（工科称呼）"], stage="本科基础", prerequisites=[], related_targets=[],
                          created_at=now, updated_at=now))
    session.add(QedCourse(course_id="02_linear_algebra", domain_id="math", sort_order=1, name="高等代数",
                          aliases=["线性代数"], stage="本科基础", prerequisites=[], related_targets=[],
                          created_at=now, updated_at=now))
    session.commit()
    yield KnowledgeRepository(factory)
    engine.dispose()


@pytest.fixture(autouse=True)
def _reset_repository():
    set_repository(None)
    yield
    set_repository(None)


def test_list_courses_contains_math(repo) -> None:
    set_repository(repo)
    assert "math" in list_courses()


def test_load_math_course_count_and_stages(repo) -> None:
    set_repository(repo)
    data = load_course("math")
    assert len(data.courses) == 2
    assert data.stages == ("本科基础", "QE冲刺")


def test_linear_algebra_alias_high_algebra(repo) -> None:
    set_repository(repo)
    course = next(c for c in load_course("math").courses if c.course_id == "02_linear_algebra")
    assert "线性代数" in course.aliases


def test_course_fields(repo) -> None:
    set_repository(repo)
    course = next(c for c in load_course("math").courses if c.course_id == "01_math_analysis")
    assert course.name == "数学分析"
    assert course.stage == "本科基础"
    assert course.prerequisites == ()


def test_unknown_course_raises(repo) -> None:
    set_repository(repo)
    with pytest.raises(ValueError):
        load_course("nonexistent")


def test_without_repository_raises_helpful_error() -> None:
    with pytest.raises(ValueError, match="数据库未配置"):
        load_course("math")
