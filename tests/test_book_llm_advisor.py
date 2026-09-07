"""书级 LLM 顾问契约（QED-050 Phase 2）：propose_queries / confirm 定向测试。

零公网：httpx.MockTransport 假 dashscope 响应（test_bailian_advisor.py 同款）。
契约语义（download-pipeline.md 阶段1/阶段2）：
- propose_queries：book-query/variants@v1，≤variants 条变体，坏 JSON 一次修复，
  预算耗尽上抛由编排层转人工指引；
- confirm：book-confirm/assess@v1，verdict ∈ {confirmed, uncertain} 两值，
  必须完整覆盖输入候选；调用预算与 propose_queries 共享（书级 LLM_BUDGET）。
"""

from __future__ import annotations

import json

import httpx
import pytest

from qed_tracker.models import BookExpectation, Candidate
from qed_tracker.providers.book_advisor import BailianBookAdvisor


def _response(payload) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "qwen-plus",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(payload, ensure_ascii=False)}}],
            "usage": {"total_tokens": 20},
        },
    )


def _book() -> BookExpectation:
    return BookExpectation(
        title="微积分学教程",
        part="第一卷",
        authors=("菲赫金哥尔茨",),
        language="zh",
        publisher="高等教育出版社",
    )


def _candidate(provider_id: str = "math_books", **overrides) -> Candidate:
    fields = {
        "provider": "internet_archive",
        "provider_id": provider_id,
        "title": "微积分学教程 第一卷",
        "authors": ("Фихтенгольц",),
        "language": "Chinese",
        "publisher": "高等教育出版社",
        "description": "苏联古典分析教材",
    }
    fields.update(overrides)
    return Candidate(**fields)


def _advisor(responses: list[httpx.Response], **kwargs) -> BailianBookAdvisor:
    client = httpx.Client(transport=httpx.MockTransport(lambda request: responses.pop(0)))
    return BailianBookAdvisor(api_key="secret", client=client, **kwargs)


def test_propose_queries_returns_variants_with_audit():
    advisor = _advisor([_response({"queries": ["微积分学教程 菲赫金哥尔茨", " Calculus Fikhtengolts "]})])
    queries = advisor.propose_queries(_book(), variants=3)
    assert queries == ["微积分学教程 菲赫金哥尔茨", "Calculus Fikhtengolts"]
    assert advisor.calls == 1
    assert len(advisor.metadata()["response_sha256"]) == 1


def test_propose_queries_repairs_bad_json_once():
    advisor = _advisor([httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "not-json"}}]}), _response({"queries": ["数学分析"]})])
    assert advisor.propose_queries(_book()) == ["数学分析"]
    assert advisor.calls == 2  # 坏 JSON 一次修复重试


def test_propose_queries_rejects_over_limit_variants():
    """LLM 超量返回（4 条 > variants=3）视为违反契约，修复后仍超量 → 上抛。"""
    advisor = _advisor([_response({"queries": ["a", "b", "c", "d"]}), _response({"queries": ["a", "b", "c", "d"]})], call_budget=2)
    with pytest.raises(ValueError, match="不得超过 3 条"):
        advisor.propose_queries(_book(), variants=3)


def test_propose_queries_rejects_nonpositive_variants():
    advisor = _advisor([])
    with pytest.raises(ValueError, match="≥ 1"):
        advisor.propose_queries(_book(), variants=0)
    assert advisor.calls == 0


def test_confirm_two_value_verdicts():
    advisor = _advisor([_response({"confirmations": [
        {"provider_id": "math_books", "verdict": "confirmed", "summary": "书名/作者/出版社一致"},
        {"provider_id": "other", "verdict": "uncertain", "summary": "卷次不符"},
    ]})])
    result = advisor.confirm(_book(), [_candidate(), _candidate("other", title="微积分学教程 第二卷")])
    assert [(item.provider_id, item.verdict) for item in result] == [("math_books", "confirmed"), ("other", "uncertain")]
    assert all(item.summary for item in result)
    assert advisor.calls == 1


def test_confirm_rejects_old_three_state_verdict():
    """旧 book-eval 契约的 recommend 不被接受（QED-050 两值裁决）。"""
    advisor = _advisor([_response({"confirmations": [{"provider_id": "math_books", "verdict": "recommend", "summary": "x"}]}), _response({"confirmations": [{"provider_id": "math_books", "verdict": "recommend", "summary": "x"}]})], call_budget=2)
    with pytest.raises(ValueError, match="confirmed 或 uncertain"):
        advisor.confirm(_book(), [_candidate()])


def test_confirm_requires_full_candidate_coverage():
    advisor = _advisor([_response({"confirmations": [{"provider_id": "math_books", "verdict": "confirmed", "summary": "x"}]}), _response({"confirmations": [{"provider_id": "math_books", "verdict": "confirmed", "summary": "x"}]})], call_budget=2)
    with pytest.raises(ValueError, match="完整覆盖"):
        advisor.confirm(_book(), [_candidate(), _candidate("missing")])


def test_confirm_carries_candidate_intro():
    """候选介绍（enrich 产物）必须进入 confirm 输入（书名/作者/语言关键字段 + 介绍辅助）。"""
    captured = {}

    def handler(request):
        captured["prompt"] = json.loads(request.content)["messages"][-1]["content"]
        return _response({"confirmations": [{"provider_id": "math_books", "verdict": "confirmed", "summary": "一致"}]})

    advisor = BailianBookAdvisor(api_key="secret", client=httpx.Client(transport=httpx.MockTransport(handler)))
    advisor.confirm(_book(), [_candidate()])
    assert "苏联古典分析教材" in captured["prompt"]
    assert "高等教育出版社" in captured["prompt"]


def test_query_and_confirm_share_call_budget():
    """书级预算共享：propose_queries 用掉 1 次后，confirm 预算耗尽按契约上抛（编排层降级 uncertain）。"""
    advisor = _advisor([
        _response({"queries": ["微积分学教程"]}),
        _response({"confirmations": [{"provider_id": "math_books", "verdict": "confirmed", "summary": "x"}]}),
    ], call_budget=1)
    assert advisor.propose_queries(_book()) == ["微积分学教程"]
    with pytest.raises(ValueError, match="预算"):
        advisor.confirm(_book(), [_candidate()])


def test_gateway_mode_sends_both_template_ids():
    captured: list[dict] = []
    replies = [
        json.dumps({"queries": ["数学分析 陈纪修"]}, ensure_ascii=False),
        json.dumps({"confirmations": [{"provider_id": "math_books", "verdict": "confirmed", "summary": "一致"}]}, ensure_ascii=False),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"reply": replies.pop(0), "call_id": "c"})

    advisor = BailianBookAdvisor(
        api_select="qed-engine",
        api_key="",
        gateway_url="http://127.0.0.1:8900",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    advisor.propose_queries(_book())
    advisor.confirm(_book(), [_candidate()])
    assert captured[0]["prompt_template"] == "book-query/variants@v1"
    assert captured[1]["prompt_template"] == "book-confirm/assess@v1"
