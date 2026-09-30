"""书级 LLM 顾问（QED-050）：检索词变体与候选确认。

模型只输出结构化结果（检索词变体 / 确认结论），不写资源事实、不自动下载；
宁缺勿滥——不确定的候选由编排层跳过不落库。`propose_queries`
（book-query/variants@v1，硬编码检索词耗尽后的书级兜底变体，≤N 条）与 `confirm`
（book-confirm/assess@v1，一批候选一次调用，verdict ∈ {confirmed, uncertain}）。
模型调用经 llm_client.py 兼容层（QED-037）：local 直连 dashscope qwen /
qed-engine 经 8900 网关 /llm/text；本类对外 API 不变。
QED-072 W-8：旧 `assess`（book-eval/assess@v1，0~100 评分）在 QED-050 两值裁决后
src 内零调用者，已作为死码删除；在用两条 prompt 的文案与输出契约迁入注册表
`prompt_lab/advisor_templates.py`，本类只组装 payload 并保留调用留痕。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any, TypeVar

import httpx

from qed_tracker.llm_client import LlmClient, LlmClientError
from qed_tracker.models import BookConfirmation, BookExpectation, Candidate
from qed_tracker.prompt_lab.templates import get_template

T = TypeVar("T")


class BailianBookAdvisor:
    contract_version = "book-eval-v1"

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

    def propose_queries(self, book: BookExpectation, *, variants: int = 3) -> list[str]:
        """书级兜底检索词变体（QED-050 阶段1）：全部渠道 × 硬编码 query 耗尽后调一次。

        输出 ≤variants 条检索词（book-query/variants@v1，写 qed_llm_calls 审计）；
        只生成检索计划，不执行下载（AGENTS.md 约束）。LLM 不可用/预算耗尽 → 异常上抛，
        由编排层转人工指引，不重试。
        """
        if variants < 1:
            raise ValueError("检索词变体数量必须 ≥ 1")
        payload = {
            "book": {
                "title": book.title,
                "original_title": book.original_title,
                "part": book.part,
                "authors": list(book.authors),
                "language": book.language,
                "publisher": book.publisher,
                "edition": book.edition,
                "year": book.year,
            },
            "variants": variants,
        }
        template = get_template("book-query", "variants")
        return self._structured(
            template.messages(payload), template.validator(payload), template_id=template.template_id
        )

    def confirm(self, book: BookExpectation, candidates: list[Candidate]) -> list[BookConfirmation]:
        """书级候选确认（QED-050 阶段2）：一批候选一次调用，逐条 verdict。

        verdict ∈ {confirmed, uncertain}：confirmed → 编排层自动进入下载；uncertain →
        qt_sources 留痕换下一候选。只生成可审阅结论，不写资源事实、不下载（AGENTS.md
        约束）。调用失败/预算耗尽由编排层按 uncertain 降级处理。
        """
        payload = {
            "expected": {
                "title": book.title,
                "original_title": book.original_title,
                "part": book.part,
                "authors": list(book.authors),
                "language": book.language,
                "publisher": book.publisher,
                "edition": book.edition,
                "year": book.year,
            },
            "candidates": [
                {
                    "provider_id": item.provider_id,
                    "provider": item.provider,
                    "title": item.title,
                    "authors": list(item.authors),
                    "language": item.language,
                    "publisher": item.publisher,
                    "year": item.year,
                    "edition": item.edition,
                    "description": item.description,
                }
                for item in candidates
            ],
        }
        template = get_template("book-confirm", "assess")
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
            raise ValueError("已达到教材评估模型调用预算")
        self.calls += 1
        try:
            content = self.llm_client.complete(messages, prompt_template=template_id)
        except LlmClientError as exc:
            raise ValueError(str(exc)) from exc
        self.usages.append(self.llm_client.last_usage)
        self.response_hashes.append(hashlib.sha256(content.encode("utf-8")).hexdigest())
        return content
