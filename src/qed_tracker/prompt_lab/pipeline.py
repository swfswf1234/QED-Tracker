"""prompt_lab 管线（QED-043 · v3 三步管线）：领域知识探索编排器。

步骤：domain（领域校验与探索）→ courses（核心课程+简述）→ path（学习顺序+层级）。
每步独立模板（templates.py 注册表）+ ExploreAdvisorBase 结构化调用骨架
（严格 JSON + 坏 JSON 一次修复重试 + 预算 + 审计）；领域先验知识经 priors.py 注入；
跨步一致性校验在管线内完成；graph TD 由服务端按 tier 分组 + prerequisites 推导渲染。
模型只生成报告，不写库不改共享表。
"""

from __future__ import annotations

import time
from typing import Any

from qed_tracker.prompt_lab import templates as templates_mod
from qed_tracker.prompt_lab.priors import get_prior_for_step
from qed_tracker.prompt_lab.templates import _DEFAULT_SCOPE
from qed_tracker.providers.explore_advisor import ExploreAdvisorBase, _read_reference


class PipelineError(RuntimeError):
    """管线失败（LLM/校验/跨步一致性）；code 面向 run.error。"""

    def __init__(self, message: str, *, code: str = "LLM_UNAVAILABLE"):
        super().__init__(message)
        self.code = code


class NameConfirmationRequired(PipelineError):
    """领域名称需要人工确认（P12：正式流程进入待确认态，前端弹窗后继续）。"""

    def __init__(self, name_check: dict[str, Any]):
        super().__init__("领域名称需要人工确认", code="CONFIRMATION_REQUIRED")
        self.name_check = name_check


def _cross_check(step_template, value, context):
    """模板 validate + 跨步一致性校验（管线内闭包，失败走一次修复重试）。"""
    result = step_template.validate(value)
    _apply_cross(step_template.step, context, result)
    return result


def _apply_cross(step: str, context: dict[str, Any], value: Any) -> None:
    if step == "courses":
        track_names = context.get("track_names")
        if track_names is None:
            return
        for course in value["courses"]:
            if course["track"] and course["track"] not in track_names:
                raise ValueError(
                    f"{course['slug']}.track 不在 classic_tracks 内：{course['track']}"
                )
    elif step == "path":
        slugs = context.get("course_slugs", set())
        result_slugs = {a["slug"] for a in value["assignments"]}
        if result_slugs != slugs:
            raise ValueError("path.assignments 必须与课程清单完全一致（不得新增/遗漏）")


class DomainPipeline(ExploreAdvisorBase):
    """领域知识探索：domain → courses → path 三步管线。"""

    contract_version = "prompt-optimize-v3"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.step_calls: list[dict[str, Any]] = []
        """每步一次调用明细（step/template_id/duration_ms，含修复重试耗时）。"""

    def explore(
        self,
        domain_name: str,
        *,
        scope_hint: str = _DEFAULT_SCOPE,
        mode: str = "direct",
        ref_text: str = "",
        ref_doc_path: str = "",
        confirm_name_override: str = "",
        count_min: int = 10,
        count_max: int = 14,
    ) -> dict[str, Any]:
        """confirm_name_override 非空 = 人工已确认领域名（P12 弹窗流），跳过确认检查并以该名贯穿后续。

        count_min/count_max 为核心课程数量区间（探索轮裁决入参化，默认 10~14），仅约束 step2 文案。
        """
        domain_template = templates_mod.get_template("domain-explore", "domain")
        courses_template = templates_mod.get_template("domain-explore", "courses")
        path_template = templates_mod.get_template("domain-explore", "path")

        reference = _read_reference(mode, ref_text, ref_doc_path)

        # step1 领域探索与校验（名称需确认且未带人工确认时提前结束）
        domain = self._run(
            domain_template,
            {"domain_name": domain_name, "scope_hint": scope_hint,
             "user_input": reference,
             "prior_knowledge": get_prior_for_step(domain_name, "domain")},
            {},
        )
        final_name = (confirm_name_override or "").strip() or str(domain_name)
        name_check = domain["name_check"]
        suggested = (name_check.get("suggested_name") or "").strip()
        if not confirm_name_override and (
            not name_check.get("valid", False) or (suggested and suggested != domain_name)
        ):
            raise NameConfirmationRequired(name_check)

        # step2 核心课程与简述（主线全量含 summary；scope_hint 权威边界贯穿）
        tracks = domain["classic_tracks"]
        courses = self._run(
            courses_template,
            {"domain": {
                "name": final_name,
                "description": domain["description"],
                "level": domain["level"],
                "classic_tracks": tracks,
                "entry_requirements": domain["entry_requirements"],
            }, "count_range": {"min": count_min, "max": count_max},
             "scope_hint": scope_hint,
             "prior_knowledge": get_prior_for_step(final_name, "courses")},
            {"track_names": {t["name"] for t in tracks}},
        )
        course_slugs = {c["slug"] for c in courses["courses"]}

        # step3 学习顺序与层级（课程清单带 summary 作为前置判断依据）
        path = self._run(
            path_template,
            {"domain": {"name": final_name, "description": domain["description"],
                        "classic_tracks": tracks},
             "courses": [{"slug": c["slug"], "name": c["name"], "track": c["track"],
                          "summary": c["summary"]} for c in courses["courses"]],
             "scope_hint": scope_hint,
             "prior_knowledge": get_prior_for_step(final_name, "path")},
            {"course_slugs": course_slugs},
        )
        tiers = {a["slug"]: a["tier"] for a in path["assignments"]}
        pres = {a["slug"]: a["prerequisites"] for a in path["assignments"]}
        edges = [{"from": pre, "to": slug} for slug, pres_list in pres.items() for pre in pres_list]

        merged_courses = [
            {**course, "tier": tiers[course["slug"]], "prerequisites": pres[course["slug"]]}
            for course in courses["courses"]
        ]
        return {
            "domain": {
                "final_name": final_name,
                "description": domain["description"],
                "level": domain["level"],
                "classic_tracks": tracks,
                "entry_requirements": domain["entry_requirements"],
            },
            "courses": merged_courses,
            "path": {
                "notes": path["notes"],
                "edges": edges,
                "graph_td": templates_mod.render_graph_td(merged_courses, edges),
            },
        }

    def _run(self, template, payload, cross_context):
        """单步执行：模板组装 → _structured（校验 + 修复重试）→ 跨步校验并入；耗时入 step_calls。"""
        started = time.monotonic()
        try:
            value = self._structured(
                template.messages(payload),
                lambda v: _cross_check(template, v, cross_context),
                template_id=template.template_id,
            )
        except Exception as exc:  # noqa: BLE001 - 管线统一包装
            if isinstance(exc, PipelineError):
                raise
            raise PipelineError(f"领域探索步骤 {template.step} 失败：{exc}") from exc
        self.step_calls.append({
            "step": template.step,
            "template_id": template.template_id,
            "duration_ms": int((time.monotonic() - started) * 1000),
        })
        return value
