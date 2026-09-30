"""QED-067 isolated LangChain orchestration contracts."""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from qed_tracker.orchestration.config import (
    ConfigurationError,
    PipelineRegistry,
    PipelineSpec,
    PipelineStep,
    ToolCatalog,
    load_pipeline,
    load_skill,
)
from qed_tracker.orchestration.evidence import EvidencePacker, EvidenceSource
from qed_tracker.orchestration.lcel import LlmChatModel
from qed_tracker.orchestration.pipeline import (
    OrchestrationError,
    PhaseResult,
    run_courses_phase,
    run_domain_phase,
)
from qed_tracker.orchestration.runner import ToolOutcome, run_pipeline, write_run_artifact
from qed_tracker.prompt_lab.pipeline import NameConfirmationRequired

_VALID_DOMAIN = {
    "name_check": {"valid": True, "reason": "领域名称明确", "suggested_name": ""},
    "final_name": "高等数学",
    "description": "大学阶段的数学核心课程体系，覆盖分析、代数等主干并为后续专业学习提供基础。",
    "level": "本科",
    "classic_tracks": [
        {"name": "分析", "summary": "极限与分析方法", "kind": "main"},
        {"name": "代数", "summary": "代数结构与计算", "kind": "main"},
    ],
    "entry_requirements": "具备高中数学与基础微积分知识",
    "prior_knowledge": "先修基础数学并按由浅入深的顺序学习。",
    "evidence_refs": ["wiki-01", "mit-01"],
}


class _FakeLlmClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[list[dict[str, str]], str]] = []

    def complete(self, messages: list[dict[str, str]], *, prompt_template: str = "") -> str:
        self.calls.append((messages, prompt_template))
        return self.responses.pop(0)


def test_chat_model_delegates_messages_and_template_to_llm_client() -> None:
    client = _FakeLlmClient(["结构化回答"])

    reply = LlmChatModel(client).invoke(
        [SystemMessage(content="系统规则"), HumanMessage(content="用户任务")],
        prompt_template="domain-explore/domain-agentic@v1",
    )

    assert reply.content == "结构化回答"
    assert client.calls == [
        (
            [
                {"role": "system", "content": "系统规则"},
                {"role": "user", "content": "用户任务"},
            ],
            "domain-explore/domain-agentic@v1",
        )
    ]


def test_pipeline_config_rejects_unknown_and_unauthorized_tools(tmp_path) -> None:
    catalog = ToolCatalog({"wikipedia.search": {"read_only": True}})
    path = tmp_path / "domain.yaml"
    path.write_text(
        """
name: domain-exploration
version: 1
task: domain_explore
steps:
  - id: wiki_lookup
    kind: tool
    tool: university.fetch
  - id: domain_synthesis
    kind: llm
    template: domain-agentic@v1
    tools: [wikipedia.search]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="university.fetch"):
        load_pipeline(path, catalog=catalog)

    path.write_text(
        path.read_text(encoding="utf-8").replace("university.fetch", "wikipedia.search"),
        encoding="utf-8",
    )
    restricted = ToolCatalog({"wikipedia.search": {"read_only": False}})
    with pytest.raises(ConfigurationError, match="只读"):
        load_pipeline(path, catalog=restricted)


def test_config_rejects_unknown_nested_pipeline_and_skill_fields(tmp_path) -> None:
    catalog = ToolCatalog({"wikipedia.search": {"read_only": True}})
    pipeline_path = tmp_path / "domain.yaml"
    pipeline_path.write_text(
        """
name: domain-exploration
version: 1
task: domain_explore
steps:
  - id: wiki_lookup
    kind: tool
    tool: wikipedia.search
    unreviewed: true
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="未知字段"):
        load_pipeline(pipeline_path, catalog=catalog)

    pipeline_path.write_text(
        # 注意：上文 write_text 用 .strip() 写入，文件无尾换行，模式串不得带 \n（否则 no-op）。
        pipeline_path.read_text(encoding="utf-8").replace("    unreviewed: true", ""),
        encoding="utf-8",
    )
    pipeline = load_pipeline(pipeline_path, catalog=catalog)
    skill_path = tmp_path / "domain-skill.yaml"
    skill_path.write_text(
        """
name: domain-exploration
pipeline: domain-exploration
requires:
  tools: [wikipedia.search]
  network: false
  unreviewed: true
max_payload_tokens: 5388
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="未知字段"):
        load_skill(skill_path, pipeline=pipeline, catalog=catalog)


def test_pipeline_registry_rejects_lower_version_and_skill_tool_escalation(tmp_path) -> None:
    catalog = ToolCatalog(
        {
            "wikipedia.search": {"read_only": True},
            "university.search": {"read_only": True},
        }
    )
    pipeline_path = tmp_path / "domain.yaml"
    pipeline_path.write_text(
        """
name: domain-exploration
version: 2
task: domain_explore
steps:
  - id: wiki_lookup
    kind: tool
    tool: wikipedia.search
""".strip(),
        encoding="utf-8",
    )
    pipeline = load_pipeline(pipeline_path, catalog=catalog)
    registry = PipelineRegistry()
    registry.register(pipeline)

    lower = pipeline_path.read_text(encoding="utf-8").replace("version: 2", "version: 1")
    pipeline_path.write_text(lower, encoding="utf-8")
    with pytest.raises(ConfigurationError, match="低版本"):
        registry.register(load_pipeline(pipeline_path, catalog=catalog))

    skill_path = tmp_path / "domain-skill.yaml"
    skill_path.write_text(
        """
name: domain-exploration
pipeline: domain-exploration
requires:
  tools: [university.search]
  network: false
max_payload_tokens: 5388
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="未获 pipeline 批准"):
        load_skill(skill_path, pipeline=pipeline, catalog=catalog)


