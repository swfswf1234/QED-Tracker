"""prompt_lab 课程管线（course-explore/tutorials@v1，2026-08-26 用户裁决单步重新设计）。

守护面：
- 注册表：course-explore/tutorials@v1 注册（tree 已砍，单 prompt）；
- 模板校验：套数 2~4、title 中文优先（禁全英文主书名）、authors 非空、
  roles 枚举、position 枚举、intro 长度、exercise 同源才可空、主教材不重复、set_no 唯一；
- priors：tutorials 步键集注入（textbook_preference）；
- CoursePipeline：单步调用、payload 注入（course.note / book_preference / reference）、
  enrich（proposal_id/set_no）、坏 JSON 一次修复、预算耗尽、validate 失败。

固定 fixture（httpx.MockTransport），零公网。
"""

from __future__ import annotations

import json

import httpx
import pytest

from qed_tracker.prompt_lab import templates as templates_mod
from qed_tracker.prompt_lab.pipeline import CoursePipeline, PipelineError
from qed_tracker.prompt_lab.priors import PRIOR_KEYS_BY_STEP, get_prior_for_step
from qed_tracker.prompt_lab.templates import get_template

# ---------------- 注册表 ----------------


def test_registry_contains_course_tutorials_step() -> None:
    steps = {(t["task"], t["step"]): t["id"] for t in templates_mod.list_templates()}
    assert steps[("course-explore", "tutorials")] == "course-explore/tutorials@v1"


def test_templates_stay_domain_neutral() -> None:
    """守护：新增 course-explore 模板文本同样保持学科中立（专属知识走 priors.py）。"""
    source = templates_mod.__file__
    import pathlib

    text = pathlib.Path(source).read_text(encoding="utf-8")
    bound_words = ("数学", "分析学", "代数", "概率", "物理", "量子", "化学", "生物", "计算机", "经济学")
    hits = [w for w in bound_words if w in text]
    assert not hits, f"模板文本含学科绑定词：{hits}"


# ---------------- priors ----------------


def test_priors_tutorials_step_injects_textbook_preference() -> None:
    assert PRIOR_KEYS_BY_STEP["tutorials"] == ("textbook_preference",)
    full = get_prior_for_step("高等数学", "tutorials")
    assert "textbook_preference" in full
    assert get_prior_for_step("不存在的领域", "tutorials") == {}


# ---------------- 模板校验 ----------------


def _book(title: str = "数学分析原理", *, authors=("Rudin",), roles=("textbook",),
          position: str = "advanced", intro: str = "", original: str = "Principles of Mathematical Analysis",
          **overrides) -> dict:
    base = {
        "title": title,
        "original_title": original,
        "authors": list(authors),
        "version": {"edition": "第3版", "publisher": "", "year": 1976},
        "roles": list(roles),
        "position": position,
        "intro": intro or ("芝加哥大学分析学泰斗的经典教材，以严格公理化风格著称。"
                           "作者视野高屋建瓴，论述精炼优美，是深度研究分析的必读之选。" * 2),
    }
    base.update(overrides)
    return base


def _exercise(title: str = "数学分析习题集", **overrides) -> dict:
    base = {
        "title": title,
        "original_title": "",
        "authors": ["吉米多维奇"],
        "version": {"edition": "", "publisher": "", "year": 2000},
        "roles": ["exercises"],
        "position": "comprehensive",
        "intro": ("经典配套习题集，覆盖从基础到综合难度的系统训练。题目按章编排、由浅入深，"
                  "与教材对照阅读可巩固概念、训练计算与证明能力；难度定位全面系统，"
                  "适合课下跟练与考研复习使用，是这门课程公认的必备训练手册。" * 2),
    }
    base.update(overrides)
    return base


def _tutorial(set_no: str = "1", *, set_name: str = "教程1：数学分析原理（Rudin）",
              textbook: dict | None = None, exercise: dict | None = None,
              reason: str = "经典严格教材与高阶配套，适合深度研究", **overrides) -> dict:
    base = {
        "set_no": set_no,
        "set_name": set_name,
        "textbook": textbook or _book(),
        "exercise": exercise if exercise is not None else _exercise(),
        "reason": reason,
    }
    base.update(overrides)
    return base


