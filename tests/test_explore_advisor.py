"""探索 LLM advisor 行为契约（LLM 线详规 Accepted）：输入组装 / 结构化输出校验 / 修复重试 / 预算。

固定 fixture（httpx.MockTransport），零公网。
"""

from __future__ import annotations

import json

import httpx
import pytest

from qed_tracker.providers.explore_advisor import (
    CourseExploreAdvisor,
    CurriculumExploreAdvisor,
    ExploreAdvisorError,
    normalize_set_no,
)


def _pdfless_client(responses: list[str]) -> httpx.Client:
    """按序返回固定文本响应的 MockTransport 客户端。"""
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": queue.pop(0)}, "finish_reason": "stop"}],
                                        "usage": {"total_tokens": 10}}, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _advisor(responses: list[str], **overrides) -> CourseExploreAdvisor:
    defaults = dict(
        api_key="k", model="qwen-plus", call_budget=6,
        api_select="local",
    )
    defaults.update(overrides)
    return CourseExploreAdvisor(client=_pdfless_client(responses), **defaults)


_VALID_PROPOSALS = {
    "proposals": [
        {
            "set_name": "套一",
            "textbook": {"title": "Principles of Mathematical Analysis", "authors": ["Walter Rudin"],
                          "version": {"edition": "中译本", "publisher": "机械工业出版社", "year": 2004},
                          "intro": "以度量空间上的分析为主线，适合深入研究。"},
            "exercise": {"title": "吉米多维奇数学分析习题集", "authors": ["吉米多维奇"],
                          "version": {"edition": "", "publisher": "", "year": None}, "intro": "全知识点题集。"},
            "reason": "顶尖名校指定教材",
        },
        {
            "set_name": "套二",
            "textbook": {"title": "Understanding Analysis", "authors": ["Stephen Abbott"],
                          "version": {"edition": "中译本", "publisher": "人民邮电出版社", "year": 2015},
                          "intro": "直观入门，适合初学者。"},
            "exercise": None,
            "reason": "初学者友好",
        },
    ]
}


def test_propose_course_normalizes_ids_and_set_no() -> None:
    advisor = _advisor([json.dumps(_VALID_PROPOSALS, ensure_ascii=False)])
    result = advisor.propose(
        {"course_id": "01_math_analysis", "name": "数学分析", "stage": "本科基础", "prerequisites": [], "note": ""},
        mode="direct",
    )
    assert [p["proposal_id"] for p in result] == ["pp_" + p["proposal_id"][3:] for p in result]
    assert all(p["proposal_id"].startswith("pp_") and len(p["proposal_id"]) == len("pp_") + 12 for p in result)
    assert [p["set_no"] for p in result] == ["1", "2"]
    assert normalize_set_no("英文对照套") == "en"
    assert normalize_set_no("苏版全知识点") == ""
    assert advisor.metadata()["calls"] == 1


def test_propose_text_mode_carries_reference() -> None:
    captured = {}

    class SpyAdvisor(CourseExploreAdvisor):
        def _structured(self, messages, validate):  # noqa: ANN001, ANN202
            captured["user"] = messages[-1]["content"]
            return super()._structured(messages, validate)

    advisor = SpyAdvisor(client=_pdfless_client([json.dumps(_VALID_PROPOSALS, ensure_ascii=False)]),
                         api_key="k", api_select="local")
    advisor.propose({"course_id": "c", "name": "n", "stage": "s", "prerequisites": [], "note": ""},
                    mode="text", ref_text="优先中译本")
    payload = json.loads(captured["user"].rpartition("\n")[2])
    assert payload["reference"]["text"] == "优先中译本"
    assert "中文翻译版本的美版经典" in payload["default_preferences"]["textbook_origin"]


def test_propose_doc_mode_reads_file_and_truncates(tmp_path) -> None:
    doc = tmp_path / "数学分析探索.txt"
    doc.write_text("参考内容" * 3000, encoding="utf-8")  # 18000 字符 > 8000
    advisor = _advisor([json.dumps(_VALID_PROPOSALS, ensure_ascii=False)])
    advisor.propose({"course_id": "c", "name": "n", "stage": "s", "prerequisites": [], "note": ""},
                    mode="doc", ref_doc_path=str(doc))
    reference = advisor.metadata()["last_payload"]["reference"]
    assert len(reference["text"]) == 8000
    assert reference["truncated"] is True


def test_doc_mode_invalid_encoding_maps_to_invalid_params(tmp_path) -> None:
    doc = tmp_path / "bad.txt"
    doc.write_bytes(b"\xff\xfe\x00bad")
    advisor = _advisor([])
    with pytest.raises(ExploreAdvisorError, match="UTF-8") as exc_info:
        advisor.propose({"course_id": "c", "name": "n", "stage": "s", "prerequisites": [], "note": ""},
                        mode="doc", ref_doc_path=str(doc))
    assert exc_info.value.code == "INVALID_PARAMS"


