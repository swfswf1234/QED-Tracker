"""Declarative pipeline configuration and read-only tool validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigurationError(ValueError):
    """Pipeline configuration cannot be safely registered."""


@dataclass(frozen=True)
class PipelineStep:
    step_id: str
    kind: str
    tool: str | None = None
    template: str | None = None
    tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class PipelineSpec:
    name: str
    version: int
    task: str
    steps: tuple[PipelineStep, ...]


class ToolCatalog:
    """The server-owned catalog of tools a pipeline may reference."""

    def __init__(self, tools: dict[str, dict[str, Any]]) -> None:
        self._tools = {name: dict(spec) for name, spec in tools.items()}

    def require_read_only(self, name: str) -> None:
        spec = self._tools.get(name)
        if spec is None:
            raise ConfigurationError(f"未知工具：{name}")
        if not spec.get("read_only", False):
            raise ConfigurationError(f"工具必须是只读：{name}")


class PipelineRegistry:
    """In-memory pipeline registry that prevents a lower revision replacing a reviewed one."""

    def __init__(self) -> None:
        self._pipelines: dict[str, PipelineSpec] = {}

    def register(self, pipeline: PipelineSpec) -> None:
        current = self._pipelines.get(pipeline.name)
        if current is not None and pipeline.version < current.version:
            raise ConfigurationError(f"拒绝低版本覆盖：{pipeline.name}")
        self._pipelines[pipeline.name] = pipeline


@dataclass(frozen=True)
class SkillSpec:
    name: str
    pipeline: str
    tools: tuple[str, ...]
    network: bool
    max_payload_tokens: int


def load_pipeline(path: Path, *, catalog: ToolCatalog) -> PipelineSpec:
    """Load one YAML pipeline and reject any tool outside the server catalog."""
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"YAML 无效：{path}") from exc
    if not isinstance(value, dict):
        raise ConfigurationError("pipeline 顶层必须是对象")

    allowed = {"name", "version", "task", "steps"}
    unknown = set(value) - allowed
    if unknown:
        raise ConfigurationError(f"pipeline 存在未知字段：{', '.join(sorted(unknown))}")

    name, version, task, raw_steps = (value.get(key) for key in ("name", "version", "task", "steps"))
    if not isinstance(name, str) or not name or not isinstance(version, int) or version < 1:
        raise ConfigurationError("pipeline name/version 无效")
    if not isinstance(task, str) or not task or not isinstance(raw_steps, list) or not raw_steps:
        raise ConfigurationError("pipeline task/steps 无效")

    steps: list[PipelineStep] = []
    seen_ids: set[str] = set()
    for raw in raw_steps:
        if not isinstance(raw, dict):
            raise ConfigurationError("step 必须是对象")
        step_id, kind = raw.get("id"), raw.get("kind")
        if not isinstance(step_id, str) or not step_id or step_id in seen_ids:
            raise ConfigurationError("step id 必须唯一且非空")
        if kind not in {"tool", "llm"}:
            raise ConfigurationError(f"step kind 无效：{step_id}")
        allowed_step_fields = {"id", "kind", "tool"} if kind == "tool" else {"id", "kind", "template", "tools"}
        unknown_step_fields = set(raw) - allowed_step_fields
        if unknown_step_fields:
            raise ConfigurationError(f"step 存在未知字段：{', '.join(sorted(unknown_step_fields))}")
        seen_ids.add(step_id)

        tool = raw.get("tool")
        template = raw.get("template")
        tools = raw.get("tools", [])
        if kind == "tool":
            if not isinstance(tool, str) or not tool:
                raise ConfigurationError(f"tool step 缺少 tool：{step_id}")
            catalog.require_read_only(tool)
        elif not isinstance(template, str) or not template:
            raise ConfigurationError(f"llm step 缺少 template：{step_id}")
        if not isinstance(tools, list) or not all(isinstance(item, str) for item in tools):
            raise ConfigurationError(f"step tools 无效：{step_id}")
        for tool_name in tools:
            catalog.require_read_only(tool_name)
        steps.append(PipelineStep(step_id, kind, tool, template, tuple(tools)))

    return PipelineSpec(name=name, version=version, task=task, steps=tuple(steps))


def load_skill(path: Path, *, pipeline: PipelineSpec, catalog: ToolCatalog) -> SkillSpec:
    """Load a small skill manifest without expanding the pipeline's approved tool surface."""
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"YAML 无效：{path}") from exc
    if not isinstance(value, dict):
        raise ConfigurationError("skill 顶层必须是对象")
    unknown = set(value) - {"name", "pipeline", "requires", "max_payload_tokens"}
    if unknown:
        raise ConfigurationError(f"skill 存在未知字段：{', '.join(sorted(unknown))}")

    name, pipeline_name, requires, max_payload_tokens = (
        value.get(key) for key in ("name", "pipeline", "requires", "max_payload_tokens")
    )
    if not isinstance(name, str) or not name or pipeline_name != pipeline.name:
        raise ConfigurationError("skill name/pipeline 无效")
    if not isinstance(requires, dict) or not isinstance(max_payload_tokens, int) or max_payload_tokens < 1:
        raise ConfigurationError("skill requires/max_payload_tokens 无效")
    unknown_requires = set(requires) - {"tools", "network"}
    if unknown_requires:
        raise ConfigurationError(f"skill requires 存在未知字段：{', '.join(sorted(unknown_requires))}")
    tools = requires.get("tools", [])
    network = requires.get("network", False)
    if not isinstance(tools, list) or not all(isinstance(item, str) for item in tools) or not isinstance(network, bool):
        raise ConfigurationError("skill requires 无效")

    approved_tools = {
        tool_name
        for step in pipeline.steps
        for tool_name in ((step.tool,) if step.tool else ()) + step.tools
    }
    for tool_name in tools:
        catalog.require_read_only(tool_name)
        if tool_name not in approved_tools:
            raise ConfigurationError(f"工具未获 pipeline 批准：{tool_name}")
    return SkillSpec(name, pipeline_name, tuple(tools), network, max_payload_tokens)
