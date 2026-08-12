from __future__ import annotations

import pytest

from qed_tracker.courses import Course, list_courses, load_course


def test_list_courses_contains_math() -> None:
    assert "math" in list_courses()


def test_load_math_course_count_and_stages() -> None:
    data = load_course("math")
    assert len(data.courses) == 14
    assert data.stages == ("本科基础", "本科进阶", "研究生基础", "QE冲刺")


def test_three_foundational_courses_have_no_prerequisites() -> None:
    data = load_course("math")
    foundational = [c for c in data.courses if not c.prerequisites]
    assert {c.course_id for c in foundational} == {
        "00_probability_stats", "01_math_analysis", "02_linear_algebra",
    }


def test_linear_algebra_alias_high_algebra() -> None:
    data = load_course("math")
    course = next(c for c in data.courses if c.course_id == "02_linear_algebra")
    assert "线性代数" in course.aliases


def test_course_fields() -> None:
    data = load_course("math")
    course: Course = next(c for c in data.courses if c.course_id == "03_topology")
    assert course.name == "点集拓扑"
    assert course.stage == "本科基础"
    assert course.prerequisites == ("01_math_analysis", "02_linear_algebra")


def test_unknown_course_raises() -> None:
    with pytest.raises(ValueError):
        load_course("nonexistent")