def test_evidence_packer_trims_deterministically_and_records_budget_omissions() -> None:
    sources = [
        EvidenceSource(
            source_id="wiki-01",
            family="wikipedia",
            institution=None,
            title="领域定义",
            canonical_url="https://example.test/wiki",
            retrieved_at="2026-09-26T00:00:00Z",
            excerpt="定义证据。" * 300,
            locator="definition",
            claims=("definition",),
            priority=0,
        ),
        EvidenceSource(
            source_id="mit-01",
            family="university",
            institution="MIT",
            title="课程页",
            canonical_url="https://example.test/mit",
            retrieved_at="2026-09-26T00:00:00Z",
            excerpt="课程顺序证据。" * 300,
            locator="overview",
            claims=("course_title", "ordering"),
            priority=1,
        ),
        EvidenceSource(
            source_id="stanford-01",
            family="university",
            institution="Stanford",
            title="课程目录",
            canonical_url="https://example.test/stanford",
            retrieved_at="2026-09-26T00:00:00Z",
            excerpt="先修证据。" * 300,
            locator="requirements",
            claims=("prerequisite",),
            priority=2,
        ),
    ]

    packed = EvidencePacker(max_tokens=180).pack(
        domain_name="高等数学",
        scope_hint="本科",
        language="zh",
        phase="domain",
        sources=sources,
        requested_families=("wikipedia", "MIT", "Stanford", "Tsinghua"),
    )

    assert packed.estimated_tokens <= 180
    assert [source["source_id"] for source in packed.bundle["sources"]] == ["wiki-01", "mit-01"]
    assert packed.bundle["coverage"]["missing"] == [
        {"family": "Stanford", "reason": "omitted_for_budget"},
        {"family": "Tsinghua", "reason": "not_collected"},
    ]
    assert packed.bundle["sources"][0]["truncated"] is True


def test_evidence_packer_budgets_control_and_source_metadata() -> None:
    packed = EvidencePacker(max_tokens=180).pack(
        domain_name="领域名称" * 200,
        scope_hint="范围说明" * 200,
        language="zh",
        phase="domain",
        sources=[
            EvidenceSource(
                source_id="wiki-01",
                family="wikipedia",
                institution=None,
                title="超长标题" * 200,
                canonical_url="https://example.test/" + "path/" * 200,
                retrieved_at="2026-09-26T00:00:00Z",
                excerpt="定义证据。" * 200,
                locator="超长定位" * 200,
                claims=("definition",),
                priority=0,
            )
        ],
        requested_families=("wikipedia",),
    )

    assert packed.estimated_tokens <= 180
    assert len(packed.bundle["query"]["domain_name"]) < len("领域名称" * 200)
    assert packed.bundle["sources"][0]["truncated"] is True


