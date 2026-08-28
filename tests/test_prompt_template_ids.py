"""prompt 模板编号落库契约（QED-043 Phase 0）：全部 LLM 调用点向 qed_llm_calls 传模板编号。

编号格式 `{task}/{step}@v{version}` 由 prompt-lab 模板注册表统一约定；
本文件守护「每个调用点确实在落库时带上编号」（共享表审计列，前端模板聚类/审核的数据基础）。
固定 fixture（httpx.MockTransport + SQLite engine），零公网、零真实 DB。
"""

from __future__ import annotations

import json

import httpx
from sqlalchemy import create_engine, text

from qed_tracker.main_line.advisor import MainLineAdvisor
from qed_tracker.models import Candidate, CatalogTarget, PaperProfile, ResourceKind
from qed_tracker.providers.bailian import BailianPaperAdvisor
from qed_tracker.providers.book_advisor import BailianBookAdvisor

_CALL_LOG_DDL = (
    "CREATE TABLE qed_llm_calls (id INTEGER PRIMARY KEY AUTOINCREMENT, service VARCHAR(32),"
    " mode VARCHAR(16), provider VARCHAR(32),"
    " model VARCHAR(64), endpoint VARCHAR(16), prompt_template VARCHAR(255), prompt TEXT,"
    " response TEXT, duration_ms INT, status VARCHAR(16), error VARCHAR(500), created_at DATETIME)"
)


def _engine():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(_CALL_LOG_DDL))
    return engine


def _dash(payload: object) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "qwen-plus",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(payload)}}],
            "usage": {"total_tokens": 10},
        },
    )


def _templates_written(engine) -> list[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT prompt_template, status FROM qed_llm_calls ORDER BY id")
        ).fetchall()
    return [row[0] for row in rows]


def test_paper_plan_and_assess_carry_template_ids() -> None:
    engine = _engine()
    responses = [
        _dash({"searches": [{"terms": ["RAG"], "category": "cs.CL", "reason": "目标"}]}),
        _dash(
            {"assessments": [{"arxiv_id": "2601.00001", "goal_fit": 5, "foundational_value": 4, "readability": 3, "reason": "相关", "risks": []}]}
        ),
    ]
    client = httpx.Client(transport=httpx.MockTransport(lambda r: responses.pop(0)))
    advisor = BailianPaperAdvisor(api_key="k", client=client, engine=engine)
    profile = PaperProfile("p", "Profile", "Description", "Audience", ("G",), ("T",), ("cs.CL",), ())
    advisor.plan(profile, "RAG", ("cs.CL",))
    advisor.assess(profile, "RAG", [Candidate("arxiv", "2601.00001", "Paper", identifiers={"arxiv": "2601.00001"}, abstract="data")])
    assert _templates_written(engine) == ["paper-plan/plan@v1", "paper-plan/assess@v1"]


def test_book_assess_carries_template_id() -> None:
    engine = _engine()
    advisor = BailianBookAdvisor(
        api_key="k",
        engine=engine,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda r: _dash({"assessments": [{"provider_id": "ia/book", "score": 90, "verdict": "recommend", "summary": "经典"}]})
            )
        ),
    )
    target = CatalogTarget(
        id="t", course_id="c", course_name="数学分析", kind=ResourceKind.BOOK, title="数学分析原理",
        authors=("Rudin",),
    )
    advisor.assess([Candidate("ia", "ia/book", "Principles of Mathematical Analysis")], target=target)
    assert _templates_written(engine) == ["book-eval/assess@v1"]


def test_mainline_prefill_carries_template_id() -> None:
    engine = _engine()
    advisor = MainLineAdvisor(
        api_key="k",
        engine=engine,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda r: _dash(
                    {
                        "evaluation": {"text": "经典教材", "authority": "高", "set_candidate": "套1"},
                        "advice": {"download": "recommended", "reason": "名校指定"},
                    }
                )
            )
        ),
    )
    advisor.prefill(course={"course_id": "01_math_analysis", "name": "数学分析"}, title="数学分析原理", authors=["Rudin"])
    assert _templates_written(engine) == ["mainline-prefill/prefill@v1"]


def test_gateway_mode_still_pass_template_id_in_payload() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        reply = json.dumps({"searches": [{"terms": ["RAG"], "category": "cs.CL", "reason": "目标"}]})
        return httpx.Response(200, json={"reply": reply, "call_id": "c"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    advisor = BailianPaperAdvisor(
        api_select="qed-engine", api_key="", gateway_url="http://127.0.0.1:8900", client=client
    )
    profile = PaperProfile("p", "Profile", "Description", "Audience", ("G",), ("T",), ("cs.CL",), ())
    advisor.plan(profile, "RAG", ("cs.CL",))
    assert captured["body"]["prompt_template"] == "paper-plan/plan@v1"
