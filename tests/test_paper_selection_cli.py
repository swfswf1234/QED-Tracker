"""QED-068 B 步：论文 CLI 转 8901 HTTP 客户端（recommend / selections list|show|adopt）。

假 httpx（monkeypatch `httpx.post`/`httpx.get`）模拟 8901 端点与任务轮询，零公网零服务依赖。
`papers search/get`（单条手动直写通道）与 `papers profiles` 维持本地直调，不在此面。
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from qed_tracker import cli
from qed_tracker.cli import main
from qed_tracker.db.selection_repository import SelectionStoreError

SELECTION_ID = "sel-20260730T000000Z-12345678"


class FakeEngine:
    def __init__(self):
        self.disposed = False

    def dispose(self):
        self.disposed = True


def _report(status="ranked"):
    return {
        "selection_id": SELECTION_ID,
        "status": status,
        "created_at": "2026-07-30T00:00:00+00:00",
        "domain_id": "math-advanced",
        "recipe": "frontier",
        "profile": {"id": "domain-math-advanced"},
        "assessments": [
            {
                "rank": 1,
                "recommended": True,
                "score": 86,
                "candidate": {"title": "Series Convergence", "identifiers": {"arxiv": "2601.00001"}},
                "assessment": {"reason": "贴合目标"},
            }
        ],
        "recommendations": [1],
    }


class FakeHttp:
    """记录调用并按 URL 分派的 8901 假面。"""

    def __init__(self, *, task_result=None, report=None, selections=None, unreachable=False):
        self.calls: list[tuple[str, str, dict]] = []
        self.task_result = task_result if task_result is not None else {"selection_id": SELECTION_ID, "status": "ranked"}
        self.report = report if report is not None else _report()
        self.selections = selections if selections is not None else []
        self.unreachable = unreachable

    def install(self, monkeypatch) -> FakeHttp:
        monkeypatch.setattr(httpx, "post", self._post)
        monkeypatch.setattr(httpx, "get", self._get)
        return self

    @staticmethod
    def _response(payload, status_code=200):
        return SimpleNamespace(
            status_code=status_code, json=lambda: payload, text=str(payload),
            raise_for_status=lambda: None,
        )

    def _post(self, url, json=None, **_kw):
        self.calls.append(("POST", url, json or {}))
        if self.unreachable:
            raise httpx.ConnectError("connection refused")
        if url.endswith("/adopt"):
            return self._response({"task_id": "task-adopt"})
        return self._response({"task_id": "task-recommend"}, status_code=202)

    def _get(self, url, params=None, **_kw):
        self.calls.append(("GET", url, dict(params or {})))
        if self.unreachable:
            raise httpx.ConnectError("connection refused")
        if url.endswith("/api/v1/tasks/task-recommend"):
            return self._response({"status": "succeeded", "result": self.task_result, "error": ""})
        if url.endswith("/api/v1/tasks/task-adopt"):
            return self._response({"status": "succeeded", "result": self.task_result, "error": ""})
        if url.endswith(f"/api/v1/papers/selections/{SELECTION_ID}"):
            return self._response(self.report)
        if url.endswith("/api/v1/papers/selections"):
            return self._response({"selections": self.selections})
        return self._response({"code": "NOT_FOUND", "message": f"未知端点 {url}"}, status_code=404)


# ---------------- F3：报告持久化装配（本地 search/get 面仍需要） ----------------


def test_paper_cli_persists_reports_when_db_configured(monkeypatch, tmp_path):
    """F3：db_configured 时 `_paper_service` 必须把真实 session_factory 交给 PaperService，
    否则报告落 in-memory SQLite、进程退出即丢（qt_selections 恒空）。"""
    from dataclasses import replace

    from qed_tracker.config import load_settings

    settings = replace(load_settings(data_root=tmp_path), db_host="127.0.0.1", db_password="pw")
    assert settings.db_configured
    engine = FakeEngine()
    seen = {}

    def fake_session_factory(bound_engine):
        seen["engine"] = bound_engine
        return lambda: "session"

    monkeypatch.setattr("qed_tracker.db.engine.create_engine_for", lambda _settings: engine)
    monkeypatch.setattr("qed_tracker.db.engine.session_factory", fake_session_factory)

    service = cli._paper_service(settings)
    assert seen["engine"] is engine
    assert service.db_engine is engine
    assert service.domain_exists is not None
    assert service.selections._session_factory() == "session"
    service.close()
    assert engine.disposed


def test_paper_cli_keeps_memory_fallback_without_db(monkeypatch, tmp_path):
    """未配置数据库时保留 in-memory 回退（默认测试不写运行数据库），且不建引擎。"""
    from dataclasses import replace

    from qed_tracker.config import load_settings

    def _boom(_settings):
        raise AssertionError("db 未配置时不得建引擎")

    monkeypatch.setattr("qed_tracker.db.engine.create_engine_for", _boom)
    settings = replace(load_settings(data_root=tmp_path), db_password="")
    assert not settings.db_configured

    service = cli._paper_service(settings)
    assert service.db_engine is None
    assert service.domain_exists is None
    selection_id = type(service.selections).new_id()
    service.selections.save({"selection_id": selection_id, "status": "ranked"})
    assert service.selections.load(selection_id)["selection_id"] == selection_id
    service.close()


def test_selection_store_error_type_still_exported():
    """CLI 不再直调报告下载，但读面异常类型仍是 api/main 的 404 映射依据。"""
    assert issubclass(SelectionStoreError, RuntimeError)


# ---------------- recommend → HTTP ----------------


def test_recommend_submits_task_then_reads_report(tmp_path, monkeypatch, capsys):
    http = FakeHttp().install(monkeypatch)
    code = main([
        "--data-root", str(tmp_path), "--json", "papers", "recommend", "级数收敛判据",
        "--domain", "math-advanced", "--recipe", "frontier", "--url", "http://127.0.0.1:8901",
    ])
    assert code == 0
    posted = next(call for call in http.calls if call[0] == "POST")
    assert posted[1] == "http://127.0.0.1:8901/api/v1/papers/recommend"
    assert posted[2]["domain_id"] == "math-advanced"
    assert posted[2]["recipe"] == "frontier"
    assert posted[2]["goal"] == "级数收敛判据"
    assert "top" not in posted[2] and "limit" not in posted[2]
    assert ("GET", f"http://127.0.0.1:8901/api/v1/papers/selections/{SELECTION_ID}", {}) in http.calls
    assert SELECTION_ID in capsys.readouterr().out


def test_recommend_passes_explicit_budget_overrides(tmp_path, monkeypatch):
    """缺省量（top/limit/years_limit）由 8901 配方决定，CLI 只透传显式给出的值。"""
    http = FakeHttp().install(monkeypatch)
    code = main([
        "--data-root", str(tmp_path), "papers", "recommend", "goal",
        "--domain", "math-advanced", "--recipe", "frontier", "--top", "3", "--years-limit", "1",
        "--url", "http://127.0.0.1:8901",
    ])
    assert code == 0
    posted = next(call for call in http.calls if call[0] == "POST")
    assert (posted[2]["top"], posted[2]["years_limit"]) == (3, 1)
    assert "limit" not in posted[2]


def test_recommend_without_domain_never_calls_service(tmp_path, monkeypatch):
    """⑤′：CLI 侧同样要求 --domain，且不发请求（论文没有默认桶）。"""
    http = FakeHttp().install(monkeypatch)
    code = main(["--data-root", str(tmp_path), "papers", "recommend", "goal", "--recipe", "core"])
    assert code == 2
    assert http.calls == []


def test_recommend_reports_no_match_exit_three(tmp_path, monkeypatch):
    http = FakeHttp(report=_report("no_recommendations")).install(monkeypatch)
    code = main([
        "--data-root", str(tmp_path), "papers", "recommend", "no match",
        "--domain", "math-advanced", "--recipe", "core", "--url", "http://127.0.0.1:8901",
    ])
    assert code == 3
    assert http.calls


def test_recommend_service_unreachable_returns_six(tmp_path, monkeypatch):
    FakeHttp(unreachable=True).install(monkeypatch)
    code = main([
        "--data-root", str(tmp_path), "papers", "recommend", "goal",
        "--domain", "math-advanced", "--url", "http://127.0.0.1:8901",
    ])
    assert code == 6


# ---------------- selections list / show → HTTP ----------------


def test_selections_list_passes_filters_and_prints_summaries(tmp_path, monkeypatch, capsys):
    summaries = [{
        "selection_id": SELECTION_ID, "domain_id": "math-advanced", "recipe": "frontier",
        "status": "ranked", "created_at": "2026-07-30T00:00:00+00:00", "recommendation_count": 3,
    }]
    http = FakeHttp(selections=summaries).install(monkeypatch)
    code = main([
        "--data-root", str(tmp_path), "papers", "selections", "list",
        "--domain", "math-advanced", "--recipe", "frontier", "--url", "http://127.0.0.1:8901",
    ])
    assert code == 0
    listing = next(call for call in http.calls if call[1].endswith("/api/v1/papers/selections"))
    assert listing[2]["domain_id"] == "math-advanced"
    assert listing[2]["recipe"] == "frontier"
    out = capsys.readouterr().out
    assert SELECTION_ID in out and "frontier" in out and "3" in out


def test_selections_show_reads_report(tmp_path, monkeypatch, capsys):
    http = FakeHttp().install(monkeypatch)
    code = main([
        "--data-root", str(tmp_path), "papers", "selections", "show", SELECTION_ID,
        "--url", "http://127.0.0.1:8901",
    ])
    assert code == 0
    assert ("GET", f"http://127.0.0.1:8901/api/v1/papers/selections/{SELECTION_ID}", {}) in http.calls
    assert "Series Convergence" in capsys.readouterr().out


def test_selections_show_unknown_reports_error_code(tmp_path, monkeypatch):
    FakeHttp().install(monkeypatch)
    code = main([
        "--data-root", str(tmp_path), "papers", "selections", "show",
        "sel-20260730T000000Z-00000000", "--url", "http://127.0.0.1:8901",
    ])
    assert code == 2


# ---------------- adopt → HTTP（替代 selections download 直写面） ----------------


def test_adopt_posts_per_pick_placement(tmp_path, monkeypatch, capsys):
    http = FakeHttp(task_result={"selection_id": SELECTION_ID, "adopted": [
        {"rank": 1, "arxiv_id": "2601.00001", "book_id": "mathadvanced-b01", "status": "created"},
    ]}).install(monkeypatch)
    code = main([
        "--data-root", str(tmp_path), "papers", "selections", "adopt", SELECTION_ID,
        "--pick", "1", "--domain", "math-advanced", "--course", "math_analysis",
        "--url", "http://127.0.0.1:8901",
    ])
    assert code == 0
    posted = next(call for call in http.calls if call[0] == "POST")
    assert posted[1] == f"http://127.0.0.1:8901/api/v1/papers/selections/{SELECTION_ID}/adopt"
    assert posted[2]["picks"] == [
        {"rank": 1, "domain_id": "math-advanced", "course_id": "math_analysis"}
    ]
    out = capsys.readouterr().out
    assert "mathadvanced-b01" in out
    assert "books fetch" in out  # 指路：下载走书级取书（裁决 5＝不自动下载）


def test_adopt_without_domain_never_calls_service(tmp_path, monkeypatch):
    http = FakeHttp().install(monkeypatch)
    code = main([
        "--data-root", str(tmp_path), "papers", "selections", "adopt", SELECTION_ID, "--pick", "1",
    ])
    assert code == 2
    assert http.calls == []


def test_selection_download_subcommand_is_retired(tmp_path):
    """B 步退役：`papers selections download` 不再是合法子命令（下载唯一路径＝书行 fetch）。"""
    with pytest.raises(SystemExit):
        main(["--data-root", str(tmp_path), "papers", "selections", "download", SELECTION_ID, "--pick", "1"])


# ---------------- 保留面：search/get 仍本地直调 ----------------


def test_paper_cli_search_without_download_needs_no_domain(monkeypatch, tmp_path):
    """纯检索分支不落盘，仍走本地 PaperService，不要求 `--domain`。"""

    class LocalService:
        def __init__(self):
            self.closed = False

        def search(self, *args, **kwargs):
            return []

        def close(self):
            self.closed = True

    service = LocalService()
    monkeypatch.setattr("qed_tracker.cli._paper_service", lambda settings: service)
    code = main(["--data-root", str(tmp_path), "papers", "search", "rag"])
    assert code == 3
    assert service.closed


def test_paper_get_without_domain_never_lands(monkeypatch, tmp_path):
    """F9 裁定：单条直写通道缺 `--domain` 直接返回 2，不构造服务、不触发下载。"""
    constructed = []

    def factory(settings):
        constructed.append(settings)
        return SimpleNamespace(close=lambda: None)

    monkeypatch.setattr("qed_tracker.cli._paper_service", factory)
    assert main(["--data-root", str(tmp_path), "papers", "get", "2601.00001"]) == 2
    assert not constructed