def test_domain_phase_requires_existing_name_confirmation_guard() -> None:
    invalid = {
        **_VALID_DOMAIN,
        "name_check": {"valid": False, "reason": "名称歧义", "suggested_name": "数学"},
        "evidence_refs": [],
    }
    client = _FakeLlmClient([json.dumps(invalid, ensure_ascii=False)])
    evidence = EvidencePacker(max_tokens=1_000).pack(
        domain_name="高等数学",
        scope_hint="本科",
        language="zh",
        phase="domain",
        sources=[],
        requested_families=(),
    )

    with pytest.raises(NameConfirmationRequired):
        run_domain_phase(client, evidence)


def test_domain_phase_returns_existing_contract_and_keeps_citations_in_trace() -> None:
    client = _FakeLlmClient([json.dumps(_VALID_DOMAIN, ensure_ascii=False)])
    evidence = EvidencePacker(max_tokens=1_000).pack(
        domain_name="高等数学",
        scope_hint="本科",
        language="zh",
        phase="domain",
        sources=[
            EvidenceSource(
                source_id="wiki-01",
                family="wikipedia",
                institution=None,
                title="领域定义",
                canonical_url="https://example.test/wiki",
                retrieved_at="2026-09-26T00:00:00Z",
                excerpt="领域定义。",
                locator="definition",
                claims=("definition",),
                priority=0,
            ),
            EvidenceSource(
                source_id="mit-01",
                family="university",
                institution="MIT",
                title="课程页",
                canonical_url="https://example.test/mit",
                retrieved_at="2026-09-26T00:00:00Z",
                excerpt="课程组织。",
                locator="overview",
                claims=("course_title",),
                priority=1,
            ),
        ],
        requested_families=("wikipedia", "MIT"),
    )

    result = run_domain_phase(client, evidence)

    assert result.report["domain"]["final_name"] == "高等数学"
    assert "evidence_refs" not in result.report["domain"]
    assert result.trace["evidence_refs"] == ["wiki-01", "mit-01"]
    assert client.calls[0][1] == "domain-explore/domain-agentic@v1"


def test_courses_phase_returns_existing_courses_contract_after_domain_confirmation() -> None:
    courses = {
        "courses": [
            {
                "course_id": "math_analysis",
                "name": "数学分析",
                "aliases": ["微积分"],
                "track": "分析",
                "summary": "系统学习极限、连续、微分、积分与级数等基本理论，训练严谨推理与证明能力，并建立后续实分析、拓扑、微分方程等课程所需的概念框架、计算方法和抽象分析基础。",
                "university_basis": ["MIT 官方课程页"],
                "stage": "基础",
                "prerequisites": [],
            }
        ],
        "notes": "先完成基础分析，再进入后续主干课程。",
        "evidence_refs": ["mit-01"],
    }
    client = _FakeLlmClient([json.dumps(courses, ensure_ascii=False)])
    evidence = EvidencePacker(max_tokens=1_000).pack(
        domain_name="高等数学",
        scope_hint="本科",
        language="zh",
        phase="courses",
        sources=[
            EvidenceSource(
                source_id="mit-01",
                family="university",
                institution="MIT",
                title="课程页",
                canonical_url="https://example.test/mit",
                retrieved_at="2026-09-26T00:00:00Z",
                excerpt="课程组织。",
                locator="overview",
                claims=("course_title", "ordering"),
                priority=0,
            )
        ],
        requested_families=("MIT",),
    )

    result = run_courses_phase(
        client,
        evidence,
        domain_info={
            "description": _VALID_DOMAIN["description"],
            "level": "本科",
            "classic_tracks": _VALID_DOMAIN["classic_tracks"],
            "entry_requirements": _VALID_DOMAIN["entry_requirements"],
        },
    )

    assert result.report["courses"][0]["course_id"] == "math_analysis"
    assert result.report["path"]["edges"] == []
    assert result.trace["evidence_refs"] == ["mit-01"]
    assert client.calls[0][1] == "domain-explore/courses-agentic@v1"


def test_domain_phase_rejects_unknown_citation() -> None:
    invalid = {**_VALID_DOMAIN, "evidence_refs": ["invented-01"]}
    client = _FakeLlmClient([json.dumps(invalid, ensure_ascii=False)])
    evidence = EvidencePacker(max_tokens=1_000).pack(
        domain_name="高等数学",
        scope_hint="本科",
        language="zh",
        phase="domain",
        sources=[],
        requested_families=(),
    )

    with pytest.raises(OrchestrationError, match="不存在"):
        run_domain_phase(client, evidence)


