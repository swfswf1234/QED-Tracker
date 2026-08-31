"""课程教材层标准答案范本契约守护（docs/knowledge/course-tutorials-math-golden.json）。

模块职责：确保 golden 范本与 prompt_lab tutorials 契约不漂移——
- 01/02 课程逐套通过 templates._validate_tutorials（完整契约校验）；
- 11 课程两套均教材自带习题（各自官方题解为英文书，契约书名强制中文不可作独立
  exercise 条目），exercise_count=0 不满足 v1「至少一套须含独立习题集」全局强制：
  逐条目按同一校验器把关 + 显式断言该已知偏离，v2 放宽事项登记于
  golden meta.contract_notes 与 docs/plans/2026-08-prompt-optimization-progress.md。
实现状态：Implemented
被测代码：docs/knowledge/course-tutorials-math-golden.json、
src/qed_tracker/prompt_lab/templates.py（_validate_tutorials/_validate_book_entry）
守护面：prompt_lab（范本与契约一致性）
失效后果：范本与管线契约漂移——prompt 优化对照失真、A2 采纳输入格式走样。
"""

import json
from pathlib import Path

import pytest

from qed_tracker.prompt_lab.templates import _validate_book_entry, _validate_tutorials

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "docs" / "knowledge" / "course-tutorials-math-golden.json"


def _load_golden() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def _tutorials(course_id: str) -> list[dict]:
    courses = {c["course_id"]: c["tutorials"] for c in _load_golden()["courses"]}
    return courses[course_id]


def test_golden_file_exists_with_expected_coverage() -> None:
    data = _load_golden()
    assert data["meta"]["contract"] == "course-explore/tutorials@v1"
    assert {c["course_id"] for c in data["courses"]} == {
        "01_math_analysis",
        "02_linear_algebra",
        "11_probability",
    }
    # 11 号课两套制放宽事项必须登记在 meta（v2 放宽前的已知偏离）
    assert any("至少一套须含独立习题集" in note for note in data["meta"]["contract_notes"])


@pytest.mark.parametrize("course_id", ["01_math_analysis", "02_linear_algebra"])
def test_full_contract_courses_pass_validator(course_id: str) -> None:
    normalized = _validate_tutorials({"tutorials": _tutorials(course_id)})
    assert 2 <= len(normalized["tutorials"]) <= 4


def test_probability_course_entries_valid_with_relaxed_exercise_rule() -> None:
    """11 号课：逐条目按同一校验器把关；exercise 全 null 为登记在案的已知偏离。"""
    tutorials = _tutorials("11_probability")
    assert 2 <= len(tutorials) <= 4
    seen_set_no: set[str] = set()
    seen_titles: set[str] = set()
    for item in tutorials:
        set_no = item["set_no"]
        assert set_no and set_no not in seen_set_no
        seen_set_no.add(set_no)
        assert item["set_name"]
        textbook = _validate_book_entry(
            item["textbook"], f"tutorials[{set_no}].textbook", require_textbook=True
        )
        assert textbook["title"].casefold() not in seen_titles
        seen_titles.add(textbook["title"].casefold())
        # exercise=null 仅当教材自带习题（roles 含 exercises）
        assert "exercises" in textbook["roles"]
        assert item["exercise"] is None
        assert item["reason"]
    # 显式登记：当前 v1 契约下 11 号课 exercise_count=0（v2 放宽前不通过全局校验）
    with pytest.raises(ValueError, match="至少一套须含习题集"):
        _validate_tutorials({"tutorials": tutorials})
