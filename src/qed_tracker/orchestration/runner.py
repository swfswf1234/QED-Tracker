"""Ordered step executor for the isolated QED-067 trial pipeline.

Tool steps are injected handlers that only gather read-only evidence; every LLM
call is observed on the wire (not assumed from configuration) so the recorded
`prompt_template` values can be read back from `qed_llm_calls` in the same order
— the gateway payload has no task/step passthrough (REQ pending to QED-Engine).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from qed_tracker.orchestration.config import PipelineSpec
from qed_tracker.orchestration.evidence import EvidencePacker, EvidenceSource, PackedEvidence
from qed_tracker.orchestration.pipeline import OrchestrationError, PhaseResult

_TEMPLATE_REF = re.compile(r"^(?P<name>[a-z0-9-]+)@v(?P<version>[1-9][0-9]*)$")


@dataclass(frozen=True)
class ToolOutcome:
    sources: tuple[EvidenceSource, ...] = ()
    marker: str = "in-process"
    detail: dict[str, Any] = field(default_factory=dict)


class RecordingClient:
    """Wraps the shared LlmClient and records the template of every call that really went out."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self.calls: list[dict[str, Any]] = []

    def complete(self, messages: list[dict[str, str]], *, prompt_template: str = "") -> str:
        content = self._client.complete(messages, prompt_template=prompt_template)
        self.calls.append(
            {
                "seq": len(self.calls) + 1,
                "prompt_template": prompt_template,
                "request_chars": sum(len(message.get("content", "")) for message in messages),
                "response_chars": len(content),
            }
        )
        return content


@dataclass
class RunState:
    domain_name: str
    scope_hint: str
    language: str
    phase: str
    client: RecordingClient
    collected: list[EvidenceSource] = field(default_factory=list)
    packed: PackedEvidence | None = None


@dataclass(frozen=True)
class StepTrace:
    seq: int
    step_id: str
    kind: str
    tool: str | None
    template_ref: str | None
    source_ids: tuple[str, ...]
    marker: str
    observed_prompt_templates: tuple[str, ...]
    detail: dict[str, Any]


@dataclass(frozen=True)
class RunResult:
    run_id: str
    pipeline: str
    task: str
    trace: tuple[StepTrace, ...]
    phase_results: Mapping[str, PhaseResult]
    packed: PackedEvidence | None
    llm_calls: tuple[dict[str, Any], ...] = ()


def run_pipeline(
    *,
    client: Any,
    pipeline: PipelineSpec,
    tools: Mapping[str, Callable[[RunState], ToolOutcome]],
    synthesis: Mapping[str, Callable[[RunState, str], PhaseResult]],
    domain_name: str,
    scope_hint: str,
    language: str,
    phase: str = "domain",
    run_id: str | None = None,
    packer: EvidencePacker | None = None,
    requested_families: Sequence[str] = ("wikipedia", "MIT", "Stanford", "Tsinghua"),
) -> RunResult:
    """Execute declared steps in order; nothing here writes facts or touches the network."""
    executor = packer or EvidencePacker()
    recorder = client if isinstance(client, RecordingClient) else RecordingClient(client)
    state = RunState(
        domain_name=domain_name, scope_hint=scope_hint, language=language, phase=phase, client=recorder
    )
    traces: list[StepTrace] = []
    phases: dict[str, PhaseResult] = {}

    def require_handler(name: str, registry: Mapping[str, object], message: str) -> Callable:
        handler = registry.get(name)
        if handler is None:
            raise OrchestrationError(f"{message}：{name}")
        return handler

    # Fail before the first model call when the declared flow cannot be honoured.
    for step in pipeline.steps:
        if step.kind == "tool":
            require_handler(step.tool or "", tools, "未注册工具")
        else:
            require_handler(_template_key(step), synthesis, "未注册步骤处理")

    for step in pipeline.steps:
        if step.kind == "tool":
            outcome = require_handler(step.tool or "", tools, "未注册工具")(state)
            state.collected.extend(outcome.sources)
            traces.append(
                StepTrace(
                    seq=len(traces) + 1,
                    step_id=step.step_id,
                    kind="tool",
                    tool=step.tool,
                    template_ref=None,
                    source_ids=tuple(source.source_id for source in outcome.sources),
                    marker=outcome.marker,
                    observed_prompt_templates=(),
                    detail=outcome.detail,
                )
            )
            continue

        template_key = _template_key(step)
        state.packed = executor.pack(
            domain_name=state.domain_name,
            scope_hint=state.scope_hint,
            language=state.language,
            phase=state.phase,
            sources=state.collected,
            requested_families=tuple(requested_families),
        )
        expected_ref = _expected_template_ref(pipeline, step)
        before = len(recorder.calls)
        phase_result = require_handler(template_key, synthesis, "未注册步骤处理")(state, expected_ref)
        observed = tuple(call["prompt_template"] for call in recorder.calls[before:])
        if not observed:
            raise OrchestrationError(f"llm step 未产生任何模型调用：{step.step_id}")
        phases[step.step_id] = phase_result
        traces.append(
            StepTrace(
                seq=len(traces) + 1,
                step_id=step.step_id,
                kind="llm",
                tool=None,
                template_ref=expected_ref,
                source_ids=tuple(source["source_id"] for source in state.packed.bundle["sources"]),
                marker="llm",
                observed_prompt_templates=observed,
                detail={
                    "estimated_evidence_tokens": phase_result.trace.get(
                        "estimated_evidence_tokens", state.packed.estimated_tokens
                    ),
                    "citations": phase_result.trace.get("evidence_refs", []),
                },
            )
        )

    return RunResult(
        run_id=run_id or uuid4().hex,
        pipeline=pipeline.name,
        task=pipeline.task,
        trace=tuple(traces),
        phase_results=phases,
        packed=state.packed,
        llm_calls=tuple(recorder.calls),
    )


