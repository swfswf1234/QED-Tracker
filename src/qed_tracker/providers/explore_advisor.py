"""探索 LLM advisor 基类与工具函数（供 prompt_lab 管线复用）。

提供：
- ExploreAdvisorBase：LLM 调用骨架（严格 JSON 校验 + 一次修复重试 + 预算控制）
- _read_reference：参考输入归一化（direct/text/doc 三模式）

模型调用经 llm_client.py 双模式；坏 JSON 一次修复重试；
预算按 run 隔离（handler 每 run 新建实例）。参考文本是不可信数据——
system 提示词强制防注入与严格 JSON 输出。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import httpx

from qed_tracker.llm_client import LlmClient, LlmClientError

T = TypeVar("T")

REF_TEXT_LIMIT = 8000  # 参考文本截断上限（L2 裁决），超出附 truncated 标记


class ExploreAdvisorError(RuntimeError):
    """探索模型调用失败；code 面向 run.error（LLM_UNAVAILABLE / INVALID_PARAMS / BUDGET_EXHAUSTED）。"""

    def __init__(self, message: str, *, code: str = "LLM_UNAVAILABLE"):
        super().__init__(message)
        self.code = code


def _read_reference(mode: str, ref_text: str, ref_doc_path: str) -> dict[str, Any]:
    """run.params → reference 输入段（三模式 + 截断标记）。"""
    if mode == "direct":
        return {"mode": mode, "text": "", "truncated": False}
    if mode == "text":
        if not (ref_text or "").strip():
            raise ExploreAdvisorError("mode=text 必须提供非空 ref_text", code="INVALID_PARAMS")
        text = ref_text[:REF_TEXT_LIMIT]
        return {"mode": mode, "text": text, "truncated": len(ref_text) > REF_TEXT_LIMIT}
    if mode == "doc":
        path = Path(ref_doc_path or "")
        if not str(ref_doc_path or "").strip() or not path.is_file():
            raise ExploreAdvisorError(f"ref_doc_path 不可读：{ref_doc_path}", code="INVALID_PARAMS")
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ExploreAdvisorError(f"探索文档无法以 UTF-8 解码：{path}", code="INVALID_PARAMS") from exc
        return {"mode": mode, "text": raw[:REF_TEXT_LIMIT], "truncated": len(raw) > REF_TEXT_LIMIT}
    raise ExploreAdvisorError(f"非法 mode：{mode}（仅 direct/text/doc）", code="INVALID_PARAMS")


class ExploreAdvisorBase:
    """共享骨架：LlmClient 组装、_structured 校验+一次修复重试、审计留存。"""

    contract_version = "explore-v1"
    template_id = ""  # prompt 模板编号（子类覆盖，如 "course-explore/tutorials@v1"）
    repair_note = "修复给定响应，使其成为符合原契约的严格 JSON。只输出 JSON。"

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
            api_select=api_select, api_key=api_key, model=model, base_url=base_url,
            gateway_url=gateway_url, timeout=timeout, call_budget=call_budget,
            max_tokens=max_tokens, client=client, engine=engine,
        )
        self.model_name = model
        self.call_budget = max(1, call_budget)
        self.calls = 0
        self.usages: list[dict[str, Any]] = []
        self.response_hashes: list[str] = []
        self.last_payload: dict[str, Any] = {}

    def close(self) -> None:
        self.llm_client.close()

    def metadata(self) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "contract_version": self.contract_version,
            "calls": self.calls,
            "usage": self.usages,
            "response_sha256": self.response_hashes,
            "last_payload": self.last_payload,
        }

    def _structured(self, messages: list[dict[str, str]], validate: Callable[[object], T], *,
                    template_id: str | None = None) -> T:
        call_id = self.template_id if template_id is None else template_id
        try:
            content = self._complete(messages, template_id=call_id)
        except LlmClientError as exc:
            raise ExploreAdvisorError(str(exc)) from exc
        try:
            return validate(json.loads(content))
        except (json.JSONDecodeError, ValueError, TypeError) as first_error:
            repair = [
                {"role": "system", "content": self.repair_note},
                {"role": "user", "content": f"原契约:{messages[-1]['content'][:6000]}\n待修复响应:{content[:8000]}"},
            ]
            try:
                repaired = self._complete(repair, template_id=call_id)
            except LlmClientError as exc:
                raise ExploreAdvisorError(str(exc)) from exc
            try:
                return validate(json.loads(repaired))
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                raise ExploreAdvisorError(f"探索结构化响应无效：{exc}") from first_error

    def _complete(self, messages: list[dict[str, str]], *, template_id: str | None = None) -> str:
        if self.calls >= self.call_budget:
            raise ExploreAdvisorError("已达到探索模型调用预算", code="BUDGET_EXHAUSTED")
        self.calls += 1
        call_template = self.template_id if template_id is None else template_id
        try:
            content = self.llm_client.complete(messages, prompt_template=call_template)
        except LlmClientError as exc:
            raise ExploreAdvisorError(str(exc)) from exc
        self.usages.append(self.llm_client.last_usage)
        self.response_hashes.append(hashlib.sha256(content.encode("utf-8")).hexdigest())
        return content
