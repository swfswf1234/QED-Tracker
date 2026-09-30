"""prompt 模板编号落库契约（QED-043 Phase 0）：全部 LLM 调用点向 qed_llm_calls 传模板编号。

编号格式 `{task}/{step}@v{version}` 由 prompt-lab 模板注册表统一约定；
本文件守护「每个调用点确实在落库时带上编号」（共享表审计列，前端模板聚类/审核的数据基础）。
QED-072 W-8 追加注册表覆盖守护：src 内出现的每个模板编号必须能在 `prompt_lab.templates`
注册表解析到条目（或在豁免清单内注明去向），使「注册表＝全部 LLM prompt 唯一事实源」可检验。
固定 fixture（httpx.MockTransport + SQLite engine），零公网、零真实 DB。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text

from qed_tracker.main_line.advisor import MainLineAdvisor
from qed_tracker.models import BookExpectation, Candidate, PaperProfile
from qed_tracker.prompt_lab import templates as templates_mod
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


def test_book_query_and_confirm_carry_template_ids() -> None:
    """QED-050 书级检索词变体与确认评估同样落模板编号（qed_llm_calls 审计）。"""
    engine = _engine()
    responses = [
        _dash({"queries": ["Rudin 数学分析原理"]}),
        _dash({"confirmations": [{"provider_id": "ia/book", "verdict": "confirmed", "summary": "一致"}]}),
    ]
    advisor = BailianBookAdvisor(
        api_key="k",
        engine=engine,
        client=httpx.Client(transport=httpx.MockTransport(lambda r: responses.pop(0))),
    )
    book = BookExpectation(title="数学分析原理", authors=("Rudin",), language="zh")
    advisor.propose_queries(book)
    advisor.confirm(book, [Candidate("ia", "ia/book", "数学分析原理")])
    assert _templates_written(engine) == ["book-query/variants@v1", "book-confirm/assess@v1"]


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


# ---------------- 注册表覆盖守护（QED-072 W-8） ----------------

_SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "qed_tracker"
_PY_ID = re.compile(r"""(?:prompt_template\s*=\s*|_template_id\s*=\s*)["']([^"'\s{}]+)["']""")
_YAML_ID = re.compile(r"^\s*template:\s*(\S+)\s*$", re.MULTILINE)

# 尚未登记进注册表的模板编号 → W-8 处置去向（步骤 2~5 逐条摘除；清单清空即收口完成）。
UNREGISTERED_EXEMPT: dict[str, str] = {
    "paper-plan/plan@v1": "QED-074 W-2 迁入注册表（2026-09-29 改判：D-7 的删除裁决作废，空窗取消）",
    "paper-plan/assess@v1": "QED-074 W-2 迁入注册表（同上，在册改写 assess@v2）",
    "domain-explore/domain-agentic@v1": "W-8 步骤 5 纳入（并行会话未跟踪 WIP）",
    "domain-explore/courses-agentic@v1": "W-8 步骤 5 纳入（并行会话未跟踪 WIP）",
    "domain-agentic@v1": "W-8 步骤 5 纳入（pipeline yaml 裸编号缺 task 前缀，同 Q67-c）",
}


def _ids_in_src() -> dict[str, str]:
    """扫描 src 内全部模板编号字面量（含 pipeline yaml 的 `template:`），返回 编号 -> 出处。"""
    found: dict[str, str] = {}
    for path in sorted(list(_SRC_ROOT.rglob("*.py")) + list(_SRC_ROOT.rglob("*.yaml"))):
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), 1):
            match = _PY_ID.search(line) or _YAML_ID.search(line)
            if match:
                found.setdefault(match.group(1), f"{path.as_posix()}:{line_no}")
    return found


def _orphans() -> set[str]:
    registered = {item["id"] for item in templates_mod.list_templates()}
    return {key for key in _ids_in_src() if key not in registered}


def test_no_orphan_template_id_outside_registry() -> None:
    undocumented = sorted(_orphans() - set(UNREGISTERED_EXEMPT))
    assert not undocumented, f"未登记且未豁免的模板编号（新调用点必须注册进 templates.py）：{undocumented}"


def test_registry_inventory_is_pinned() -> None:
    """注册表条目清单变化必须显式改动本断言（防止悄悄漏登记）。"""
    assert sorted(item["id"] for item in templates_mod.list_templates()) == [
        "book-confirm/assess@v1",
        "book-query/variants@v1",
        "course-explore/tutorials@v2",
        "domain-explore/courses@v8",
        "domain-explore/domain@v4",
        "mainline-prefill/prefill@v1",
    ]


def test_exempt_list_carries_no_stale_entries() -> None:
    """豁免清单不得留已迁走或已删除的编号（W-8 每步交付后据此收口）。"""
    stale = sorted(set(UNREGISTERED_EXEMPT) - _orphans())
    assert not stale, f"豁免清单已失效，请删除：{stale}"


def test_exempt_entries_state_their_destination() -> None:
    assert all(
        value.startswith(("W-8 步骤", "QED-074")) for value in UNREGISTERED_EXEMPT.values()
    )