def _template_key(step: object) -> str:
    template = getattr(step, "template", None) or ""
    if not _TEMPLATE_REF.fullmatch(template):
        raise OrchestrationError(
            f"llm step 模板编号须为 {{name}}@v{{n}}：{getattr(step, 'step_id', '?')}"
        )
    return template


def _expected_template_ref(pipeline: PipelineSpec, step: object) -> str:
    match = _TEMPLATE_REF.fullmatch(getattr(step, "template", None) or "")
    if match is None:
        raise OrchestrationError(f"模板编号无效：{getattr(step, 'template', None)}")
    return f"{pipeline.task}/{step.step_id}@v{match.group('version')}"


def write_run_artifact(result: RunResult, directory: Path) -> Path:
    """Persist the ordered trace plus per-LLM-step readback keys as a review artifact."""
    directory.mkdir(parents=True, exist_ok=True)
    llm_calls = [
        {
            "seq": call["seq"],
            "step_id": next(
                (
                    entry.step_id
                    for entry in result.trace
                    if entry.kind == "llm"
                    and call["prompt_template"] in entry.observed_prompt_templates
                ),
                "",
            ),
            "prompt_template": call["prompt_template"],
            "expected_prompt_template": next(
                (
                    entry.template_ref
                    for entry in result.trace
                    if entry.kind == "llm"
                    and call["prompt_template"] in entry.observed_prompt_templates
                ),
                "",
            ),
            "request_chars": call["request_chars"],
            "response_chars": call["response_chars"],
            "evidence_source_ids": next(
                (
                    list(entry.source_ids)
                    for entry in result.trace
                    if entry.kind == "llm"
                    and call["prompt_template"] in entry.observed_prompt_templates
                ),
                [],
            ),
            "estimated_evidence_tokens": next(
                (
                    entry.detail.get("estimated_evidence_tokens")
                    for entry in result.trace
                    if entry.kind == "llm"
                    and call["prompt_template"] in entry.observed_prompt_templates
                ),
                None,
            ),
        }
        for call in result.llm_calls
    ]
    payload = {
        "run_id": result.run_id,
        "pipeline": result.pipeline,
        "task": result.task,
        "llm_calls": llm_calls,
        "trace": [{**asdict(entry), "source_ids": list(entry.source_ids), "observed_prompt_templates": list(entry.observed_prompt_templates)} for entry in result.trace],
        "report": {step_id: phase.report for step_id, phase in result.phase_results.items()},
    }
    path = directory / f"{result.run_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
