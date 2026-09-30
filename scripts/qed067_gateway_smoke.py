"""QED-067-1 网关端到端冒烟：真实调用 8900 网关跑通领域/课程两轮编排链。

目的（计划 `docs/plans/2026-09-14-local-llm-langchain.md` 工作项 1）：
1. 确认 `qed-engine` 模式经 8900 调用成功，且 `qed_llm_calls` 留痕可按顺序回读；
2. 确认网关载荷实际支持的留痕字段（当前无 `task/step` 透传，见计划「067-1 结论」）。

工具步取证为**冻结 fixture**（`orchestration/fixtures/067-smoke-evidence.json`），
真实只读抓取属 067-5；本脚本不写库、不下载、不改根仓库配置。

用法：
    conda run -n qed_env python scripts/qed067_gateway_smoke.py --preflight-only
    conda run -n qed_env python scripts/qed067_gateway_smoke.py --rounds both

退出码：0 成功；1 运行失败（网关/模型/契约错误）；2 参数错误；3 前置条件不满足（未真跑）。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
# Windows 控制台默认 GBK，会把中文报告行改成乱码；冒烟结果必须可直读。
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from qed_tracker.config import load_settings  # noqa: E402
from qed_tracker.llm_client import LlmClient  # noqa: E402
from qed_tracker.orchestration import pipeline as phases  # noqa: E402
from qed_tracker.orchestration.config import PipelineRegistry, ToolCatalog, load_pipeline, load_skill  # noqa: E402
from qed_tracker.orchestration.evidence import EvidencePacker, EvidenceSource  # noqa: E402
from qed_tracker.orchestration.runner import ToolOutcome, run_pipeline, write_run_artifact  # noqa: E402

PACKAGES = Path(ROOT) / "src" / "qed_tracker" / "orchestration"
FIXTURE = PACKAGES / "fixtures" / "067-smoke-evidence.json"
PIPELINE_YAML = PACKAGES / "pipelines" / "domain-exploration.yaml"
SKILL_YAML = PACKAGES / "skills" / "domain-exploration.yaml"
LOCAL_SLOT_MODEL = "qwen/qwen3.5-9b"


def _get(client: httpx.Client, url: str, path: str) -> dict[str, Any]:
    response = client.get(f"{url}{path}")
    response.raise_for_status()
    return response.json()


def preflight(gateway: httpx.Client, url: str, settings: Any, *, allow_nonlocal: bool) -> list[str]:
    """Print the live gateway/config snapshot and return blocking reasons."""
    blocks: list[str] = []
    health = _get(gateway, url, "/api/v1/health")
    default = _get(gateway, url, "/api/v1/config/models").get("default", {})
    slot = _get(gateway, url, "/api/v1/models/qwen")
    probe = _get(gateway, url, "/api/v1/monitor/qwen")

    print("— 网关探活 ---------------------------------------------------")
    print(f"  health            : {health.get('status')} ({health.get('service')})")
    print(f"  文字槽位 source    : {slot.get('source')} / model={slot.get('model')} / ready={slot.get('ready')}")
    print(f"  默认通道 default   : {default.get('model')} (provider={default.get('provider')})")
    print(f"  LM Studio 直连探测 : reachable={probe.get('reachable')} reason={probe.get('reason') or '-'}")
    print(f"  本仓生效模式      : api_select={settings.api_select} model={settings.llm_model}")
    print(f"  网关地址          : {settings.llm_gateway_url}")

    if settings.api_select != "qed-engine":
        blocks.append(
            f"本仓 QED_API_SELECT={settings.api_select}，未经 8900 网关；067-1 须 qed-engine 模式"
        )
    if slot.get("source") != "local":
        blocks.append(
            f"网关文字槽位 source={slot.get('source')}，当前不会调用本地 qwen3.5 9B"
        )
    if not slot.get("ready"):
        blocks.append(f"本地槽位未就绪：{slot.get('health_reason') or slot.get('availability')}")
    if blocks and not allow_nonlocal:
        print("\n  结论：前置条件不满足（067-1 成功标准要求真实本地模型）。")
    return blocks


def _fixture_sources() -> tuple[EvidenceSource, ...]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return tuple(
        EvidenceSource(
            source_id=item["source_id"],
            family=item["family"],
            institution=item.get("institution"),
            title=item["title"],
            canonical_url=item["canonical_url"],
            retrieved_at=item["retrieved_at"],
            excerpt=item["excerpt"],
            locator=item["locator"],
            claims=tuple(item["claims"]),
            priority=item["priority"],
        )
        for item in payload["sources"]
    )


def _readback(
    gateway: httpx.Client, url: str, *, since: str, prefix: str
) -> list[dict[str, Any]]:
    """Pull this run's rows out of qed_llm_calls through the gateway query endpoint.

    过滤只按日期（网关 `start` 仅收 YYYY-MM-DD），故按 UTC 当日取回后本地收敛到
    本次运行窗口；失败的轮次同样留痕，所以不能只认成功轮观测到的模板名。
    """
    query = urllib.parse.urlencode({"start": since[:10], "size": 200})
    body = _get(gateway, url, f"/api/v1/llm/calls?{query}")
    rows = [
        item
        for item in body.get("items", [])
        if str(item.get("created_at", "")) >= since
        and str(item.get("prompt_template") or "").startswith(prefix)
    ]
    return sorted(rows, key=lambda item: int(item["id"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--domain", default="高等数学")
    parser.add_argument("--scope", default="本科，面向非数学专业")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--rounds", choices=("domain", "both"), default="both")
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="任一轮失败即中止（默认继续跑完，让每轮都在 qed_llm_calls 留下顺序行）",
    )
    parser.add_argument("--preflight-only", action="store_true", help="只探活，不发模型调用")
    parser.add_argument("--allow-nonlocal", action="store_true", help="允许在非本地通道下试跑（不算 067-1 达成）")
    parser.add_argument(
        "--template-prefix",
        default="domain-explore",
        help="回读 qed_llm_calls 时认定本次运行的 prompt_template 前缀",
    )
    parser.add_argument("--artifact-dir", default=str(ROOT / "logs" / "067-smoke"))
    args = parser.parse_args(argv)

    settings = load_settings()
    run_started_at = datetime.now(UTC).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
    catalog = ToolCatalog({"wikipedia.search": {"read_only": True}, "university.search": {"read_only": True}})
    pipeline = load_pipeline(PIPELINE_YAML, catalog=catalog)
    skill = load_skill(SKILL_YAML, pipeline=pipeline, catalog=catalog)
    registry = PipelineRegistry()
    registry.register(pipeline)

    sources = _fixture_sources()
    wiki_sources = tuple(item for item in sources if item.family == "wikipedia")
    university_sources = tuple(item for item in sources if item.family == "university")

    failures: list[str] = []
    templates: list[str] = []

    with httpx.Client(timeout=httpx.Timeout(600.0, connect=10.0), trust_env=False) as gateway:
        blocks = preflight(gateway, settings.llm_gateway_url, settings, allow_nonlocal=args.allow_nonlocal)
        if blocks:
            print("\n  阻塞项（须由根仓库/机器侧处理，本脚本不改根 .env）：")
            for reason in blocks:
                print(f"   - {reason}")
        if args.preflight_only:
            return 3 if blocks else 0
        if blocks:
            print("\n  未发起模型调用。解除阻塞后重跑，或加 --allow-nonlocal 强行试跑。")
            return 3

        client = LlmClient(
            api_select=settings.api_select,
            model=settings.llm_model,
            gateway_url=settings.llm_gateway_url,
            timeout=600.0,
            call_budget=4,
            max_tokens=2048,
        )
        packer = EvidencePacker(max_tokens=min(skill.max_payload_tokens, 5388))
        rounds: list[dict[str, Any]] = []
        context: dict[str, Any] = {"domain_info": {}}

        def wiki(_state: Any) -> ToolOutcome:
            return ToolOutcome(sources=wiki_sources, marker=f"fixture:{FIXTURE.name}")

        def university(_state: Any) -> ToolOutcome:
            return ToolOutcome(sources=university_sources, marker=f"fixture:{FIXTURE.name}")

        for phase in ("domain", "courses")[: 1 if args.rounds == "domain" else 2]:

            def synthesize(state: Any, _expected_ref: str) -> Any:
                if state.phase == "domain":
                    return phases.run_domain_phase(state.client, state.packed)
                return phases.run_courses_phase(state.client, state.packed, domain_info=context["domain_info"])

            try:
                result = run_pipeline(
                    client=client,
                    pipeline=pipeline,
                    tools={"wikipedia.search": wiki, "university.search": university},
                    synthesis={"domain-agentic@v1": synthesize, "courses-agentic@v1": synthesize},
                    domain_name=args.domain,
                    scope_hint=args.scope,
                    language=args.language,
                    phase=phase,
                    packer=packer,
                )
            except Exception as exc:  # noqa: BLE001 - 冒烟须把失败原样交给操作者
                failures.append(f"{phase}: {type(exc).__name__}: {exc}")
                print(f"\n  阶段 {phase} 失败：{type(exc).__name__}: {exc}")
                if args.stop_on_error:
                    break
                print("  继续下一轮（本步失败已记入留痕与产物；跨步顺序仍可在 qed_llm_calls 回读）")
                continue
            rounds.append(result)
            templates += [call["prompt_template"] for call in result.llm_calls]
            if phase == "domain":
                context["domain_info"] = result.phase_results["domain_synthesis"].report["domain"]

        print("\n— 执行序（本脚本侧）------------------------------------------------")
        for result in rounds:
            for entry in result.trace:
                print(
                    f"  seq={entry.seq:<2} {entry.step_id:<18} kind={entry.kind:<4} "
                    f"marker={entry.marker:<28} evidence={','.join(entry.source_ids) or '-'}"
                )
            for call in result.llm_calls:
                print(
                    f"    LLM #{call['seq']} prompt_template={call['prompt_template']} "
                    f"req_chars={call['request_chars']} resp_chars={call['response_chars']}"
                )

        print("\n— qed_llm_calls 回读（经 GET /api/v1/llm/calls）-------------------")
        if not templates:
            print("  注意：本轮编排未走完，以下仅列已落到网关的调用行（失败同样留痕）。")
        rows = _readback(
            gateway,
            settings.llm_gateway_url,
            since=run_started_at,
            prefix=args.template_prefix,
        )
        if not rows:
            print("  未回读到任何行。")
        for row in rows:
            print(
                f"  id={row['id']:<6} {row['created_at']} service={row['service']:<11} mode={row['mode']:<5} "
                f"model={row['model']:<26} {row['status']:<7} {row['duration_ms']}ms "
                f"template={row['prompt_template']} task={row.get('task') or 'NULL'} step={row.get('step') or 'NULL'}"
            )
        print(f"\n  共回读 {len(rows)} 行；id 升序即调用顺序。")
        print("  人工核对 URL：")
        for template in templates or [args.template_prefix]:
            query = urllib.parse.urlencode(
                {"prompt_template": template, "start": run_started_at[:10]}
            )
            print(f"    {settings.llm_gateway_url}/api/v1/llm/calls?{query}")

    artifact_dir = Path(args.artifact_dir)
    paths = []
    for result in rounds:
        paths.append(write_run_artifact(result, artifact_dir))
    print("\n— 运行产物 ------------------------------------------------------")
    for path in paths:
        print(f"  {path}")
    if failures:
        print("  失败记录：" + "；".join(failures))
        return 1
    return 0 if rounds else 1


if __name__ == "__main__":
    raise SystemExit(main())
