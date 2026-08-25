"""llm_client.py 兼容层测试（QED-037/REQ-043）：direct / gateway 双模式 + 调用记录。

固定 fixture（httpx.MockTransport），不访问公网；qed_llm_calls 落库用 SQLite 注入 engine。
"""

from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import create_engine, text

from qed_tracker.llm_client import LlmClient, LlmClientError


def _dash_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "qwen-plus",
            "choices": [{"finish_reason": "stop", "message": {"content": content}}],
            "usage": {"total_tokens": 10},
        },
    )


def _direct_client(handler, **kw) -> LlmClient:
    return LlmClient(
        api_select="local",
        api_key="sk-1",
        model="qwen-plus",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        **kw,
    )


def test_direct_mode_calls_dashscope_with_key() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization")
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return _dash_response("hello")

    client = _direct_client(handler)
    assert client.complete([{"role": "user", "content": "hi"}]) == "hello"
    assert captured["auth"] == "Bearer sk-1"
    assert captured["path"].endswith("/chat/completions")
    assert captured["body"]["model"] == "qwen-plus"
    assert captured["body"]["messages"] == [{"role": "user", "content": "hi"}]
    client.close()


def test_api_select_api_also_uses_direct() -> None:
    called = []

    def handler(request: httpx.Request) -> httpx.Response:
        called.append(request.url.path)
        return _dash_response("ok")

    client = LlmClient(
        api_select="api", api_key="sk-1", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert client.complete([{"role": "user", "content": "hi"}]) == "ok"
    assert called[0].endswith("/chat/completions")


def test_gateway_mode_calls_8900_without_key() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization")
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"reply": "gw-reply", "call_id": "call-1"})

    client = LlmClient(
        api_select="qed-engine",
        api_key="",  # gateway 模式不接触密钥
        gateway_url="http://127.0.0.1:8900",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert (
        client.complete([{"role": "system", "content": "sys"}, {"role": "user", "content": "q"}])
        == "gw-reply"
    )
    assert captured["auth"] is None
    assert captured["url"] == "http://127.0.0.1:8900/api/v1/llm/text"
    assert captured["body"]["prompt"] == "q"
    assert captured["body"]["system"] == "sys"
    client.close()


def test_gateway_mode_works_without_api_key() -> None:
    client = LlmClient(
        api_select="qed-engine",
        api_key="",
        client=httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"reply": "ok", "call_id": "c"}))
        ),
    )
    assert client.complete([{"role": "user", "content": "x"}]) == "ok"


def test_gateway_failure_surfaces_error_instead_of_empty_reply() -> None:
    """网关失败语义：reply="" + success=false + error —— 必须抛错，不允许空串穿透为合法回答。"""
    client = LlmClient(
        api_select="qed-engine",
        api_key="",
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"reply": "", "call_id": None,
                                                    "success": False, "error": "模型调用失败：ReadTimeout"})
            )
        ),
    )
    with pytest.raises(LlmClientError, match="ReadTimeout"):
        client.complete([{"role": "user", "content": "x"}])


def test_direct_missing_key_raises() -> None:
    client = LlmClient(api_select="local", api_key="")
    with pytest.raises(LlmClientError, match="未配置"):
        client.complete([{"role": "user", "content": "x"}])


def test_http_status_error_message() -> None:
    client = _direct_client(lambda r: httpx.Response(500))
    with pytest.raises(LlmClientError, match="HTTP 500"):
        client.complete([{"role": "user", "content": "x"}])
    client.close()


def test_call_budget_exhaustion() -> None:
    client = _direct_client(lambda r: _dash_response("ok"), call_budget=1)
    assert client.complete([{"role": "user", "content": "x"}]) == "ok"
    with pytest.raises(LlmClientError, match="预算"):
        client.complete([{"role": "user", "content": "x"}])


def test_direct_records_call_into_qed_llm_calls() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE qed_llm_calls (service VARCHAR(32), mode VARCHAR(16), provider VARCHAR(32),"
                " model VARCHAR(64), endpoint VARCHAR(16), prompt_template VARCHAR(255), prompt TEXT,"
                " response TEXT, duration_ms INT, status VARCHAR(16), error VARCHAR(500), created_at DATETIME)"
            )
        )
    client = _direct_client(lambda r: _dash_response("recorded"), engine=engine)
    assert client.complete([{"role": "user", "content": "hi"}]) == "recorded"
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT service, mode, provider, endpoint, status FROM qed_llm_calls")
        ).first()
    assert tuple(row) == ("qed_tracker", "api", "qwen", "text", "success")
    client.close()


def test_direct_records_prompt_template_identifier() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE qed_llm_calls (service VARCHAR(32), mode VARCHAR(16), provider VARCHAR(32),"
                " model VARCHAR(64), endpoint VARCHAR(16), prompt_template VARCHAR(255), prompt TEXT,"
                " response TEXT, duration_ms INT, status VARCHAR(16), error VARCHAR(500), created_at DATETIME)"
            )
        )
    client = _direct_client(lambda r: _dash_response("recorded"), engine=engine)
    assert (
        client.complete(
            [{"role": "user", "content": "hi"}], prompt_template="domain-explore/scope@v1"
        )
        == "recorded"
    )
    with engine.connect() as conn:
        row = conn.execute(text("SELECT prompt_template, prompt FROM qed_llm_calls")).first()
    assert row[0] == "domain-explore/scope@v1"
    assert "hi" in row[1]
    client.close()


def test_gateway_mode_does_not_write_call_log() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE qed_llm_calls (service VARCHAR(32), mode VARCHAR(16), provider VARCHAR(32),"
                " model VARCHAR(64), endpoint VARCHAR(16), prompt_template VARCHAR(255), prompt TEXT,"
                " response TEXT, duration_ms INT, status VARCHAR(16), error VARCHAR(500), created_at DATETIME)"
            )
        )
    client = LlmClient(
        api_select="qed-engine",
        api_key="",
        engine=engine,
        client=httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"reply": "ok", "call_id": "c"}))
        ),
    )
    assert client.complete([{"role": "user", "content": "x"}]) == "ok"
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM qed_llm_calls")).scalar()
    assert count == 0


def test_recording_degrades_when_db_unreachable() -> None:
    class BoomEngine:
        def begin(self):
            raise RuntimeError("db down")

    client = _direct_client(lambda r: _dash_response("still-ok"), engine=BoomEngine())
    assert client.complete([{"role": "user", "content": "x"}]) == "still-ok"
    client.close()
