import json

import httpx
import pytest

from qed_tracker.models import Candidate, PaperProfile
from qed_tracker.providers.bailian import BailianError, BailianPaperAdvisor


def _response(payload):
    return httpx.Response(200, json={"model": "qwen-plus", "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(payload)}}], "usage": {"total_tokens": 20}})


def _profile():
    return PaperProfile("p", "Profile", "Description", "Audience", ("Goal",), ("Topic",), ("cs.CL",), ())


def test_bailian_plans_and_assesses_with_strict_candidate_ids():
    responses = [
        _response({"searches": [{"terms": ["RAG", "evaluation"], "category": "cs.CL", "reason": "目标"}]}),
        _response({"assessments": [{"arxiv_id": "2601.00001", "goal_fit": 5, "foundational_value": 4, "readability": 3, "reason": "相关", "risks": []}]}),
    ]

    def handler(request):
        assert request.headers["Authorization"] == "Bearer secret"
        assert request.url.path.endswith("/chat/completions")
        return responses.pop(0)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    advisor = BailianPaperAdvisor(api_key="secret", client=client)
    searches = advisor.plan(_profile(), "RAG", ("cs.CL",))
    candidate = Candidate("arxiv", "2601.00001", "Paper", identifiers={"arxiv": "2601.00001"}, abstract="data")
    assessments = advisor.assess(_profile(), "RAG", [candidate])
    assert searches[0].terms == ("RAG", "evaluation")
    assert assessments[0].score == 86
    assert advisor.metadata()["calls"] == 2
    assert len(advisor.metadata()["response_sha256"]) == 2


def test_bailian_repairs_invalid_json_once():
    responses = [
        httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "not-json"}}]}),
        _response({"searches": [{"terms": ["transformer"], "category": "cs.CL", "reason": "核心"}]}),
    ]
    advisor = BailianPaperAdvisor(api_key="secret", client=httpx.Client(transport=httpx.MockTransport(lambda request: responses.pop(0))))
    assert advisor.plan(_profile(), "", ("cs.CL",))[0].category == "cs.CL"
    assert advisor.calls == 2


def test_bailian_rejects_missing_key_and_budget_exhaustion():
    advisor_without_key = BailianPaperAdvisor(api_key="")
    with pytest.raises(BailianError, match="未配置"):
        advisor_without_key.plan(_profile(), "", ("cs.CL",))
    assert advisor_without_key.calls == 0
    advisor = BailianPaperAdvisor(api_key="secret", call_budget=1, client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500))))
    with pytest.raises(BailianError, match="HTTP 500"):
        advisor.plan(_profile(), "", ("cs.CL",))
    with pytest.raises(BailianError, match="调用预算"):
        advisor.plan(_profile(), "", ("cs.CL",))


def test_bailian_gateway_mode_routes_via_8900_without_key():
    """qed-engine 模式：_complete 经 llm_client 调 8900 /api/v1/llm/text，不接触密钥。"""
    captured: dict = {}

    def handler(request):
        captured["auth"] = request.headers.get("Authorization")
        captured["path"] = str(request.url)
        body = json.loads(request.content)
        captured["prompt"] = body["prompt"]
        reply = json.dumps(
            {"searches": [{"terms": ["RAG"], "category": "cs.CL", "reason": "网关模式"}]},
            ensure_ascii=False,
        )
        return httpx.Response(200, json={"reply": reply, "call_id": "call-1"})

    advisor = BailianPaperAdvisor(
        api_select="qed-engine",
        api_key="",
        gateway_url="http://127.0.0.1:8900",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    searches = advisor.plan(_profile(), "RAG", ("cs.CL",))
    assert searches[0].terms == ("RAG",)
    assert captured["auth"] is None
    assert captured["path"] == "http://127.0.0.1:8900/api/v1/llm/text"
    assert "RAG" in captured["prompt"]
    assert advisor.metadata()["calls"] == 1
