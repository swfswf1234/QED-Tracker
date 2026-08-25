"""模型调用兼容层（QED-037 / REQ-043）：local 直连 / qed-engine 经 8900 网关。

模式（`QED_API_SELECT`，本子项目只以 qwen 提供 API）：

- `local` / `api`：**direct** —— 用自身 `API_KEY` 直连 dashscope 文字模型
  （OpenAI 兼容 `/chat/completions`），不依赖 8900 在线（独立性铁律）。
- `qed-engine`：**gateway** —— HTTP 调 8900 `POST /api/v1/llm/text`，不接触密钥。

direct 成功后写根仓库 `qed_llm_calls` 调用记录（`service=qed_tracker`、`mode=api`、
`provider=qwen`、`endpoint=text`），DB 不可达时降级记日志不抛；gateway 模式由网关统一
写表，本层不重复写。表结构契约以根仓库 llm-gateway-and-model-management.md 为准。

业务调用方（bailian.py / book_advisor.py / main_line/advisor.py）统一经本层调用，
对外 API 不变。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx
from sqlalchemy import Engine, text

from qed_tracker.database import utc_now

logger = logging.getLogger(__name__)

_DASH_SCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_DEFAULT_GATEWAY_URL = "http://127.0.0.1:8900"
_CALL_LOG_COLUMNS = (
    "service, mode, provider, model, endpoint, prompt_template, prompt, response,"
    " duration_ms, status, error, created_at"
)


class LlmClientError(RuntimeError):
    """模型调用失败（缺密钥 / 网络 / HTTP / 格式 / 预算），消息面向用户可读。"""


class LlmClient:
    """统一文字模型调用入口；`api_select` 决定 direct / gateway 路由。"""

    def __init__(
        self,
        *,
        api_select: str = "local",
        api_key: str = "",
        model: str = "qwen-plus",
        base_url: str = _DASH_SCOPE_BASE_URL,
        gateway_url: str = _DEFAULT_GATEWAY_URL,
        timeout: float = 60.0,
        call_budget: int = 6,
        max_tokens: int = 4096,
        client: httpx.Client | None = None,
        engine: Engine | None = None,
    ):
        self.api_select = api_select
        self.api_key = api_key
        self.model_name = model
        self.base_url = base_url.rstrip("/")
        self.gateway_url = gateway_url.rstrip("/")
        self.call_budget = max(1, call_budget)
        self.max_tokens = max_tokens
        self.calls = 0
        self.last_usage: dict[str, Any] = {}
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=timeout)
        self.engine = engine  # direct 模式调用记录写 qed_llm_calls 用（None=不落库）

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @property
    def is_gateway(self) -> bool:
        return self.api_select == "qed-engine"

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def complete(self, messages: list[dict[str, str]], *, prompt_template: str = "") -> str:
        """统一调用：返回模型回答文本。messages 为 OpenAI 风格 [{role, content}]。"""
        if self.calls >= self.call_budget:
            raise LlmClientError("已达到模型调用预算")
        self.calls += 1
        if self.is_gateway:
            return self._gateway_complete(messages, prompt_template)
        return self._direct_complete(messages, prompt_template)

    # ---------------- direct（dashscope 直连） ----------------

    def _direct_complete(self, messages: list[dict[str, str]], prompt_template: str) -> str:
        if not self.api_key:
            raise LlmClientError("未配置 API_KEY（可在自身 .env 或根 .env 提供）")
        started = time.monotonic()
        prompt = json.dumps(messages, ensure_ascii=False)
        content = ""
        status, error = "success", ""
        try:
            response = self.client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model_name,
                    "messages": messages,
                    "temperature": 0,
                    "max_tokens": self.max_tokens,
                },
            )
            response.raise_for_status()
            body = response.json()
            choice = body["choices"][0]
            content = choice["message"]["content"]
            if choice.get("finish_reason") != "stop" or not isinstance(content, str):
                raise LlmClientError("模型响应未完整结束")
            self.last_usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        except LlmClientError as exc:
            status, error = "error", str(exc)
            raise
        except httpx.TimeoutException as exc:
            status, error = "error", "模型网络请求失败"
            raise LlmClientError(error) from exc
        except httpx.NetworkError as exc:
            status, error = "error", "模型网络请求失败"
            raise LlmClientError(error) from exc
        except httpx.HTTPStatusError as exc:
            status, error = "error", f"模型返回 HTTP {exc.response.status_code}"
            raise LlmClientError(error) from exc
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            status, error = "error", "模型响应格式无效"
            raise LlmClientError(error) from exc
        finally:
            self._record_call(prompt, content, started, status=status, error=error, prompt_template=prompt_template)
        return content

    # ---------------- gateway（8900 /api/v1/llm/text） ----------------

    def _gateway_complete(self, messages: list[dict[str, str]], prompt_template: str) -> str:
        system = next((m["content"] for m in messages if m.get("role") == "system"), None)
        prompt = messages[-1]["content"] if messages else ""
        payload: dict[str, Any] = {"prompt": prompt, "max_tokens": self.max_tokens}
        if system:
            payload["system"] = system
        if prompt_template:
            payload["prompt_template"] = prompt_template
        try:
            response = self.client.post(
                f"{self.gateway_url}/api/v1/llm/text",
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
            if body.get("success") is False:
                # 网关失败语义（ARCH-016）：reply="" + success=false + error —— 抛错而非空串穿透
                raise LlmClientError(f"网关调用失败：{body.get('error') or '未知错误'}")
            reply = body.get("reply")
            if not isinstance(reply, str):
                raise LlmClientError("网关响应格式无效")
            self.last_usage = {}
            return reply
        except LlmClientError:
            raise
        except httpx.TimeoutException as exc:
            raise LlmClientError("网关请求失败") from exc
        except httpx.NetworkError as exc:
            raise LlmClientError("网关请求失败") from exc
        except httpx.HTTPStatusError as exc:
            raise LlmClientError(f"网关返回 HTTP {exc.response.status_code}") from exc
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise LlmClientError("网关响应格式无效") from exc

    # ---------------- qed_llm_calls 调用记录（仅 direct） ----------------

    def _record_call(
        self,
        prompt: str,
        response_text: str,
        started: float,
        *,
        status: str,
        error: str,
        prompt_template: str = "",
    ) -> None:
        if self.engine is None:
            return
        params = {
            "service": "qed_tracker",
            "mode": "api",
            "provider": "qwen",
            "model": self.model_name,
            "endpoint": "text",
            "prompt_template": prompt_template,
            "prompt": prompt,
            "response": response_text,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "status": status,
            "error": error,
            "created_at": utc_now(),
        }
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    text(f"INSERT INTO qed_llm_calls ({_CALL_LOG_COLUMNS}) VALUES"
                         " (:service, :mode, :provider, :model, :endpoint, :prompt_template, :prompt,"
                         " :response, :duration_ms, :status, :error, :created_at)"),
                    params,
                )
        except Exception as exc:  # noqa: BLE001 - DB 不可达降级，不阻塞模型调用
            logger.warning("qed_llm_calls 写入降级（数据库不可达）：%s", type(exc).__name__)
