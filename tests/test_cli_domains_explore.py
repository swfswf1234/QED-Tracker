"""CLI `domains explore` 领域探索命令测试（QED-050-A，2026-09-03）。

fake httpx.post 模拟 8901 dry-run 端点三态：报告成功 / confirmation_required /
服务不可达与 HTTP 错误——断言 CLI 输出与退出码契约。
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from qed_tracker.cli import _domains_explore
from qed_tracker.config import load_settings

_REPORT = {
    "dry_run": True,
    "confirmation_required": False,
    "report": {
        "domain": {"final_name": "高等数学", "description": "d", "level": "本科",
                   "stages": ["基础", "主干", "分支", "前沿"], "classic_tracks": [],
                   "entry_requirements": "", "prior_knowledge": ""},
        "courses": [{"course_id": "math_analysis", "name": "数学分析", "aliases": [],
                     "track": "分析", "summary": "s", "university_basis": [],
                     "stage": "基础", "prerequisites": []}],
        "path": {"notes": "", "edges": [], "graph_td": "graph TD\n"},
    },
    "calls": [{"step": "domain", "template_id": "domain-explore/domain@v4", "duration_ms": 5},
              {"step": "courses", "template_id": "domain-explore/courses@v8", "duration_ms": 6}],
}


def _args(**overrides) -> SimpleNamespace:
    values = dict(name="高等数学", scope="", mode="direct", ref_text="", ref_doc_path="",
                  confirm_name="", tracker_url="http://127.0.0.1:8901", timeout=600.0, json=True)
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def settings(tmp_path):
    return load_settings(data_root=tmp_path)


def test_domains_explore_prints_report_and_calls(settings, monkeypatch, capsys) -> None:
    calls: list[tuple[str, dict]] = []

    def handler(url: str, json: dict | None = None, **_kw) -> SimpleNamespace:  # noqa: A002
        calls.append((url, json or {}))
        return SimpleNamespace(status_code=200, json=lambda: _REPORT, text="")

    monkeypatch.setattr(httpx, "post", handler)
    code = _domains_explore(_args(), settings)
    assert code == 0
    url, payload = calls[0]
    assert url.endswith("/api/v1/prompt-explores/dry-run")
    assert payload["domain_name"] == "高等数学"
    assert payload["mode"] == "direct"
    assert payload["confirm_name_override"] == ""
    out = capsys.readouterr().out
    assert "domain-explore/courses@v8" in out  # calls 明细
    parsed = __import__("json").loads(out)
    assert parsed["report"]["domain"]["final_name"] == "高等数学"


def test_domains_explore_passes_scope_and_confirm_name(settings, monkeypatch, capsys) -> None:
    captured: dict = {}

    def handler(url: str, json: dict | None = None, **_kw) -> SimpleNamespace:  # noqa: A002
        captured["payload"] = json or {}
        return SimpleNamespace(status_code=200, json=lambda: _REPORT, text="")

    monkeypatch.setattr(httpx, "post", handler)
    code = _domains_explore(_args(scope="本科基础课", confirm_name="高等数学"), settings)
    assert code == 0
    assert captured["payload"]["scope_hint"] == "本科基础课"
    assert captured["payload"]["confirm_name_override"] == "高等数学"


def test_domains_explore_confirmation_required(settings, monkeypatch, capsys) -> None:
    body = {"dry_run": True, "confirmation_required": True,
            "name_check": {"valid": False, "reason": "疑似拼写错误", "suggested_name": "高等数学"}}

    def handler(url: str, json: dict | None = None, **_kw) -> SimpleNamespace:  # noqa: A002
        return SimpleNamespace(status_code=200, json=lambda: body, text="")

    monkeypatch.setattr(httpx, "post", handler)
    code = _domains_explore(_args(json=False), settings)
    assert code == 2
    out = capsys.readouterr().out
    assert "高等数学" in out  # suggested_name 提示
    assert "--confirm-name" in out  # 重跑指引


def test_domains_explore_http_error_maps_exit_2(settings, monkeypatch, capsys) -> None:
    def handler(url: str, json: dict | None = None, **_kw) -> SimpleNamespace:  # noqa: A002
        return SimpleNamespace(status_code=502, json=lambda: {"detail": {"code": "LLM_FAILURE", "message": "模型失败"}},
                               text="")

    monkeypatch.setattr(httpx, "post", handler)
    code = _domains_explore(_args(), settings)
    assert code == 2


def test_domains_explore_unreachable_maps_exit_6(settings, monkeypatch) -> None:
    def handler(url: str, json: dict | None = None, **_kw) -> SimpleNamespace:  # noqa: A002
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", handler)
    code = _domains_explore(_args(), settings)
    assert code == 6