def test_mode_validation_rejects_missing_inputs(tmp_path) -> None:
    advisor = _advisor([])
    course = {"course_id": "c", "name": "n", "stage": "s", "prerequisites": [], "note": ""}
    with pytest.raises(ExploreAdvisorError, match="ref_text"):
        advisor.propose(course, mode="text", ref_text="")
    with pytest.raises(ExploreAdvisorError, match="ref_doc_path"):
        advisor.propose(course, mode="doc", ref_doc_path=str(tmp_path / "missing.txt"))
    with pytest.raises(ExploreAdvisorError, match="mode"):
        advisor.propose(course, mode="voice")


def test_repair_retry_recovers_from_bad_json() -> None:
    good = json.dumps(_VALID_PROPOSALS, ensure_ascii=False)
    advisor = _advisor(["这不是JSON", good])
    result = advisor.propose({"course_id": "c", "name": "n", "stage": "s", "prerequisites": [], "note": ""},
                             mode="direct")
    assert len(result) == 2
    assert advisor.metadata()["calls"] == 2


def test_unrepairable_response_raises_advisor_error() -> None:
    advisor = _advisor(["坏", "还是坏"])
    with pytest.raises(ExploreAdvisorError, match="结构化"):
        advisor.propose({"course_id": "c", "name": "n", "stage": "s", "prerequisites": [], "note": ""},
                        mode="direct")


def test_all_null_exercises_violates_global_rule() -> None:
    """L7：全部 proposals 的 exercise 均为 null 时校验失败（该课至少一本习题集）。"""
    broken = json.loads(json.dumps(_VALID_PROPOSALS))
    broken["proposals"][0]["exercise"] = None
    advisor = _advisor([json.dumps(broken, ensure_ascii=False), json.dumps(broken, ensure_ascii=False)])
    with pytest.raises(ExploreAdvisorError):
        advisor.propose({"course_id": "c", "name": "n", "stage": "s", "prerequisites": [], "note": ""},
                        mode="direct")


def test_budget_exhaustion_raises() -> None:
    advisor = _advisor([], call_budget=1)
    advisor.llm_client.calls = 1  # 直接触发 LlmClient 预算闸
    with pytest.raises(ExploreAdvisorError, match="预算"):
        advisor.propose({"course_id": "c", "name": "n", "stage": "s", "prerequisites": [], "note": ""},
                        mode="direct")


def test_gateway_client_without_key_is_configured() -> None:
    """qed-engine 网关模式不接触密钥：无 API_KEY 也视为可用（网关响应 {reply} 格式）。"""
    gateway = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"reply": json.dumps(_VALID_PROPOSALS, ensure_ascii=False)},
                                       request=request)
    ))
    advisor = CourseExploreAdvisor(api_key="", api_select="qed-engine", gateway_url="http://gw.test", client=gateway)
    result = advisor.propose({"course_id": "c", "name": "n", "stage": "s", "prerequisites": [], "note": ""},
                             mode="direct")
    assert len(result) == 2


def test_llm_transport_error_wraps_as_llm_unavailable() -> None:
    advisor = _advisor([])
    advisor.llm_client.client.close()
    advisor.llm_client.client = httpx.Client(
        transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ConnectError("boom"))),
    )
    with pytest.raises(ExploreAdvisorError) as exc_info:
        advisor.propose({"course_id": "c", "name": "n", "stage": "s", "prerequisites": [], "note": ""},
                        mode="direct")
    assert exc_info.value.code == "LLM_UNAVAILABLE"


# ---------------- 领域层 CurriculumExploreAdvisor ----------------

_VALID_CHANGES = {
    "changes": [
        {"action": "create_domain", "entity": "domain", "target_id": "advanced_math",
         "payload": {"name": "高等数学", "description": "本科高数课程群",
                      "stages": ["本科基础", "本科进阶"]},
         "reason": "补齐工科数学主线"},
        {"action": "create_course", "entity": "course", "target_id": "01_calculus",
         "payload": {"name": "数学分析", "stage": "本科基础", "sort_order": 1,
                      "prerequisites": [], "aliases": ["分析"], "note": "核心基础课"},
         "reason": "体系起点"},
        {"action": "create_course", "entity": "course", "target_id": "02_ode",
         "payload": {"name": "常微分方程", "stage": "本科进阶", "sort_order": 2,
                      "prerequisites": ["01_calculus"], "aliases": [], "note": ""},
         "reason": "后续课程先修"},
        {"action": "create_course", "entity": "course", "target_id": "03_complex",
         "payload": {"name": "复变函数", "stage": "本科进阶", "sort_order": 3,
                      "prerequisites": ["01_calculus"], "aliases": [], "note": ""},
         "reason": "工程数学主干"},
    ]
}


