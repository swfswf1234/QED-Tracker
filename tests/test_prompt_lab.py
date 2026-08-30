"""prompt_lab 模板注册表与领域管线契约（QED-043 · v3 三步管线，2026-08-24 用户裁决 P12/P13）。

守护面：
- 注册表：domain@v2 / courses@v4 / path@v4 三步齐全（describe 已删除）；
- 学科中立：templates.py 禁止学科绑定词（领域专属知识归 priors.py）；
- priors：精确域名匹配，未命中不影响其它领域；
- 各步 validate：数量/枚举/引用/无环/禁拆学期等规则；
- graph TD 渲染：tier 分组 + 前置边（由 prerequisites 服务端推导）；
- 管线：三步顺序调用、坏 JSON 一次修复、跨步校验、名称确认提前结束/人工确认放行、报告聚合。

固定 fixture（httpx.MockTransport），零公网。
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, text

from qed_tracker.prompt_lab import templates as templates_mod
from qed_tracker.prompt_lab.pipeline import (
    DomainPipeline,
    NameConfirmationRequired,
    PipelineError,
)
from qed_tracker.prompt_lab.priors import PRIOR_KEYS_BY_STEP, get_prior, get_prior_for_step
from qed_tracker.prompt_lab.templates import TIERS, get_template, render_graph_td

# ---------------- 注册表 ----------------


def test_registry_contains_three_steps_with_ids() -> None:
    steps = {(t["task"], t["step"]): t["id"] for t in templates_mod.list_templates()}
    assert set(k for k in steps if k[0] == "domain-explore") == {
        ("domain-explore", "domain"),
        ("domain-explore", "courses"),
        ("domain-explore", "path"),
    }
    assert steps[("domain-explore", "domain")] == "domain-explore/domain@v3"
    assert steps[("domain-explore", "courses")] == "domain-explore/courses@v6"
    assert steps[("domain-explore", "path")] == "domain-explore/path@v5"


def test_unknown_template_raises() -> None:
    with pytest.raises(KeyError):
        get_template("domain-explore", "describe")
    with pytest.raises(KeyError):
        get_template("domain-explore", "scope")


def test_templates_are_domain_neutral() -> None:
    """守护：模板文本学科中立——领域只由输入决定，专属知识一律走 priors.py。"""
    source = Path(templates_mod.__file__).read_text(encoding="utf-8")
    bound_words = ("数学", "分析学", "代数", "概率", "物理", "量子", "化学", "生物", "计算机", "经济学")
    hits = [w for w in bound_words if w in source]
    assert not hits, f"模板文本含学科绑定词：{hits}"


# ---------------- priors ----------------


def test_prior_matches_exact_domain_only() -> None:
    prior = get_prior("高等数学")
    assert prior.get("textbook_preference")
    assert prior.get("tracks_hint")
    assert list(get_prior("高等数学 ").keys()) == list(prior.keys())  # 去空白后命中
    assert get_prior("物理学") == {}
    assert get_prior("不存在的领域") == {}


def test_prior_computer_science_registered() -> None:
    """QED-050：计算机领域先验注册（计算机基础 + LLM 前沿语境）。"""
    prior = get_prior("计算机科学与技术")
    assert prior.get("naming_convention")
    assert prior.get("anchor_courses")
    for track_name in ("程序设计与算法", "计算机系统", "人工智能与机器学习"):
        assert track_name in prior["tracks_hint"]
    assert "大语言模型" in prior.get("capstone_hint", "")


def test_priors_tracks_hint_aligns_four_tracks() -> None:
    """知识文档定稿后主线提示对齐四条经典主线（用户裁决 2026-08-26）。"""
    hint = get_prior("高等数学")["tracks_hint"]
    for track_name in ("分析学", "代数学", "概率与统计", "几何与拓扑"):
        assert track_name in hint


def test_priors_naming_convention_resolves_domain_aliases() -> None:
    """「数学」「数学（高等数学）」等称呼应能归一到规范名「高等数学」。"""
    naming = get_prior("高等数学")["naming_convention"]
    assert "高等数学" in naming
    assert "数学（高等数学）" in naming


def test_get_prior_for_step_trims_by_step() -> None:
    """分步裁剪注入表：domain=4 键 / courses=全量 / path=仅 capstone_hint。"""
    assert set(PRIOR_KEYS_BY_STEP["domain"]) == {
        "naming_convention", "tracks_hint", "anchor_courses", "level_default",
    }
    assert set(PRIOR_KEYS_BY_STEP["path"]) == {"capstone_hint"}
    full = get_prior("高等数学")
    assert set(get_prior_for_step("高等数学", "domain")) == set(PRIOR_KEYS_BY_STEP["domain"])
    assert set(get_prior_for_step("高等数学", "courses")) == set(full)
    assert get_prior_for_step("高等数学", "path") == {"capstone_hint": full["capstone_hint"]}
    assert get_prior_for_step("物理学", "domain") == {}


# ---------------- step1 domain 校验 ----------------

_VALID_NAME_CHECK = {"valid": True, "reason": "指代完整的课程体系，合格", "suggested_name": ""}


def test_domain_validate_rules() -> None:
    domain_t = get_template("domain-explore", "domain")
    ok = {
        "name_check": dict(_VALID_NAME_CHECK),
        "final_name": "高等数学",
        "description": "大学阶段的数学核心课程体系，覆盖分析、代数等主干直至硕士主课。",
        "level": "本科-硕士",
        "classic_tracks": [{"name": "分析", "summary": "极限与分析方向", "kind": "main"}, {"name": "代数", "summary": "代数结构方向", "kind": "main"}],
        "entry_requirements": "微积分基础",
    }
    assert domain_t.validate(ok) == ok
    # 描述超长（>200）
    with pytest.raises(ValueError):
        domain_t.validate({**ok, "description": "长" * 201})
    # 主线数量越界（>4）
    with pytest.raises(ValueError):
        domain_t.validate({**ok, "classic_tracks": [{"name": f"t{i}", "summary": "s"} for i in range(5)]})
    # 主线名重复
    with pytest.raises(ValueError):
        domain_t.validate({**ok, "classic_tracks": [{"name": "t", "summary": "s"}, {"name": "t", "summary": "x"}]})
    # kind 非法
    with pytest.raises(ValueError):
        domain_t.validate({**ok, "classic_tracks": [{"name": "t", "summary": "s", "kind": "invalid"}]})
    # entry_requirements 须为字符串（原数组契约已退役）
    with pytest.raises(ValueError):
        domain_t.validate({**ok, "entry_requirements": ["微积分基础"]})
    # 缺 name_check
    with pytest.raises(ValueError):
        domain_t.validate({k: v for k, v in ok.items() if k != "name_check"})


def test_domain_template_v2_contract_notes() -> None:
    """探索轮裁决五项文案要素：括号限定名合法化/scope 权威边界/description 质量锚点/下游用途/中文输出。"""
    domain_t = get_template("domain-explore", "domain")
    user_text = domain_t.build_user(
        {"domain_name": "示例领域", "scope_hint": _SCOPE_HINT, "user_input": "", "prior_knowledge": {}}
    )
    assert "括号" in user_text  # 带括号的学科限定名是合法名称
    assert "范围边界" in user_text and "权威" in user_text  # scope_hint 职责升级
    assert "定性" in user_text  # description 第一层质量锚点
    assert "套话" in user_text  # 禁空泛套话
    assert "学习顺序" in user_text  # 下游用途说明
    assert "中文" in (domain_t.system + user_text)  # 显式中文输出（system 段声明）


# ---------------- step2 courses 校验 ----------------


def _course(slug: str, name: str, **overrides) -> dict:
    base = {
        "slug": slug, "name": name, "aliases": [],
        "track": "", "summary": "这是一门足够长的课程简介文本用于通过最短长度校验。",
        "university_basis": ["清华大学 对应课程"],
    }
    base.update(overrides)
    return base


def _ok_rest() -> list[dict]:
    return [_course("course_b", "课程乙"), _course("course_c", "课程丙"), _course("course_d", "课程丁")]


def test_courses_validate_rules() -> None:
    courses_t = get_template("domain-explore", "courses")
    ok = {"courses": [_course("math_analysis", "数学分析"), _course("algebra", "高等代数"),
                      _course("real_analysis", "实分析"), _course("topology", "点集拓扑")]}
    assert courses_t.validate(ok) == ok
    # 精炼探索下限放宽：3 门合法（courses@v6，dry-run count_range 3~5 支撑）
    refined = courses_t.validate({"courses": ok["courses"][:3]})
    assert len(refined["courses"]) == 3
    # 数量越界（<3）
    with pytest.raises(ValueError):
        courses_t.validate({"courses": ok["courses"][:2]})
    # 拆学期命名（数字结尾）
    with pytest.raises(ValueError):
        courses_t.validate({"courses": [_course("a", "数学分析1"), *_ok_rest()]})
    # 拆学期命名（括号序号）
    with pytest.raises(ValueError):
        courses_t.validate({"courses": [_course("a", "数学分析（一）"), *_ok_rest()]})
    # summary 过短
    with pytest.raises(ValueError):
        courses_t.validate({"courses": [_course("a", "课程", summary="太短"), *_ok_rest()]})
    # university_basis 可为空数组或缺省（V1 放宽：确无对应依据时不强制编造）
    ok_empty = courses_t.validate({"courses": [_course("crs", "课程", university_basis=[]), *_ok_rest()]})
    assert ok_empty["courses"][0]["university_basis"] == []
    missing = _course("crs2", "课程")
    missing.pop("university_basis")
    courses_t.validate({"courses": [missing, *_ok_rest()]})
    # 连字符 slug
    with pytest.raises(ValueError):
        courses_t.validate({"courses": [_course("algorithms-and-ds", "课程"), *_ok_rest()]})


def test_courses_template_forbids_hyphen_slugs() -> None:
    """slug 规则必须显式禁止连字符并给出下划线示例（真实评估中 LLM 曾输出 algorithms-and-data-structures）。"""
    courses_t = get_template("domain-explore", "courses")
    user_text = courses_t.build_user({"domain": {}, "prior_knowledge": {}})
    assert "连字符" in user_text
    assert "_" in user_text


# ---------------- step3 path 校验 ----------------


def test_path_assignments_rules() -> None:
    path_t = get_template("domain-explore", "path")
    ok = {"assignments": [
        {"slug": "math_analysis", "tier": "基础", "prerequisites": []},
        {"slug": "real_analysis", "tier": "主干", "prerequisites": ["math_analysis"]},
    ], "notes": ""}
    assert path_t.validate(ok) == ok
    # tier 越界
    with pytest.raises(ValueError):
        path_t.validate({"assignments": [{"slug": "a", "tier": "选修", "prerequisites": []}]})
    # 自环前置
    with pytest.raises(ValueError):
        path_t.validate({"assignments": [{"slug": "a", "tier": "基础", "prerequisites": ["a"]}]})
    # 前置成环（a↔b）
    cyclic = {"assignments": [
        {"slug": "a", "tier": "基础", "prerequisites": ["b"]},
        {"slug": "b", "tier": "分支", "prerequisites": ["a"]},
    ], "notes": ""}
    with pytest.raises(ValueError):
        path_t.validate(cyclic)


def test_path_stage_tiers_follow_ordered_enum() -> None:
    assert TIERS == ("基础", "主干", "分支", "前沿")


# ---------------- graph TD 渲染 ----------------


def test_render_graph_td_groups_by_tier_with_edges() -> None:
    courses = [
        {"slug": "math_analysis", "name": "数学分析", "tier": "基础"},
        {"slug": "algebra", "name": "高等代数", "tier": "基础"},
        {"slug": "real_analysis", "name": "实分析", "tier": "主干"},
    ]
    text_out = render_graph_td(courses, [{"from": "math_analysis", "to": "real_analysis"}])
    assert text_out.startswith("graph TD")
    assert "math_analysis[数学分析]" in text_out
    assert "%% 基础" in text_out and "%% 主干" in text_out
    assert "math_analysis --> real_analysis" in text_out


# ---------------- 管线 fixtures ----------------

_SCOPE_HINT = "大学往上的知识内容（本科-硕士阶段）"
_DOMAIN_RESP = {
    "name_check": dict(_VALID_NAME_CHECK),
    "final_name": "高等数学",
    "description": "大学阶段的数学核心课程体系。",
    "level": "本科-硕士",
    "classic_tracks": [{"name": "分析", "summary": "极限与分析", "kind": "main"}, {"name": "代数", "summary": "代数结构", "kind": "main"}],
    "entry_requirements": "微积分基础",
}
_COURSES_RESP = {"courses": [
    _course("math_analysis", "数学分析", aliases=["微积分"], track="分析"),
    _course("algebra", "高等代数", aliases=["线性代数"], track="代数"),
    _course("topology", "点集拓扑", track="分析"),
    _course("real_analysis", "实分析", track="分析"),
]}
_PATH_RESP = {"assignments": [
    {"slug": "math_analysis", "tier": "基础", "prerequisites": []},
    {"slug": "algebra", "tier": "基础", "prerequisites": []},
    {"slug": "topology", "tier": "分支", "prerequisites": ["math_analysis"]},
    {"slug": "real_analysis", "tier": "主干", "prerequisites": ["math_analysis", "topology"]},
], "notes": ""}


def _pipeline(responses: list[str], **overrides) -> DomainPipeline:
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": queue.pop(0)}, "finish_reason": "stop"}],
                                         "usage": {"total_tokens": 10}}, request=request)

    defaults = dict(api_key="k", call_budget=9)
    defaults.update(overrides)
    return DomainPipeline(client=httpx.Client(transport=httpx.MockTransport(handler)), **defaults)


# ---------------- 管线行为 ----------------


def test_domain_pipeline_runs_three_steps_and_aggregates_report() -> None:
    pipeline = _pipeline([json.dumps(_DOMAIN_RESP), json.dumps(_COURSES_RESP), json.dumps(_PATH_RESP)])
    report = pipeline.explore("高等数学", scope_hint=_SCOPE_HINT, mode="direct")
    assert report["domain"]["final_name"] == "高等数学"
    assert report["domain"]["level"] == "本科-硕士"
    assert len(report["courses"]) == 4
    merged = {c["slug"]: c for c in report["courses"]}
    assert merged["math_analysis"]["tier"] == "基础"
    assert merged["math_analysis"]["prerequisites"] == []
    assert merged["real_analysis"]["prerequisites"] == ["math_analysis", "topology"]
    assert merged["math_analysis"]["track"] == "分析"
    assert report["path"]["graph_td"].startswith("graph TD")
    assert pipeline.calls == 3
    assert [c["step"] for c in pipeline.step_calls] == ["domain", "courses", "path"]
    assert [c["template_id"] for c in pipeline.step_calls] == [
        "domain-explore/domain@v3", "domain-explore/courses@v6", "domain-explore/path@v5",
    ]


def test_pipeline_payload_carries_prior_and_slugs() -> None:
    captured: list[dict] = []
    queue = [json.dumps(_DOMAIN_RESP), json.dumps(_COURSES_RESP), json.dumps(_PATH_RESP)]

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": queue.pop(0)}, "finish_reason": "stop"}],
                                         "usage": {"total_tokens": 10}}, request=request)

    pipeline = DomainPipeline(client=httpx.Client(transport=httpx.MockTransport(handler)),
                              api_key="k", call_budget=9)
    pipeline.explore("高等数学", mode="direct")
    domain_user = captured[0]["messages"][1]["content"]
    courses_user = captured[1]["messages"][1]["content"]
    path_user = captured[2]["messages"][1]["content"]
    # step1 注入分步裁剪后的先验（domain 步不含教材偏好/顶峰提示）与默认范围
    assert "prior_knowledge" in domain_user
    assert "naming_convention" in domain_user
    assert "textbook_preference" not in domain_user
    assert _SCOPE_HINT in domain_user
    # step2 携带权威范围、主线全量对象（含 summary）
    assert '"scope_hint"' in courses_user
    assert '"summary"' in courses_user
    # step3 注入课程清单（slug+name+track+summary，作为前置判断依据）
    assert '"slug": "math_analysis"' in path_user
    assert '"summary"' in path_user
    assert '"track": "分析"' in path_user


def test_pipeline_repairs_bad_json_once_per_step() -> None:
    pipeline = _pipeline(["not-json", json.dumps(_DOMAIN_RESP), json.dumps(_COURSES_RESP),
                          json.dumps(_PATH_RESP)])
    report = pipeline.explore("高等数学", mode="direct")
    assert report["domain"]["final_name"] == "高等数学"
    assert pipeline.calls == 4


def test_pipeline_stops_for_name_confirmation() -> None:
    bad_name = {**_DOMAIN_RESP,
                "name_check": {"valid": False, "reason": "疑似拼写错误", "suggested_name": "高等数学"}}
    pipeline = _pipeline([json.dumps(bad_name)])
    with pytest.raises(NameConfirmationRequired) as exc_info:
        pipeline.explore("高凳数学", mode="direct")
    assert exc_info.value.name_check["suggested_name"] == "高等数学"
    assert pipeline.calls == 1  # 提前结束，不跑后续步骤


def test_pipeline_confirm_name_override_continues_with_user_name() -> None:
    """P12 弹窗流：人工确认保留原名后，以 override 名跳过确认并贯穿后续步骤。"""
    suggested_other = {**_DOMAIN_RESP,
                       "name_check": {"valid": False, "reason": "建议规范化", "suggested_name": "数学"},
                       "final_name": "数学"}
    pipeline = _pipeline([json.dumps(suggested_other), json.dumps(_COURSES_RESP), json.dumps(_PATH_RESP)])
    report = pipeline.explore("高等数学", mode="direct", confirm_name_override="高等数学")
    assert report["domain"]["final_name"] == "高等数学"  # 用户拍板的名字
    assert len(report["courses"]) == 4
    assert pipeline.calls == 3


def test_pipeline_rejects_track_outside_classic_tracks() -> None:
    bad_courses = {"courses": [
        _course("math_analysis", "数学分析", track="不存在的线"),
        *_ok_rest(),
    ]}
    pipeline = _pipeline([json.dumps(_DOMAIN_RESP), json.dumps(bad_courses), json.dumps(bad_courses)])
    with pytest.raises(PipelineError):
        pipeline.explore("高等数学", mode="direct")


def test_pipeline_rejects_incomplete_assignments() -> None:
    bad_path = {"assignments": [{"slug": "ghost", "tier": "基础", "prerequisites": []}], "notes": ""}
    pipeline = _pipeline([json.dumps(_DOMAIN_RESP), json.dumps(_COURSES_RESP),
                          json.dumps(bad_path), json.dumps(bad_path)])
    with pytest.raises(PipelineError):
        pipeline.explore("高等数学", mode="direct")


def test_pipeline_budget_exhaustion_raises() -> None:
    pipeline = _pipeline([json.dumps(_DOMAIN_RESP)], call_budget=1)
    with pytest.raises(PipelineError):
        pipeline.explore("高等数学", mode="direct")


def test_pipeline_writes_per_step_template_ids_to_call_log() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE qed_llm_calls (id INTEGER PRIMARY KEY AUTOINCREMENT, service VARCHAR(32),"
            " mode VARCHAR(16), provider VARCHAR(32), model VARCHAR(64), endpoint VARCHAR(16),"
            " prompt_template VARCHAR(255), prompt TEXT, response TEXT, duration_ms INT,"
            " status VARCHAR(16), error VARCHAR(500), created_at DATETIME)"
        ))
    queue = [json.dumps(_DOMAIN_RESP), json.dumps(_COURSES_RESP), json.dumps(_PATH_RESP)]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": queue.pop(0)}, "finish_reason": "stop"}],
                      "usage": {"total_tokens": 10}}, request=request)

    pipeline = DomainPipeline(client=httpx.Client(transport=httpx.MockTransport(handler)),
                              api_key="k", call_budget=9, engine=engine)
    pipeline.explore("高等数学", mode="direct")
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT prompt_template FROM qed_llm_calls ORDER BY id")).fetchall()
    assert [r[0] for r in rows] == [
        "domain-explore/domain@v3", "domain-explore/courses@v6", "domain-explore/path@v5",
    ]
