import json

import httpx
import pytest

from qed_tracker.models import Candidate, PaperProfile
from qed_tracker.prompt_lab.templates import get_template
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


# ---------- QED-068-2（S3）plan@v2 查询纪律 + 确定性清洗 ----------


def test_plan_template_upgraded_to_v2_assess_keeps_v1():
    assert get_template("paper-plan", "plan").template_id == "paper-plan/plan@v2"
    assert get_template("paper-plan", "assess").template_id == "paper-plan/assess@v1"


def test_plan_prompt_carries_query_discipline():
    captured: dict = {}

    def handler(request):
        captured["messages"] = json.loads(request.content)["messages"]
        return _response({"searches": [{"terms": ["graph neural networks"], "category": "cs.CL", "reason": "核心"}]})

    advisor = BailianPaperAdvisor(api_key="secret", client=httpx.Client(transport=httpx.MockTransport(handler)))
    advisor.plan(_profile(), "RAG", ("cs.CL",))
    user = captured["messages"][-1]["content"]
    assert "1~3 个英文词" in user
    assert "反复改写" in user


def test_plan_cleans_terms_before_validation():
    payload = {"searches": [{"terms": ['"Graph  Neural\nNets"', "graph neural nets", "PDE"], "category": "cs.CL", "reason": "相关"}]}
    advisor = BailianPaperAdvisor(
        api_key="secret", client=httpx.Client(transport=httpx.MockTransport(lambda r: _response(payload)))
    )
    searches = advisor.plan(_profile(), "RAG", ("cs.CL",))
    assert searches[0].terms == ("Graph Neural Nets", "PDE")
    assert advisor.calls == 1


def test_plan_caps_overlong_term_at_200_chars():
    payload = {"searches": [{"terms": ["x" * 300], "category": "cs.CL", "reason": "超长"}]}
    advisor = BailianPaperAdvisor(
        api_key="secret", client=httpx.Client(transport=httpx.MockTransport(lambda r: _response(payload)))
    )
    searches = advisor.plan(_profile(), "RAG", ("cs.CL",))
    assert searches[0].terms == ("x" * 200,)


def test_empty_group_after_cleaning_fails_contract_not_dropped():
    bad = {"searches": [{"terms": ['""'], "category": "cs.CL", "reason": "空组"}]}
    responses = [_response(bad), _response(bad)]
    advisor = BailianPaperAdvisor(
        api_key="secret", client=httpx.Client(transport=httpx.MockTransport(lambda r: responses.pop(0)))
    )
    with pytest.raises(BailianError, match="结构化响应无效"):
        advisor.plan(_profile(), "RAG", ("cs.CL",))
    assert advisor.calls == 2


# ---------- QED-068 W5 取证（2026-10-07）：围栏正文不得触发 repair 长调用 ----------


def _raw_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"model": "qwen/qwen3.5-9b", "choices": [{"finish_reason": "stop", "message": {"content": content}}]},
    )


def _fenced(payload) -> str:
    return "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"


def test_fenced_plan_reply_parses_in_one_call_without_repair():
    """真机形态（qed_llm_calls 行 79）：内容合规但被 ```json 围栏包裹 → 必须一次过，不烧 repair。"""
    payload = {"searches": [{"terms": ["limits", "continuity"], "category": "cs.CL", "reason": "核心框架"}]}
    responses = [_raw_response(_fenced(payload))]
    advisor = BailianPaperAdvisor(
        api_key="secret", client=httpx.Client(transport=httpx.MockTransport(lambda r: responses.pop(0)))
    )
    searches = advisor.plan(_profile(), "RAG", ("cs.CL",))
    assert searches[0].terms == ("limits", "continuity")
    assert advisor.calls == 1
    assert not responses


def test_fenced_assess_reply_parses_in_one_call_without_repair():
    payload = {
        "assessments": [
            {"arxiv_id": "2601.00001", "goal_fit": 5, "foundational_value": 4, "readability": 3,
             "reason": "相关", "risks": []}
        ]
    }
    advisor = BailianPaperAdvisor(
        api_key="secret", client=httpx.Client(transport=httpx.MockTransport(lambda r: _raw_response(_fenced(payload))))
    )
    candidate = Candidate("arxiv", "2601.00001", "Paper", identifiers={"arxiv": "2601.00001"}, abstract="data")
    assessments = advisor.assess(_profile(), "RAG", [candidate])
    assert assessments[0].score == 86
    assert advisor.calls == 1


def test_plan_with_prose_around_json_is_sliced_not_repaired():
    payload = {"searches": [{"terms": ["graph neural networks"], "category": "cs.CL", "reason": "核心"}]}
    content = "检索计划如下：\n" + json.dumps(payload, ensure_ascii=False) + "\n以上。"
    advisor = BailianPaperAdvisor(
        api_key="secret", client=httpx.Client(transport=httpx.MockTransport(lambda r: _raw_response(content)))
    )
    assert advisor.plan(_profile(), "RAG", ("cs.CL",))[0].category == "cs.CL"
    assert advisor.calls == 1


def test_plain_text_reply_still_repairs_once_then_succeeds():
    """回归护栏：真正的非 JSON 正文仍走一次 repair（容错只治形态，不放宽契约）。"""
    payload = {"searches": [{"terms": ["transformer"], "category": "cs.CL", "reason": "核心"}]}
    responses = [_raw_response("我需要更多信息才能给出计划。"), _raw_response(json.dumps(payload))]
    advisor = BailianPaperAdvisor(
        api_key="secret", client=httpx.Client(transport=httpx.MockTransport(lambda r: responses.pop(0)))
    )
    assert advisor.plan(_profile(), "", ("cs.CL",))[0].category == "cs.CL"
    assert advisor.calls == 2


def test_contract_violation_inside_fence_still_fails_after_repair():
    """围栏里的越界分类不被容错掩盖：校验仍按契约失败。"""
    payload = {"searches": [{"terms": ["x"], "category": "physics.geo", "reason": "越界"}]}
    responses = [_raw_response(_fenced(payload)), _raw_response(_fenced(payload))]
    advisor = BailianPaperAdvisor(
        api_key="secret", client=httpx.Client(transport=httpx.MockTransport(lambda r: responses.pop(0)))
    )
    with pytest.raises(BailianError, match="结构化响应无效"):
        advisor.plan(_profile(), "RAG", ("cs.CL",))
    assert advisor.calls == 2