def _curriculum_advisor(responses: list[str], **overrides) -> CurriculumExploreAdvisor:
    defaults = dict(api_key="k", model="qwen-plus", call_budget=6, api_select="local")
    defaults.update(overrides)
    return CurriculumExploreAdvisor(client=_pdfless_client(responses), **defaults)


def test_curriculum_propose_normalizes_change_ids_and_order() -> None:
    advisor = _curriculum_advisor([json.dumps(_VALID_CHANGES, ensure_ascii=False)])
    result = advisor.propose("高等数学", mode="direct")
    assert [c["change_id"] for c in result] == ["ch_01", "ch_02", "ch_03", "ch_04"]
    assert result[0]["action"] == "create_domain"
    assert all(c["action"] == "create_course" for c in result[1:])


def test_curriculum_repair_retry_on_bad_slug() -> None:
    """slug 格式非法触发一次修复重试后成功。"""
    broken = json.loads(json.dumps(_VALID_CHANGES))
    broken["changes"][1]["target_id"] = "Bad Slug!"
    good = json.dumps(_VALID_CHANGES, ensure_ascii=False)
    advisor = _curriculum_advisor([json.dumps(broken, ensure_ascii=False), good])
    result = advisor.propose("高等数学", mode="direct")
    assert result[1]["target_id"] == "01_calculus"


def test_curriculum_prerequisites_must_reference_batch(repo=None) -> None:
    broken = json.loads(json.dumps(_VALID_CHANGES))
    broken["changes"][2]["payload"]["prerequisites"] = ["cs_ai"]  # 不在本批
    advisor = _curriculum_advisor([json.dumps(broken, ensure_ascii=False),
                                   json.dumps(broken, ensure_ascii=False)])
    with pytest.raises(ExploreAdvisorError):
        advisor.propose("高等数学", mode="direct")


def test_curriculum_stage_must_be_in_domain_stages() -> None:
    broken = json.loads(json.dumps(_VALID_CHANGES))
    broken["changes"][2]["payload"]["stage"] = "研究生基础"  # domain stages 未包含
    advisor = _curriculum_advisor([json.dumps(broken, ensure_ascii=False),
                                   json.dumps(broken, ensure_ascii=False)])
    with pytest.raises(ExploreAdvisorError):
        advisor.propose("高等数学", mode="direct")


def test_curriculum_domain_must_come_first_and_be_unique() -> None:
    broken = json.loads(json.dumps(_VALID_CHANGES))
    broken["changes"].pop(0)  # 缺 create_domain
    advisor = _curriculum_advisor([json.dumps(broken, ensure_ascii=False),
                                   json.dumps(broken, ensure_ascii=False)])
    with pytest.raises(ExploreAdvisorError):
        advisor.propose("高等数学", mode="direct")


def test_curriculum_count_bounds_enforced() -> None:
    too_many = json.loads(json.dumps(_VALID_CHANGES))
    extra = dict(too_many["changes"][3])
    extra["target_id"] = "04_extra"
    too_many["changes"].append(extra)
    assert len(too_many["changes"]) == 5  # 5 在 4~9 界内：先补足再越界
    more = [dict(too_many["changes"][3], target_id=f"x_{i:02d}") for i in range(6)]
    too_many["changes"].extend(more)
    advisor = _curriculum_advisor([json.dumps(too_many, ensure_ascii=False),
                                   json.dumps(too_many, ensure_ascii=False)])
    with pytest.raises(ExploreAdvisorError):
        advisor.propose("高等数学", mode="direct")


def test_curriculum_doc_mode_reads_reference(tmp_path) -> None:
    doc = tmp_path / "领域探索.txt"
    doc.write_text("领域：高等数学\n范围：本科\n备注：对照顶尖工科院系", encoding="utf-8")
    captured = {}

    class Spy(CurriculumExploreAdvisor):
        def _structured(self, messages, validate):  # noqa: ANN001, ANN202
            captured["user"] = messages[-1]["content"]
            return super()._structured(messages, validate)

    advisor = Spy(client=_pdfless_client([json.dumps(_VALID_CHANGES, ensure_ascii=False)]),
                  api_key="k", api_select="local")
    advisor.propose("高等数学", mode="doc", ref_doc_path=str(doc))
    payload = json.loads(captured["user"].rpartition("\n")[2])
    assert payload["domain_name"] == "高等数学"
    assert "备注：对照顶尖工科院系" in payload["reference"]["text"]