_RUNNER_SOURCES = (
    EvidenceSource(
        source_id="wiki-01",
        family="wikipedia",
        institution=None,
        title="高等数学",
        canonical_url="https://en.wikipedia.org/wiki/Calculus",
        retrieved_at="2026-09-26T00:00:00Z",
        excerpt="高等数学是大学阶段的数学核心课程。",
        locator="para-0",
        claims=("definition",),
        priority=1,
    ),
    EvidenceSource(
        source_id="mit-01",
        family="university",
        institution="MIT",
        title="18.01 Single Variable Calculus",
        canonical_url="https://student.mit.edu/catalog/m18a.html",
        retrieved_at="2026-09-26T00:00:01Z",
        excerpt="覆盖极限、微分与积分。",
        locator="heading-1",
        claims=("course_title",),
        priority=2,
    ),
)


def _domain_payload() -> str:
    return json.dumps(_VALID_DOMAIN, ensure_ascii=False)


def _runner_pipeline(llm_template: str = "domain-agentic@v1") -> PipelineSpec:
    return PipelineSpec(
        name="domain-exploration",
        version=1,
        task="domain-explore",
        steps=(
            PipelineStep("wiki_lookup", "tool", tool="wikipedia.search"),
            PipelineStep("university_lookup", "tool", tool="university.search"),
            PipelineStep("domain_synthesis", "llm", template=llm_template),
        ),
    )


def _runner_tools() -> dict:
    return {
        "wikipedia.search": lambda _state: ToolOutcome(
            sources=(_RUNNER_SOURCES[0],), marker="fixture:wiki-01"
        ),
        "university.search": lambda _state: ToolOutcome(
            sources=(_RUNNER_SOURCES[1],), marker="fixture:mit-01"
        ),
    }


def test_executor_runs_declared_order_and_records_observed_templates() -> None:
    client = _FakeLlmClient([_domain_payload()])
    seen: list[str] = []

    def wiki(_state) -> ToolOutcome:
        seen.append("wiki_lookup")
        return ToolOutcome(sources=(_RUNNER_SOURCES[0],), marker="fixture:wiki-01")

    def university(_state) -> ToolOutcome:
        seen.append("university_lookup")
        return ToolOutcome(sources=(_RUNNER_SOURCES[1],), marker="fixture:mit-01")

    def synthesize(state, expected_ref: str) -> PhaseResult:
        seen.append("domain_synthesis")
        content = state.client.complete(
            [{"role": "user", "content": "bundle"}], prompt_template=expected_ref
        )
        return PhaseResult(
            report=json.loads(content),
            trace={
                "evidence_refs": ["wiki-01"],
                "estimated_evidence_tokens": state.packed.estimated_tokens,
            },
        )

    result = run_pipeline(
        client=client,
        pipeline=_runner_pipeline(),
        tools={"wikipedia.search": wiki, "university.search": university},
        synthesis={"domain-agentic@v1": synthesize},
        domain_name="高等数学",
        scope_hint="本科",
        language="zh",
        run_id="067-test-run",
    )

    assert seen == ["wiki_lookup", "university_lookup", "domain_synthesis"]
    assert [(entry.seq, entry.step_id, entry.kind) for entry in result.trace] == [
        (1, "wiki_lookup", "tool"),
        (2, "university_lookup", "tool"),
        (3, "domain_synthesis", "llm"),
    ]
    assert result.trace[0].source_ids == ("wiki-01",)
    assert result.trace[0].marker == "fixture:wiki-01"
    assert result.trace[2].template_ref == "domain-explore/domain_synthesis@v1"
    assert result.trace[2].observed_prompt_templates == ("domain-explore/domain_synthesis@v1",)
    assert result.trace[2].source_ids == ("wiki-01", "mit-01")
    assert client.calls[0][1] == "domain-explore/domain_synthesis@v1"
    assert [call["prompt_template"] for call in result.llm_calls] == [
        "domain-explore/domain_synthesis@v1"
    ]


