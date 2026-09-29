"""主链路教材条目预填：LLM 生成版本/评价/建议（可审阅，不写资源事实）。

参照顶尖大学（MIT/清华等）课程设置作为提示词锚点；防「总评高」校准：
权威性等级只能取 高/中/低，必须给出区分度依据（名校指定/社区公认/小众），
且同课程多本候选对比评级（不能全部评高）。人工评审可覆盖（source=manual）。
模型调用经 llm_client.py 兼容层（QED-037）：local 直连 dashscope qwen / qed-engine 经
8900 网关 /llm/text；本类对外 API 不变。
QED-072 W-8：prompt 文案与输出契约（mainline-prefill/prefill@v1）迁入注册表
`prompt_lab/advisor_templates.py`，本类只组装 payload 并保留调用留痕。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, TypeVar

import httpx

from qed_tracker.llm_client import LlmClient, LlmClientError
from qed_tracker.prompt_lab.templates import get_template

T = TypeVar("T")


class MainLineAdvisor:
    contract_version = "mainline-prefill-v1"

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

    def close(self) -> None:
        self.llm_client.close()

    def metadata(self) -> dict[str, Any]:
        return {"model": self.model_name, "contract_version": self.contract_version, "calls": self.calls}

    def prefill(
        self,
        *,
        course: dict[str, Any],
        title: str,
        authors: list[str],
        language: str = "",
        edition: str = "",
    ) -> dict[str, Any]:
        """为教材条目预填 evaluation + advice（不写条目文件，由调用方落盘）。

        返回 {"evaluation": {"source": "llm", "text", "authority", "set_candidate"},
              "advice": {"download", "reason"}}
        """
        payload = {
            "course": course,
            "book": {"title": title, "authors": authors, "language": language, "edition": edition},
        }
        template = get_template("mainline-prefill", "prefill")
        return self._structured(
            template.messages(payload), template.validator(payload), template_id=template.template_id
        )

    def _structured(self, messages: list[dict[str, str]], validate: Callable[[object], T], *, template_id: str) -> T:
        content = self._complete(messages, template_id=template_id)
        try:
            return validate(json.loads(content))
        except (json.JSONDecodeError, ValueError, TypeError) as first_error:
            repair = [
                {"role": "system", "content": "修复给定响应，使其成为符合原契约的严格 JSON。只输出 JSON。"},
                {"role": "user", "content": f"原契约：{messages[-1]['content'][:6000]}\n待修复响应：{content[:8000]}"},
            ]
            repaired = self._complete(repair, template_id=template_id)
            try:
                return validate(json.loads(repaired))
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                raise ValueError(f"百炼结构化响应无效：{exc}") from first_error

    def _complete(self, messages: list[dict[str, str]], *, template_id: str) -> str:
        if not self.llm_client.is_gateway and not self.llm_client.configured:
            raise ValueError("未配置 API_KEY（可在自身 .env 或根 .env 提供）")
        if self.calls >= self.call_budget:
            raise ValueError("已达到教材预填模型调用预算")
        self.calls += 1
        try:
            return self.llm_client.complete(messages, prompt_template=template_id)
        except LlmClientError as exc:
            raise ValueError(str(exc)) from exc
