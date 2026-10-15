"""通过百炼文本模型生成论文检索计划并评估 arXiv 候选。

模型调用经 llm_client.py 兼容层（QED-037）：local 直连 dashscope qwen / qed-engine 经
8900 网关 /llm/text；本类对外 API 不变。

两条 prompt 文案与校验器已迁入 `prompt_lab/advisor_templates.py`（QED-074 W-2 迁入；
`paper-plan/plan@v2` 于 QED-068-2 S3 在册升代，`paper-plan/assess@v1` 不升代），本类只组装
payload 并经 `get_template` 取用。plan 响应在校验前经 `_clean_plan_value` 确定性清洗
（去引号/折叠空白/单条 ≤200 字符/组内大小写不敏感去重；结构问题不静默修复，仍按契约失败）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict
from typing import Any, TypeVar

import httpx

from qed_tracker.llm_client import LlmClient, LlmClientError
from qed_tracker.llm_json import loads_model_json
from qed_tracker.models import Candidate, PaperAssessment, PaperProfile, PaperSearch
from qed_tracker.prompt_lab.templates import get_template

T = TypeVar("T")

TERM_MAX_CHARS = 200
"""单条检索词硬顶（QED-068-2 清洗规则：超长截断，不整条丢弃）。"""


class BailianError(RuntimeError):
    pass


def _clean_plan_value(value: object) -> object:
    """检索计划确定性清洗（QED-068-2）：只规范化 term 形状，不改组数、不丢整组。

    去外围引号 → 折叠空白 → 截断 200 字符 → 组内大小写不敏感去重（保留首个清洗形态）。
    清洗后空组 / 超 4 组 / 越界分类一律交给校验器按契约失败（repair→报错），不在此静默修复。
    """
    if not isinstance(value, dict) or not isinstance(value.get("searches"), list):
        return value
    searches: list[Any] = []
    for search in value["searches"]:
        if not isinstance(search, dict) or not isinstance(search.get("terms"), list):
            searches.append(search)
            continue
        cleaned: list[Any] = []
        seen: set[str] = set()
        for term in search["terms"]:
            if not isinstance(term, str):
                cleaned.append(term)
                continue
            text = " ".join(term.strip().strip("\"'").split())[:TERM_MAX_CHARS]
            key = text.lower()
            if not text or key in seen:
                continue
            seen.add(key)
            cleaned.append(text)
        searches.append({**search, "terms": cleaned})
    return {**value, "searches": searches}


class BailianPaperAdvisor:
    contract_version = "paper-selection-v1"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "qwen-plus",
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        timeout: float = 60.0,
        call_budget: int = 6,
        max_tokens: int = 4096,
        client: httpx.Client | None = None,
        api_select: str = "local",
        gateway_url: str = "http://127.0.0.1:8900",
        engine=None,
    ):
        self.llm_client = LlmClient(
            api_select=api_select,
            api_key=api_key,
            model=model,
            base_url=base_url,
            gateway_url=gateway_url,
            timeout=timeout,
            call_budget=call_budget,
            max_tokens=max_tokens,
            client=client,
            engine=engine,
        )
        self.model_name = model
        self.call_budget = max(1, call_budget)
        self.calls = 0
        self.usages: list[dict[str, Any]] = []
        self.response_hashes: list[str] = []

    def close(self) -> None:
        self.llm_client.close()

    def metadata(self) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "contract_version": self.contract_version,
            "calls": self.calls,
            "usage": self.usages,
            "response_sha256": self.response_hashes,
        }

    def plan(self, profile: PaperProfile, goal: str, allowed_categories: tuple[str, ...]) -> list[PaperSearch]:
        payload = {
            "profile": asdict(profile),
            "temporary_goal": goal,
            "allowed_categories": allowed_categories,
            "limits": {"searches": 4, "terms_per_search": 4},
        }
        template = get_template("paper-plan", "plan")
        validator = template.validator(payload)
        return self._structured(
            template.messages(payload),
            lambda value: validator(_clean_plan_value(value)),
            template_id=template.template_id,
        )

    def assess(self, profile: PaperProfile, goal: str, candidates: list[Candidate]) -> list[PaperAssessment]:
        assessments: list[PaperAssessment] = []
        for offset in range(0, len(candidates), 10):
            batch = candidates[offset : offset + 10]
            assessments.extend(self._assess_batch(profile, goal, batch))
        return assessments

    def _assess_batch(self, profile: PaperProfile, goal: str, candidates: list[Candidate]) -> list[PaperAssessment]:
        candidate_payload = [
            {
                "arxiv_id": item.identifiers.get("arxiv", item.provider_id),
                "title": item.title,
                "authors": item.authors,
                "subjects": item.subjects,
                "published_at": item.published_at,
                "abstract": item.abstract[:4000],
            }
            for item in candidates
        ]
        payload = {"profile": asdict(profile), "temporary_goal": goal, "candidates": candidate_payload}
        template = get_template("paper-plan", "assess")
        return self._structured(
            template.messages(payload), template.validator(payload), template_id=template.template_id
        )

    def _structured(self, messages: list[dict[str, str]], validate: Callable[[object], T], *, template_id: str) -> T:
        # 形态容错在契约校验之前（2026-10-07 W5 取证）：围栏/前后散文不烧 repair 长调用
        content = self._complete(messages, template_id=template_id)
        try:
            return validate(loads_model_json(content))
        except (json.JSONDecodeError, ValueError, TypeError) as first_error:
            repair = [
                {"role": "system", "content": "修复给定响应，使其成为符合原契约的严格 JSON。只输出 JSON。"},
                {"role": "user", "content": f"原契约：{messages[-1]['content'][:6000]}\n待修复响应：{content[:8000]}"},
            ]
            repaired = self._complete(repair, template_id=template_id)
            try:
                return validate(loads_model_json(repaired))
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                raise BailianError(f"百炼结构化响应无效：{exc}") from first_error

    def _complete(self, messages: list[dict[str, str]], *, template_id: str) -> str:
        if not self.llm_client.is_gateway and not self.llm_client.configured:
            raise BailianError("未配置 API_KEY（可在自身 .env 或根 .env 提供）")
        if self.calls >= self.call_budget:
            raise BailianError("已达到论文推荐模型调用预算")
        self.calls += 1
        try:
            content = self.llm_client.complete(messages, prompt_template=template_id)
        except LlmClientError as exc:
            raise BailianError(str(exc)) from exc
        self.usages.append(self.llm_client.last_usage)
        self.response_hashes.append(hashlib.sha256(content.encode("utf-8")).hexdigest())
        return content
