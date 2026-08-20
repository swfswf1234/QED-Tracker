from __future__ import annotations

import json

import httpx
import pytest

from qed_tracker.main_line.advisor import MainLineAdvisor


def _fake_llm(request: httpx.Request) -> httpx.Response:
    payload = {
        "evaluation": {
            "text": "Rudin《数学分析原理》是数学系经典教材，MIT 等多校指定",
            "authority": "高",
            "set_candidate": "套一",
        },
        "advice": {"download": "recommended", "reason": "顶尖大学指定 + 中译本可得"},
    }
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}, "finish_reason": "stop"}]})


def test_prefill_course_context_in_prompt() -> None:
    requests: list[dict] = []

    def capture(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"evaluation": {"text": "x", "authority": "中", "set_candidate": ""}, "advice": {"download": "optional", "reason": "y"}}, ensure_ascii=False)}, "finish_reason": "stop"}]})

    advisor = MainLineAdvisor(api_key="test-key", client=httpx.Client(transport=httpx.MockTransport(capture)))
    result = advisor.prefill(
        course={"course_id": "01_math_analysis", "name": "数学分析", "stage": "本科基础"},
        title="数学分析原理",
        authors=["Rudin"],
    )
    assert result["evaluation"]["authority"] in {"高", "中", "低"}
    assert result["advice"]["download"] in {"recommended", "optional", "not_recommended"}
    system_prompt = requests[0]["messages"][0]["content"]
    assert "数学分析" in system_prompt
    assert "顶尖大学" in system_prompt


def test_prefill_happy_path_returns_contract() -> None:
    advisor = MainLineAdvisor(api_key="test-key", client=httpx.Client(transport=httpx.MockTransport(_fake_llm)))
    result = advisor.prefill(
        course={"course_id": "01_math_analysis", "name": "数学分析", "stage": "本科基础"},
        title="数学分析原理",
        authors=["Rudin"],
    )
    assert result["evaluation"]["source"] == "llm"
    assert result["evaluation"]["authority"] == "高"
    assert result["evaluation"]["set_candidate"] == "套一"
    assert result["advice"] == {"download": "recommended", "reason": "顶尖大学指定 + 中译本可得"}


def test_no_api_key_raises() -> None:
    advisor = MainLineAdvisor(api_key="")
    with pytest.raises(ValueError):
        advisor.prefill(course={"course_id": "01", "name": "x"}, title="y", authors=[])


def test_invalid_llm_output_raises() -> None:
    advisor = MainLineAdvisor(api_key="test-key", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "not json"}, "finish_reason": "stop"}]}))))
    with pytest.raises(ValueError):
        advisor.prefill(course={"course_id": "01", "name": "x"}, title="y", authors=[])


def test_gateway_mode_routes_via_8900_without_key() -> None:
    """qed-engine 模式：prefill 经 llm_client 调 8900 /api/v1/llm/text，不接触密钥。"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization")
        captured["path"] = str(request.url)
        body = json.loads(request.content)
        captured["prompt"] = body["prompt"]
        reply = json.dumps(
            {"evaluation": {"text": "网关预填", "authority": "中", "set_candidate": ""},
             "advice": {"download": "optional", "reason": "网关模式"}},
            ensure_ascii=False,
        )
        return httpx.Response(200, json={"reply": reply, "call_id": "call-1"})

    advisor = MainLineAdvisor(
        api_select="qed-engine",
        api_key="",
        gateway_url="http://127.0.0.1:8900",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = advisor.prefill(
        course={"course_id": "01_math_analysis", "name": "数学分析", "stage": "本科基础"},
        title="数学分析原理",
        authors=["Rudin"],
    )
    assert result["evaluation"]["source"] == "llm"
    assert captured["auth"] is None
    assert captured["path"] == "http://127.0.0.1:8900/api/v1/llm/text"
    assert "数学分析原理" in captured["prompt"]
