"""prompt-lab dry-run API 契约测试（QED-043 评估模式）。

守护面：POST /api/v1/prompt-explores/dry-run 同步执行领域探索管线，
不走正式流程（不写 qt_prompt_runs、不入任务队列），唯一痕迹是
qed_llm_calls 的 LLM 日志（direct 模式由 LlmClient 写入）。
零公网：DomainPipeline 经 monkeypatch 替换为固定响应 fake。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from qed_tracker.api import main as api_main
from qed_tracker.config import load_settings
from qed_tracker.prompt_lab.pipeline import NameConfirmationRequired, PipelineError


class FakePipeline:
    """固定报告 fake；记录构造 kwargs 与最近一次 explore 入参。"""

    last_instance: FakePipeline | None = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.step_calls = [
            {"step": "domain", "template_id": "domain-explore/domain@v1", "duration_ms": 5},
            {"step": "courses", "template_id": "domain-explore/courses@v3", "duration_ms": 6},
            {"step": "path", "template_id": "domain-explore/path@v3", "duration_ms": 7},
        ]
        self.last_call: dict = {}
        FakePipeline.last_instance = self

    def explore(self, domain_name, *, scope_hint="", mode="direct", ref_text="", ref_doc_path="",
                confirm_name_override=""):
        self.last_call = {
            "domain_name": domain_name,
            "scope_hint": scope_hint,
            "mode": mode,
            "ref_text": ref_text,
            "ref_doc_path": ref_doc_path,
            "confirm_name_override": confirm_name_override,
        }
        if mode == "doc" and not Path(ref_doc_path).is_file():
            raise PipelineError(f"探索文档无法读取：{ref_doc_path}", code="INVALID_PARAMS")
        if mode == "text" and not ref_text.strip():
            raise PipelineError("mode=text 必须提供非空 ref_text", code="INVALID_PARAMS")
        return {
            "domain": {"final_name": domain_name, "description": "d", "level": "本科-硕士",
                       "classic_tracks": [], "entry_requirements": []},
            "courses": [],
            "path": {"notes": "", "edges": [], "graph_td": "graph TD\n"},
        }

    def close(self):
        self.closed = True


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "llm_api_key", lambda: "k")
    monkeypatch.setattr(api_main, "DomainPipeline", FakePipeline)
    FakePipeline.last_instance = None
    app = api_main.create_app(load_settings(data_root=tmp_path))
    with TestClient(app) as test_client:
        yield test_client


def test_dry_run_returns_report_step_calls_and_closes(client) -> None:
    response = client.post(
        "/api/v1/prompt-explores/dry-run",
        json={"domain_name": "高等数学", "scope_hint": "本科-硕士", "mode": "direct"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["confirmation_required"] is False
    assert body["report"]["domain"]["final_name"] == "高等数学"
    assert [c["template_id"] for c in body["calls"]][0] == "domain-explore/domain@v1"
    instance = FakePipeline.last_instance
    assert instance is not None
    assert instance.kwargs["api_key"] == "k"
    assert instance.last_call == {
        "domain_name": "高等数学", "scope_hint": "本科-硕士",
        "mode": "direct", "ref_text": "", "ref_doc_path": "",
        "confirm_name_override": "",
    }
    assert getattr(instance, "closed", False)


def test_dry_run_returns_confirmation_marker_when_name_needs_review(tmp_path, monkeypatch) -> None:
    class ConfirmPipeline(FakePipeline):
        def explore(self, domain_name, **kw):
            self.last_call = {"domain_name": domain_name}
            raise NameConfirmationRequired(
                {"valid": False, "reason": "疑似拼写错误", "suggested_name": "高等数学"}
            )

    monkeypatch.setattr(api_main, "llm_api_key", lambda: "k")
    monkeypatch.setattr(api_main, "DomainPipeline", ConfirmPipeline)
    app = api_main.create_app(load_settings(data_root=tmp_path))
    with TestClient(app) as test_client:
        response = test_client.post("/api/v1/prompt-explores/dry-run", json={"domain_name": "高凳数学"})
    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["confirmation_required"] is True
    assert body["name_check"]["suggested_name"] == "高等数学"
    assert "report" not in body


def test_dry_run_scope_hint_defaults_when_blank(client) -> None:
    client.post("/api/v1/prompt-explores/dry-run", json={"domain_name": "物理学", "mode": "direct"})
    instance = FakePipeline.last_instance
    assert instance is not None
    assert instance.last_call["scope_hint"]  # 回退到默认范围说明（非空）


def test_dry_run_requires_domain_name(client) -> None:
    response = client.post("/api/v1/prompt-explores/dry-run", json={})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_PARAMS"


def test_dry_run_rejects_unknown_mode(client) -> None:
    response = client.post(
        "/api/v1/prompt-explores/dry-run", json={"domain_name": "x", "mode": "web"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_PARAMS"


def test_dry_run_doc_mode_missing_file_maps_invalid_params(client, tmp_path) -> None:
    missing = str(tmp_path / "nope.txt")
    response = client.post(
        "/api/v1/prompt-explores/dry-run",
        json={"domain_name": "高等数学", "mode": "doc", "ref_doc_path": missing},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_PARAMS"
    assert getattr(FakePipeline.last_instance, "closed", False)  # 失败也要关闭连接


def test_dry_run_passes_confirm_name_override(client) -> None:
    client.post(
        "/api/v1/prompt-explores/dry-run",
        json={"domain_name": "高等数学", "confirm_name_override": "高等数学"},
    )
    instance = FakePipeline.last_instance
    assert instance is not None
    assert instance.last_call.get("domain_name") == "高等数学"


def test_dry_run_llm_failure_maps_502(tmp_path, monkeypatch) -> None:
    class BoomPipeline(FakePipeline):
        def explore(self, domain_name, **kw):
            raise PipelineError("模型网络请求失败", code="LLM_UNAVAILABLE")

    monkeypatch.setattr(api_main, "llm_api_key", lambda: "k")
    monkeypatch.setattr(api_main, "DomainPipeline", BoomPipeline)
    app = api_main.create_app(load_settings(data_root=tmp_path))
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/prompt-explores/dry-run", json={"domain_name": "高等数学"}
        )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LLM_UNAVAILABLE"


def test_dry_run_unconfigured_key_maps_409(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(api_main, "llm_api_key", lambda: "")
    app = api_main.create_app(load_settings(data_root=tmp_path))
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/prompt-explores/dry-run", json={"domain_name": "高等数学"}
        )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "LLM_UNAVAILABLE"
