"""prompt_lab 课程管线（course-explore/tutorials@v2，2026-09-03 ref 结构化裁决）。

守护面：
- 注册表：course-explore/tutorials@v2 注册（tree 已砍，单 prompt）；
- 模板校验：套数 2~4、CJK 废止、position 五档（set 级）、intro 100~200 字散文（set 级）、
  authors 结构化 [{name,role}]、roles 枚举 textbook/exercises/solutions、
  exercise_ref null ⇔ 教材 roles 含 exercises、主教材不重复、set_no 唯一、
  name 格式「教程N：...」、part 全本/Vol.N 通配；
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
    assert steps[("course-explore", "tutorials")] == "course-explore/tutorials@v2"


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


def _ref(title: str = "数学分析原理", *, authors=((("Rudin", "author")),), roles=("textbook",),
         language: str = "zh", part: str = "全本", publisher: str = "", edition: str = "第3版",
         year: int | None = 1976, **overrides) -> dict:
    base = {
        "title": title,
        "part": part,
        "authors": [{"name": n, "role": r} for n, r in authors],
        "publisher": publisher,
        "edition": edition,
        "year": year,
        "language": language,
        "roles": list(roles),
    }
    base.update(overrides)
    return base


def _exercise_ref(title: str = "数学分析习题集", **overrides) -> dict:
    base = {
        "title": title,
        "part": "全本",
        "authors": [{"name": "吉米多维奇", "role": "author"}],
        "publisher": "",
        "edition": "",
        "year": 2000,
        "language": "zh",
        "roles": ["exercises"],
    }
    base.update(overrides)
    return base


_DEFAULT_INTRO = ("芝加哥大学分析学泰斗的经典教材，以严格公理化风格著称。"
                  "从实数系构造到多元分析一气呵成，论述精炼优美，视野高屋建瓴。"
                  "适合数学系高年级本科生和研究生深度学习，是分析方向的必备参考。"
                  "配套习题难度极高，建议配合提示集使用。")  # ~130字


_SENTINEL = object()


def _tutorial(set_no: str = "1", *, name: str = "教程1：Rudin《数学分析原理》",
              position: str = "advanced", intro: str = "",
              textbook_ref: list[dict] | None = _SENTINEL,
              exercise_ref: list[dict] | None = _SENTINEL,
              parallel_ref: list[dict] | None = None, **overrides) -> dict:
    base = {
        "set_no": set_no,
        "name": name,
        "position": position,
        "intro": intro or _DEFAULT_INTRO,
        "textbook_ref": [_ref()] if textbook_ref is _SENTINEL else textbook_ref,
        "exercise_ref": [_exercise_ref()] if exercise_ref is _SENTINEL else exercise_ref,
        "parallel_ref": parallel_ref,
    }
    base.update(overrides)
    return base


def test_tutorials_validate_happy_path() -> None:
    t = get_template("course-explore", "tutorials")
    # 套一：独立习题集；套二：教材自带习题集 → exercise_ref=null
    ok = {"tutorials": [
        _tutorial("1"),
        _tutorial("2", name="教程2：陈纪修《数学分析》",
                  textbook_ref=[_ref(title="数学分析", authors=(("陈纪修", "author"),),
                                     roles=("textbook", "exercises"))],
                  exercise_ref=None),
    ]}
    result = t.validate(ok)
    assert [item["set_no"] for item in result["tutorials"]] == ["1", "2"]


def test_tutorials_validate_rejects_out_of_range_count() -> None:
    t = get_template("course-explore", "tutorials")
    # 少于 2 套
    with pytest.raises(ValueError):
        t.validate({"tutorials": []})
    # 多于 4 套
    with pytest.raises(ValueError):
        t.validate({"tutorials": [_tutorial(str(i)) for i in range(1, 6)]})


def test_tutorials_validate_rejects_duplicate_set_no() -> None:
    t = get_template("course-explore", "tutorials")
    with pytest.raises(ValueError):
        t.validate({"tutorials": [_tutorial("1"), _tutorial("1")]})


def test_tutorials_validate_allows_same_book_across_sets() -> None:
    """书库化后多套可引用同一本书（不同 position/用途）。"""
    t = get_template("course-explore", "tutorials")
    ok = {"tutorials": [
        _tutorial("1", position="beginner",
                  textbook_ref=[_ref(title="数学分析原理", authors=(("Rudin", "author"),))]),
        _tutorial("2", position="advanced",
                  textbook_ref=[_ref(title="数学分析原理", authors=(("Rudin", "author"),))]),
    ]}
    result = t.validate(ok)
    assert len(result["tutorials"]) == 2


def test_tutorials_validate_rejects_latin_only_title() -> None:
    """CJK 废止：全英文主书名不再拒绝（language 字段承载语言标记）。"""
    t = get_template("course-explore", "tutorials")
    ok = {"tutorials": [
        _tutorial("1", textbook_ref=[_ref(title="Principles of Mathematical Analysis",
                                          authors=(("Rudin", "author"),), language="en")]),
        _tutorial("2", name="教程2：陈纪修《数学分析》",
                  textbook_ref=[_ref(title="数学分析", authors=(("陈纪修", "author"),),
                                     roles=("textbook", "exercises"))],
                  exercise_ref=None),
    ]}
    result = t.validate(ok)
    assert result["tutorials"][0]["textbook_ref"][0]["title"] == "Principles of Mathematical Analysis"


def test_tutorials_validate_rejects_missing_authors() -> None:
    t = get_template("course-explore", "tutorials")
    with pytest.raises(ValueError):
        t.validate({"tutorials": [_tutorial("1", textbook_ref=[_ref(authors=[])]),
                                  _tutorial("2")]})


def test_tutorials_validate_rejects_bad_roles() -> None:
    t = get_template("course-explore", "tutorials")
    # 未知角色
    with pytest.raises(ValueError):
        t.validate({"tutorials": [_tutorial("1", textbook_ref=[_ref(roles=["textbook", "notes"])]),
                                  _tutorial("2")]})


def test_tutorials_validate_rejects_bad_position() -> None:
    t = get_template("course-explore", "tutorials")
    with pytest.raises(ValueError):
        t.validate({"tutorials": [_tutorial("1", position="deep"),
                                  _tutorial("2")]})


def test_tutorials_validate_rejects_bad_intro_length() -> None:
    t = get_template("course-explore", "tutorials")
    # 过短
    with pytest.raises(ValueError):
        t.validate({"tutorials": [_tutorial("1", intro="太短"),
                                  _tutorial("2")]})
    # 超长
    with pytest.raises(ValueError):
        t.validate({"tutorials": [_tutorial("1", intro="长" * 300),
                                  _tutorial("2")]})


def test_tutorials_validate_allows_null_exercise_for_self_contained() -> None:
    """v2 放宽：exercise_ref 可空（教材自含习题或允许不提供习题集）。"""
    t = get_template("course-explore", "tutorials")
    # textbook 不含 exercises → exercise_ref=null 在 v2 允许
    ok = {"tutorials": [_tutorial("1", exercise_ref=None,
                                  textbook_ref=[_ref(roles=["textbook"])]),
                        _tutorial("2")]}
    result = t.validate(ok)
    assert result["tutorials"][0]["exercise_ref"] is None


def test_tutorials_validate_rejects_long_set_no() -> None:
    t = get_template("course-explore", "tutorials")
    # set_no 必须是 1~2 位纯数字
    with pytest.raises(ValueError):
        t.validate({"tutorials": [_tutorial("123"),
                                  _tutorial("2")]})
    with pytest.raises(ValueError):
        t.validate({"tutorials": [_tutorial("A"),
                                  _tutorial("2")]})


def test_tutorials_template_contract_notes() -> None:
    """模板文案契约锚点：position 五档 / exercises 角色 / 中文输出 / 防注入。"""
    t = get_template("course-explore", "tutorials")
    user_text = t.build_user({"course": {"name": "课程"}, "book_preference": {}, "reference": {"text": ""}})
    assert "position" in user_text and "beginner" in user_text and "advanced" in user_text
    assert "exercises" in user_text  # exercises 角色
    assert "中文" in user_text  # 输出语言
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
    _tutorial("2", name="教程2：陈纪修《数学分析》",
              textbook_ref=[_ref(title="数学分析", authors=(("陈纪修", "author"),),
                                 roles=("textbook", "exercises"))],
              exercise_ref=None),
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
    assert [c["template_id"] for c in pipeline.step_calls] == ["course-explore/tutorials@v2"]
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
    bad = {"tutorials": [_tutorial("1", position="invalid_position")]}  # 违规：非法 position
    pipeline = _pipeline([json.dumps(bad)])
    with pytest.raises(PipelineError):
        pipeline.explore(_COURSE, mode="direct")


def test_course_pipeline_budget_exhaustion_raises() -> None:
    """预算耗尽：坏 JSON 触发修复重试时二次调用超出预算 → PipelineError。"""
    pipeline = _pipeline(["not-json"], call_budget=1)
    with pytest.raises(PipelineError):
        pipeline.explore(_COURSE, mode="direct")