def test_executor_records_multiple_calls_within_one_step_in_order() -> None:
    client = _FakeLlmClient([_domain_payload(), _domain_payload()])

    def synthesize(state, expected_ref: str) -> PhaseResult:
        state.client.complete([{"role": "user", "content": "x"}], prompt_template=expected_ref)
        content = state.client.complete(
            [{"role": "user", "content": "x"}], prompt_template=f"{expected_ref}+repair"
        )
        return PhaseResult(report=json.loads(content), trace={})

    result = run_pipeline(
        client=client,
        pipeline=_runner_pipeline(),
        tools=_runner_tools(),
        synthesis={"domain-agentic@v1": synthesize},
        domain_name="高等数学",
        scope_hint="本科",
        language="zh",
    )

    assert result.trace[2].observed_prompt_templates == (
        "domain-explore/domain_synthesis@v1",
        "domain-explore/domain_synthesis@v1+repair",
    )
    assert [call["seq"] for call in result.llm_calls] == [1, 2]


def test_executor_rejects_missing_tool_handler_before_any_llm_call() -> None:
    client = _FakeLlmClient([_domain_payload()])

    with pytest.raises(OrchestrationError, match="未注册工具"):
        run_pipeline(
            client=client,
            pipeline=_runner_pipeline(),
            tools={"wikipedia.search": lambda _state: ToolOutcome(sources=(_RUNNER_SOURCES[0],))},
            synthesis={"domain-agentic@v1": lambda _s, _t: PhaseResult(report={}, trace={})},
            domain_name="高等数学",
            scope_hint="本科",
            language="zh",
        )

    assert client.calls == []


def test_executor_requires_handler_for_every_step_kind() -> None:
    client = _FakeLlmClient([])

    with pytest.raises(OrchestrationError, match="未注册步骤处理"):
        run_pipeline(
            client=client,
            pipeline=_runner_pipeline(),
            tools=_runner_tools(),
            synthesis={},
            domain_name="高等数学",
            scope_hint="本科",
            language="zh",
        )

    assert client.calls == []


def test_executor_rejects_template_ref_outside_numbered_convention() -> None:
    client = _FakeLlmClient([])

    with pytest.raises(OrchestrationError, match="模板编号"):
        run_pipeline(
            client=client,
            pipeline=_runner_pipeline(llm_template="domain-agentic"),
            tools=_runner_tools(),
            synthesis={"domain-agentic": lambda _s, _t: PhaseResult(report={}, trace={})},
            domain_name="高等数学",
            scope_hint="本科",
            language="zh",
        )


def test_executor_fails_when_llm_step_makes_no_observed_call() -> None:
    client = _FakeLlmClient([])

    with pytest.raises(OrchestrationError, match="未产生任何模型调用"):
        run_pipeline(
            client=client,
            pipeline=_runner_pipeline(),
            tools=_runner_tools(),
            synthesis={"domain-agentic@v1": lambda _state, _ref: PhaseResult(report={}, trace={})},
            domain_name="高等数学",
            scope_hint="本科",
            language="zh",
        )


def test_run_artifact_keeps_llm_order_for_qed_llm_calls_readback(tmp_path) -> None:
    client = _FakeLlmClient([_domain_payload()])

    def synthesize(state, expected_ref: str) -> PhaseResult:
        content = state.client.complete(
            [{"role": "user", "content": "b" * 40}], prompt_template=expected_ref
        )
        return PhaseResult(
            report=json.loads(content),
            trace={"evidence_refs": ["wiki-01"], "estimated_evidence_tokens": 1234},
        )

    result = run_pipeline(
        client=client,
        pipeline=_runner_pipeline(),
        tools=_runner_tools(),
        synthesis={"domain-agentic@v1": synthesize},
        domain_name="高等数学",
        scope_hint="本科",
        language="zh",
        run_id="067-artifact",
    )

    path = write_run_artifact(result, tmp_path / "runs")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert path.parent == tmp_path / "runs"
    assert payload["run_id"] == "067-artifact"
    (first_call,) = payload["llm_calls"]
    assert first_call["seq"] == 1
    assert first_call["step_id"] == "domain_synthesis"
    assert first_call["prompt_template"] == "domain-explore/domain_synthesis@v1"
    assert first_call["expected_prompt_template"] == "domain-explore/domain_synthesis@v1"
    assert first_call["request_chars"] == 40
    assert first_call["evidence_source_ids"] == ["wiki-01", "mit-01"]
    assert first_call["estimated_evidence_tokens"] == 1234
    assert [entry["step_id"] for entry in payload["trace"]] == [
        "wiki_lookup",
        "university_lookup",
        "domain_synthesis",
    ]
    assert payload["trace"][0]["marker"] == "fixture:wiki-01"