def test_tutorials_validate_happy_path() -> None:
    t = get_template("course-explore", "tutorials")
    # 套一：独立习题集；套二：教材自带习题集 → exercise=null
    ok = {"tutorials": [
        _tutorial("1"),
        _tutorial("2", set_name="教程2：数学分析（陈纪修）",
                  textbook=_book(title="数学分析", authors=("陈纪修",), roles=("textbook", "exercises"),
                                 position="comprehensive", original="数学分析"),
                  exercise=None),
    ]}
    result = t.validate(ok)
    assert [item["set_no"] for item in result["tutorials"]] == ["1", "2"]


def test_tutorials_validate_rejects_out_of_range_count() -> None:
    t = get_template("course-explore", "tutorials")
    with pytest.raises(ValueError):
        t.validate({"tutorials": [_tutorial("1")]})
    with pytest.raises(ValueError):
        t.validate({"tutorials": [_tutorial(str(i)) for i in range(1, 6)]})


def test_tutorials_validate_rejects_duplicate_set_no() -> None:
    t = get_template("course-explore", "tutorials")
    with pytest.raises(ValueError):
        t.validate({"tutorials": [_tutorial("1"), _tutorial("1")]})


def test_tutorials_validate_rejects_duplicate_textbook_title() -> None:
    t = get_template("course-explore", "tutorials")
    with pytest.raises(ValueError):
        t.validate({"tutorials": [
            _tutorial("1"),
            _tutorial("2", textbook=_book(title="数学分析原理", authors=("其他作者",))),
        ]})


def test_tutorials_validate_rejects_latin_only_title() -> None:
    """title 中文优先：全英文/拉丁字符主书名拒绝（original_title 承载原版名）。"""
    t = get_template("course-explore", "tutorials")
    with pytest.raises(ValueError):
        t.validate({"tutorials": [_tutorial("1", textbook=_book(title="Principles of Mathematical Analysis"))]})


def test_tutorials_validate_rejects_missing_authors() -> None:
    t = get_template("course-explore", "tutorials")
    with pytest.raises(ValueError):
        t.validate({"tutorials": [_tutorial("1", textbook=_book(authors=[]))]})


def test_tutorials_validate_rejects_bad_roles() -> None:
    t = get_template("course-explore", "tutorials")
    # textbook 必须含 textbook 角色
    with pytest.raises(ValueError):
        t.validate({"tutorials": [_tutorial("1", textbook=_book(roles=["exercises"]))]})
    # 未知角色
    with pytest.raises(ValueError):
        t.validate({"tutorials": [_tutorial("1", textbook=_book(roles=["textbook", "notes"]))]})


def test_tutorials_validate_rejects_bad_position() -> None:
    t = get_template("course-explore", "tutorials")
    with pytest.raises(ValueError):
        t.validate({"tutorials": [_tutorial("1", textbook=_book(position="deep"))]})


def test_tutorials_validate_rejects_bad_intro_length() -> None:
    t = get_template("course-explore", "tutorials")
    # 过短
    with pytest.raises(ValueError):
        t.validate({"tutorials": [_tutorial("1", textbook=_book(intro="太短"))]})
    # 超长
    with pytest.raises(ValueError):
        t.validate({"tutorials": [_tutorial("1", textbook=_book(intro="长" * 400))]})


def test_tutorials_validate_rejects_null_exercise_unless_same_source() -> None:
    """exercise 可空仅当 textbook.roles 含 exercises（同源）；否则必须提供。"""
    t = get_template("course-explore", "tutorials")
    with pytest.raises(ValueError):
        t.validate({"tutorials": [_tutorial("1", exercise=None)]})


def test_tutorials_validate_rejects_long_reason() -> None:
    t = get_template("course-explore", "tutorials")
    with pytest.raises(ValueError):
        t.validate({"tutorials": [_tutorial("1", reason="长" * 51)]})


