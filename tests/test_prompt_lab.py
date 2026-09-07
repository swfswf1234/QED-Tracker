"""prompt_lab 模板注册表与领域管线契约（QED-043 · 领域管线 v8 两步，2026-09-03 用户裁决）。

守护面：
- 注册表：domain@v4 / courses@v8 两步齐全（path@v5 已并入 courses@v8）；
- 学科中立：templates.py 禁止学科绑定词（领域专属知识归 priors.py）；
- priors：精确域名匹配，未命中不影响其它领域；
- courses@v8 validate：数量兜底/stage 枚举/prerequisites 引用/自环/无环/禁拆学期/summary 60~200 等规则；
- graph TD 渲染：stage 分组 + 前置边（由 prerequisites 服务端推导）；
- 管线：两步顺序调用、坏 JSON 一次修复、跨步 track 校验、名称确认提前结束/人工确认放行、报告聚合。

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
from qed_tracker.prompt_lab.templates import STAGES, get_template, render_graph_td

# ---------------- 注册表 ----------------


def test_registry_contains_two_steps_with_ids() -> None:
    steps = {(t["task"], t["step"]): t["id"] for t in templates_mod.list_templates()}
    assert set(k for k in steps if k[0] == "domain-explore") == {
        ("domain-explore", "domain"),
        ("domain-explore", "courses"),
    }
    assert steps[("domain-explore", "domain")] == "domain-explore/domain@v4"
    assert steps[("domain-explore", "courses")] == "domain-explore/courses@v8"


def test_unknown_template_raises() -> None:
    with pytest.raises(KeyError):
        get_template("domain-explore", "describe")
    with pytest.raises(KeyError):
        get_template("domain-explore", "scope")
    with pytest.raises(KeyError):
        get_template("domain-explore", "path")


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


def test_priors_tracks_hint_aligns_tracks() -> None:
    """知识文档定稿后主线提示对齐（三条主干 + 几何与拓扑为分支，用户裁决 2026-09-02）。"""
    hint = get_prior("高等数学")["tracks_hint"]
    for track_name in ("分析学", "代数学", "概率与统计"):
        assert track_name in hint
    assert "几何与拓扑" in hint
    assert "branch" in hint


def test_priors_naming_convention_resolves_domain_aliases() -> None:
    """「数学」「数学（高等数学）」等称呼应能归一到规范名「高等数学」。"""
    naming = get_prior("高等数学")["naming_convention"]
    assert "高等数学" in naming
    assert "数学（高等数学）" in naming


def test_get_prior_for_step_trims_by_step() -> None:
    """分步裁剪注入表：domain=4 键 / courses=全量（path 步已并入 courses@v8）。"""
    assert set(PRIOR_KEYS_BY_STEP["domain"]) == {
        "naming_convention", "tracks_hint", "anchor_courses", "level_default",
    }
    assert "path" not in PRIOR_KEYS_BY_STEP
    full = get_prior("高等数学")
    assert set(get_prior_for_step("高等数学", "domain")) == set(PRIOR_KEYS_BY_STEP["domain"])
    assert set(get_prior_for_step("高等数学", "courses")) == set(full)
    assert get_prior_for_step("物理学", "domain") == {}


# ---------------- step1 domain 校验 ----------------

_VALID_NAME_CHECK = {"valid": True, "reason": "指代完整的课程体系，合格", "suggested_name": ""}


def test_domain_validate_rules() -> None:
    domain_t = get_template("domain-explore", "domain")
    ok = {
        "name_check": dict(_VALID_NAME_CHECK),
        "final_name": "高等数学",
        "description": "大学阶段的数学核心课程体系，覆盖分析、代数等主干直至硕士主课。",
        "level": "本科",
        "classic_tracks": [{"name": "分析", "summary": "极限与分析方向", "kind": "main"}, {"name": "代数", "summary": "代数结构方向", "kind": "main"}],
        "entry_requirements": "微积分基础",
        "prior_knowledge": "已探明基础课程与教材偏好",
    }
    assert domain_t.validate(ok) == ok
    # prior_knowledge 可省略（默认空字符串）
    ok_no_prior = {k: v for k, v in ok.items() if k != "prior_knowledge"}
    assert domain_t.validate(ok_no_prior)["prior_knowledge"] == ""
    # 描述超长（>200）
    with pytest.raises(ValueError):
        domain_t.validate({**ok, "description": "长" * 201})
    # entry_requirements 超长（>80，2026-09-02 用户裁定）
    with pytest.raises(ValueError):
        domain_t.validate({**ok, "entry_requirements": "长" * 81})
    # prior_knowledge 超长（>500）
    with pytest.raises(ValueError):
        domain_t.validate({**ok, "prior_knowledge": "长" * 501})
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


def test_domain_template_v4_contract_notes() -> None:
    """v4 裁决六项文案要素：名称大类/括号可选/description 说明白/level 本科/entry ≤80/prior_knowledge 整理+学习建议。"""
    domain_t = get_template("domain-explore", "domain")
    user_text = domain_t.build_user(
        {"domain_name": "示例领域", "scope_hint": _SCOPE_HINT, "user_input": "", "prior_knowledge": {}}
    )
    assert "学科大类" in user_text  # 名称应为学科大类而非专业划分
    assert "括号" in user_text and "最优解不使用括号" in user_text  # 括号限定可选
    assert "说明白" in user_text  # description 目标是说明白
    assert "套话" in user_text  # 禁空泛套话
    assert "80" in user_text  # entry_requirements ≤80 字
    assert "学习建议" in user_text and "学习路径" in user_text  # prior_knowledge 含学习建议
    assert "中文" in (domain_t.system + user_text)  # 显式中文输出（system 段声明）


# ---------------- step2 courses@v8 校验（并入原 path 规则） ----------------

_SUMMARY_OK = (
    "这门课程系统讲授该领域的核心概念、基本方法与典型应用，训练严谨的分析与建模能力，"
    "帮助学生建立完整的知识框架与进一步学习后续课程所必需的基础，是本方向的重要基石。"
)


def _course(course_id: str, name: str, **overrides) -> dict:
    base = {
        "course_id": course_id, "name": name, "aliases": [],
        "track": "", "summary": _SUMMARY_OK,
        "university_basis": ["清华大学 对应课程"],
        "stage": "基础", "prerequisites": [],
    }
    base.update(overrides)
    return base


def _ok_rest() -> list[dict]:
    return [_course("course_b", "课程乙"), _course("course_c", "课程丙"), _course("course_d", "课程丁")]


def test_courses_validate_rules() -> None:
    courses_t = get_template("domain-explore", "courses")
    ok = {"courses": [_course("foundations", "基础课程"), _course("core_a", "主干课程甲"),
                      _course("core_b", "主干课程乙"), _course("branch_a", "分支课程")], "notes": ""}
    assert courses_t.validate(ok) == ok
    # 数量推荐 3~16 非强制（D4 裁决）：2 门合法
    refined = courses_t.validate({"courses": ok["courses"][:2]})
    assert len(refined["courses"]) == 2
    # 数量兜底下限（0 门非法）
    with pytest.raises(ValueError):
        courses_t.validate({"courses": []})
    # 数量兜底上限（>24 非法）
    with pytest.raises(ValueError):
        courses_t.validate({"courses": [_course(f"c{i}", f"课程{i}") for i in range(25)]})
    # 拆学期命名（数字结尾）
    with pytest.raises(ValueError):
        courses_t.validate({"courses": [_course("a", "基础课程1"), *_ok_rest()]})
    # 拆学期命名（括号序号）
    with pytest.raises(ValueError):
        courses_t.validate({"courses": [_course("a", "基础课程（一）"), *_ok_rest()]})
    # summary 过短（<60，D2 裁决：prompt 与 validate 同界 60~200）
    with pytest.raises(ValueError):
        courses_t.validate({"courses": [_course("a", "课程", summary="太短"), *_ok_rest()]})
    # summary 超长（>200）
    with pytest.raises(ValueError):
        courses_t.validate({"courses": [_course("a", "课程", summary="长" * 201), *_ok_rest()]})
    # university_basis 可为空数组或缺省（V1 放宽：确无对应依据时不强制编造）
    ok_empty = courses_t.validate({"courses": [_course("crs", "课程", university_basis=[]), *_ok_rest()]})
    assert ok_empty["courses"][0]["university_basis"] == []
    missing = _course("crs2", "课程")
    missing.pop("university_basis")
    courses_t.validate({"courses": [missing, *_ok_rest()]})
    # 连字符 course_id
    with pytest.raises(ValueError):
        courses_t.validate({"courses": [_course("algorithms-and-ds", "课程"), *_ok_rest()]})
    # notes 可选（缺省为空字符串），超长（>500）非法
    with_notes = courses_t.validate({**ok, "notes": "整体编排说明"})
    assert with_notes["notes"] == "整体编排说明"
    assert courses_t.validate(ok)["notes"] == ""
    with pytest.raises(ValueError):
        courses_t.validate({**ok, "notes": "长" * 501})


def test_courses_validate_stage_and_prerequisites_rules() -> None:
    """path@v5 规则并入：stage 枚举 + prerequisites 引用/自环/无环。"""
    courses_t = get_template("domain-explore", "courses")
    ok = {"courses": [
        _course("foundations", "基础课程", stage="基础", prerequisites=[]),
        _course("core_a", "主干课程甲", stage="主干", prerequisites=["foundations"]),
        _course("branch_a", "分支课程", stage="分支", prerequisites=["core_a"]),
    ], "notes": ""}
    assert courses_t.validate(ok) == ok
    # stage 越界
    with pytest.raises(ValueError):
        courses_t.validate({"courses": [_course("a", "课程", stage="选修"), *_ok_rest()]})
    # 自环前置
    with pytest.raises(ValueError):
        courses_t.validate({"courses": [_course("a", "课程", prerequisites=["a"]), *_ok_rest()]})
    # 前置成环（a↔b）
    cyclic = {"courses": [
        _course("a", "课程甲", prerequisites=["b"]),
        _course("b", "课程乙", prerequisites=["a"]),
    ]}
    with pytest.raises(ValueError):
        courses_t.validate(cyclic)
    # 前置引用不在本批
    with pytest.raises(ValueError):
        courses_t.validate({"courses": [_course("a", "课程", prerequisites=["ghost"]), *_ok_rest()]})


def test_courses_stage_enum_follows_ordered_stages() -> None:
    assert STAGES == ("基础", "主干", "分支", "前沿")


def test_courses_template_v8_contract_notes() -> None:
    """v8 裁决文案要素：数量推荐构成导向/命名先验优先/stage 四档/prerequisites 依赖判断/notes。"""
    courses_t = get_template("domain-explore", "courses")
    user_text = courses_t.build_user({"domain": {}, "prior_knowledge": {}})
    assert "3~16" in user_text  # 推荐数量（非强制）
    assert "核心主干" in user_text  # 构成导向：基础+核心主干优先
    assert "分支" in user_text and "前沿" in user_text  # 关键分支与重要前沿纳入
    assert "命名约定" in user_text and "优先" in user_text  # 先验命名约定优先于默认基准
    assert "入门基石" in user_text and "论文驱动" in user_text  # stage 四档语义
    assert "知识依赖" in user_text  # prerequisites 基于 summary 知识依赖判断
    assert "自环" in user_text  # 禁自环/循环
    assert "连字符" in user_text and "_" in user_text  # course_id 规则（真实评估中 LLM 曾输出连字符 slug）
    assert "notes" in user_text  # 整体编排说明
    assert "中文" in (courses_t.system + user_text)  # 显式中文输出


# ---------------- graph TD 渲染 ----------------


def test_render_graph_td_groups_by_stage_with_edges() -> None:
    courses = [
        {"course_id": "foundations", "name": "基础课程", "stage": "基础"},
        {"course_id": "core_a", "name": "主干课程甲", "stage": "主干"},
        {"course_id": "branch_a", "name": "分支课程", "stage": "分支"},
    ]
    text_out = render_graph_td(courses, [{"from": "foundations", "to": "core_a"}])
    assert text_out.startswith("graph TD")
    assert "foundations[基础课程]" in text_out
    assert "%% 基础" in text_out and "%% 主干" in text_out
    assert "foundations --> core_a" in text_out


# ---------------- 管线 fixtures ----------------

_SCOPE_HINT = "大学往上的知识内容（本科-硕士阶段）"
_DOMAIN_RESP = {
    "name_check": dict(_VALID_NAME_CHECK),
    "final_name": "高等数学",
    "description": "大学阶段的数学核心课程体系。",
    "level": "本科",
    "classic_tracks": [{"name": "分析", "summary": "极限与分析", "kind": "main"}, {"name": "代数", "summary": "代数结构", "kind": "main"}],
    "entry_requirements": "微积分基础",
}
_COURSES_RESP = {"notes": "先基础后主干，拓扑为分支拓展", "courses": [
    _course("math_analysis", "数学分析", aliases=["微积分"], track="分析", stage="基础", prerequisites=[]),
    _course("algebra", "高等代数", aliases=["线性代数"], track="代数", stage="基础", prerequisites=[]),
    _course("topology", "点集拓扑", track="分析", stage="分支", prerequisites=["math_analysis"]),
    _course("real_analysis", "实分析", track="分析", stage="主干", prerequisites=["math_analysis", "topology"]),
]}


def _pipeline(responses: list[str], **overrides) -> DomainPipeline:
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": queue.pop(0)}, "finish_reason": "stop"}],
                                         "usage": {"total_tokens": 10}}, request=request)

    defaults = dict(api_key="k", call_budget=9)
    defaults.update(overrides)
    return DomainPipeline(client=httpx.Client(transport=httpx.MockTransport(handler)), **defaults)


# ---------------- 管线行为 ----------------


def test_domain_pipeline_runs_two_steps_and_aggregates_report() -> None:
    pipeline = _pipeline([json.dumps(_DOMAIN_RESP), json.dumps(_COURSES_RESP)])
    report = pipeline.explore("高等数学", scope_hint=_SCOPE_HINT, mode="direct")
    assert report["domain"]["final_name"] == "高等数学"
    assert report["domain"]["level"] == "本科"
    assert report["domain"]["stages"] == ["基础", "主干", "分支", "前沿"]
    assert len(report["courses"]) == 4
    merged = {c["course_id"]: c for c in report["courses"]}
    assert merged["math_analysis"]["stage"] == "基础"
    assert merged["math_analysis"]["prerequisites"] == []
    assert merged["real_analysis"]["prerequisites"] == ["math_analysis", "topology"]
    assert merged["real_analysis"]["track"] == "分析"
    assert report["path"]["notes"] == "先基础后主干，拓扑为分支拓展"
    assert {"from": "math_analysis", "to": "real_analysis"} in report["path"]["edges"]
    assert {"from": "topology", "to": "real_analysis"} in report["path"]["edges"]
    assert report["path"]["graph_td"].startswith("graph TD")
    assert pipeline.calls == 2
    assert [c["step"] for c in pipeline.step_calls] == ["domain", "courses"]
    assert [c["template_id"] for c in pipeline.step_calls] == [
        "domain-explore/domain@v4", "domain-explore/courses@v8",
    ]


def test_pipeline_payload_carries_prior_and_scope() -> None:
    captured: list[dict] = []
    queue = [json.dumps(_DOMAIN_RESP), json.dumps(_COURSES_RESP)]

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": queue.pop(0)}, "finish_reason": "stop"}],
                                         "usage": {"total_tokens": 10}}, request=request)

    pipeline = DomainPipeline(client=httpx.Client(transport=httpx.MockTransport(handler)),
                              api_key="k", call_budget=9)
    pipeline.explore("高等数学", mode="direct")
    domain_user = captured[0]["messages"][1]["content"]
    courses_user = captured[1]["messages"][1]["content"]
    # step1 注入分步裁剪后的先验（domain 步不含教材偏好/顶峰提示）与默认范围
    assert "prior_knowledge" in domain_user
    assert "naming_convention" in domain_user
    assert "textbook_preference" not in domain_user
    assert _SCOPE_HINT in domain_user
    # step2 携带权威范围、主线全量对象（含 summary）与全量先验
    assert '"scope_hint"' in courses_user
    assert '"summary"' in courses_user
    assert '"capstone_hint"' in courses_user


def test_pipeline_repairs_bad_json_once_per_step() -> None:
    pipeline = _pipeline(["not-json", json.dumps(_DOMAIN_RESP), json.dumps(_COURSES_RESP)])
    report = pipeline.explore("高等数学", mode="direct")
    assert report["domain"]["final_name"] == "高等数学"
    assert pipeline.calls == 3


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
    pipeline = _pipeline([json.dumps(suggested_other), json.dumps(_COURSES_RESP)])
    report = pipeline.explore("高等数学", mode="direct", confirm_name_override="高等数学")
    assert report["domain"]["final_name"] == "高等数学"  # 用户拍板的名字
    assert len(report["courses"]) == 4
    assert pipeline.calls == 2


def test_pipeline_rejects_track_outside_classic_tracks() -> None:
    bad_courses = {"courses": [
        _course("math_analysis", "数学分析", track="不存在的线"),
        *_ok_rest(),
    ]}
    pipeline = _pipeline([json.dumps(_DOMAIN_RESP), json.dumps(bad_courses), json.dumps(bad_courses)])
    with pytest.raises(PipelineError):
        pipeline.explore("高等数学", mode="direct")


def test_pipeline_accepts_track_in_branch_directions() -> None:
    """分支方向（kind=branch）也可拥有课程（2026-09-02 用户裁决：几何与拓扑降分支后课程归属需要）。"""
    branch_tracks = {**_DOMAIN_RESP, "classic_tracks": [
        {"name": "分析", "summary": "极限与分析", "kind": "main"},
        {"name": "几何", "summary": "空间与形状", "kind": "branch"},
    ]}
    branch_courses = {"courses": [
        _course("math_analysis", "数学分析", track="分析"),
        _course("topology", "点集拓扑", track="几何"),
        _course("algebra", "高等代数", track=""),
        _course("real_analysis", "实分析", track="分析"),
    ]}
    pipeline = _pipeline([json.dumps(branch_tracks), json.dumps(branch_courses)])
    report = pipeline.explore("高等数学", mode="direct")
    merged = {c["course_id"]: c for c in report["courses"]}
    assert merged["topology"]["track"] == "几何"


def test_pipeline_rejects_cyclic_prerequisites() -> None:
    """prerequisites 成环由 courses@v8 validate 兜底（原 path 步规则并入）。"""
    cyclic = {"courses": [
        _course("a", "课程甲", prerequisites=["b"]),
        _course("b", "课程乙", prerequisites=["a"]),
        *_ok_rest(),
    ]}
    pipeline = _pipeline([json.dumps(_DOMAIN_RESP), json.dumps(cyclic), json.dumps(cyclic)])
    with pytest.raises(PipelineError):
        pipeline.explore("高等数学", mode="direct")


def test_pipeline_budget_exhaustion_raises() -> None:
    pipeline = _pipeline([json.dumps(_DOMAIN_RESP), json.dumps(_COURSES_RESP)], call_budget=1)
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
    queue = [json.dumps(_DOMAIN_RESP), json.dumps(_COURSES_RESP)]

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
        "domain-explore/domain@v4", "domain-explore/courses@v8",
    ]


def test_pipeline_defaults_to_extended_max_tokens() -> None:
    """合并后单次输出变长（D1 缓解）：DomainPipeline 默认 max_tokens 放宽到 16384。"""
    pipeline = _pipeline([], api_key="k")
    assert pipeline.llm_client.max_tokens == 16384