def test_tutorials_template_contract_notes() -> None:
    """模板文案契约锚点：中文书名优先 / 六要素 intro / 同源可空 / position 枚举。"""
    t = get_template("course-explore", "tutorials")
    user_text = t.build_user({"course": {"name": "课程"}, "book_preference": {}, "reference": {"text": ""}})
    assert "中文" in user_text  # 书名中文优先
    assert "original_title" in user_text  # 英文原名单独承载
    assert "position" in user_text and "beginner" in user_text and "advanced" in user_text
    assert "exercises" in user_text and "同源" in user_text  # 同源可空规则
    assert "作者" in user_text and "经典" in user_text  # 六要素锚点
    assert "不可信" in t.system  # 防注入


# ---------------- 管线 fixtures ----------------


def _pipeline(responses: list[str], **overrides) -> CoursePipeline:
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": queue.pop(0)}, "finish_reason": "stop"}],
                                         "usage": {"total_tokens": 10}}, request=request)

    defaults = dict(api_key="k", call_budget=9)
    defaults.update(overrides)
    return CoursePipeline(client=httpx.Client(transport=httpx.MockTransport(handler)), **defaults)


_COURSE = {
    "course_id": "mathematical_analysis",
    "name": "数学分析",
    "aliases": ["数学分析（高等数学）"],
    "stage": "本科基础",
    "prerequisites": ["point_set_topology"],
    "note": "数学系的第一门严格分析课。以 ε-δ 极限语言重建微积分。",
}

_TUTORIALS_RESP = {"tutorials": [
    _tutorial("1"),
    _tutorial("2", set_name="教程2：数学分析（陈纪修）",
              textbook=_book(title="数学分析", authors=("陈纪修",), roles=("textbook", "exercises"),
                             position="comprehensive", original="数学分析"),
              exercise=None),
]}


# ---------------- 管线行为 ----------------


def test_course_pipeline_runs_single_step_and_enriches() -> None:
    pipeline = _pipeline([json.dumps(_TUTORIALS_RESP)])
    report = pipeline.explore(_COURSE, mode="direct")
    assert len(report["tutorials"]) == 2
    first = report["tutorials"][0]
    assert first["proposal_id"].startswith("pp_")
    assert first["set_no"] == "1"
    assert [c["step"] for c in pipeline.step_calls] == ["tutorials"]
    assert [c["template_id"] for c in pipeline.step_calls] == ["course-explore/tutorials@v1"]
    assert pipeline.calls == 1


def test_course_pipeline_payload_carries_note_prior_and_reference() -> None:
    captured: list[dict] = []
    queue = [json.dumps(_TUTORIALS_RESP)]

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": queue.pop(0)}, "finish_reason": "stop"}],
                                         "usage": {"total_tokens": 10}}, request=request)

    pipeline = CoursePipeline(client=httpx.Client(transport=httpx.MockTransport(handler)),
                              api_key="k", call_budget=9)
    pipeline.explore(_COURSE, domain_name="高等数学", mode="text", ref_text="用户偏好：需要习题讲解视频配套。")
    user_text = captured[0]["messages"][1]["content"]
    assert "数学系的第一门严格分析课" in user_text  # course.description 注入
    assert "textbook_preference" in user_text  # priors 注入
    assert '"mode": "text"' in user_text  # reference 段
    assert "习题讲解视频" in user_text


def test_course_pipeline_repairs_bad_json_once() -> None:
    pipeline = _pipeline(["not-json", json.dumps(_TUTORIALS_RESP)])
    report = pipeline.explore(_COURSE, mode="direct")
    assert len(report["tutorials"]) == 2
    assert pipeline.calls == 2


def test_course_pipeline_wraps_validate_failure() -> None:
    bad = {"tutorials": [_tutorial("1", exercise=None)]}  # 违规：非同一来源却 null
    pipeline = _pipeline([json.dumps(bad)])
    with pytest.raises(PipelineError):
        pipeline.explore(_COURSE, mode="direct")


def test_course_pipeline_budget_exhaustion_raises() -> None:
    """预算耗尽：坏 JSON 触发修复重试时二次调用超出预算 → PipelineError。"""
    pipeline = _pipeline(["not-json"], call_budget=1)
    with pytest.raises(PipelineError):
        pipeline.explore(_COURSE, mode="direct")
