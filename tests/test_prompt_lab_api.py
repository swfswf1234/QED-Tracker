"""prompt-lab dry-run API 契约测试（QED-043 评估模式）。

守护面：POST /api/v1/prompt-explores/dry-run 同步执行领域探索管线，
不入任务队列，唯一痕迹是 qed_llm_calls 的 LLM 日志
（direct 模式由 LlmClient 写入）。
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


# ---------------- QED-047（A1）：课程层探索 dry-run 端点 ----------------


class FakeCoursePipeline:
    """课程管线固定 fake；记录构造 kwargs 与最近一次 explore 入参。"""

    last_instance: FakeCoursePipeline | None = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.step_calls = [
            {"step": "tutorials", "template_id": "course-explore/tutorials@v1", "duration_ms": 9},
        ]
        self.last_call: dict = {}
        FakeCoursePipeline.last_instance = self

    def explore(self, course, *, domain_name="", mode="direct", ref_text="", ref_doc_path=""):
        self.last_call = {
            "course": course, "domain_name": domain_name, "mode": mode,
            "ref_text": ref_text, "ref_doc_path": ref_doc_path,
        }
        if mode == "doc" and not Path(ref_doc_path).is_file():
            raise PipelineError(f"探索文档无法读取：{ref_doc_path}", code="INVALID_PARAMS")
        if mode == "text" and not ref_text.strip():
            raise PipelineError("mode=text 必须提供非空 ref_text", code="INVALID_PARAMS")
        return {
            "course": course,
            "tutorials": [{
                "proposal_id": "pp_abc123", "set_no": "1",
                "set_name": "菲赫金哥尔茨《微积分学教程》+ 吉米多维奇习题集",
                "textbook": {"title": "微积分学教程", "original_title": "", "roles": ["textbook"],
                             "position": "comprehensive", "intro": "苏版经典三卷本，中文翻译成熟，" * 8},
                "exercise": {"title": "吉米多维奇数学分析习题集", "original_title": "",
                             "roles": ["exercises"], "position": "comprehensive",
                             "intro": "题量巨大的经典习题集，配套解答齐全，" * 8},
                "reason": "苏版经典，与国内大纲最接近",
            }],
        }

    def close(self):
        self.closed = True


@pytest.fixture
def course_client(tmp_path, monkeypatch):
    """注入 SQLite 仓储（种子 01 数学分析）+ FakeCoursePipeline。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from qed_tracker.database import utc_now
    from qed_tracker.db.knowledge_repository import KnowledgeRepository
    from qed_tracker.db.models import Base, QedCourse, QedDomain

    engine = create_engine(f"sqlite:///{tmp_path / 'course.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    now = utc_now()
    session.add(QedDomain(domain_id="math", name="数学（高等数学）", description="d",
                          stages=["基础", "进阶"], created_at=now, updated_at=now))
    session.add(QedCourse(course_id="01_math_analysis", domain_id="math", sort_order=1,
                          name="数学分析", aliases=["微积分"], stage="基础", prerequisites=[],
                          related_targets=[], description="分析学地基",
                          created_at=now, updated_at=now))
    session.commit()
    repo = KnowledgeRepository(lambda: factory())
    monkeypatch.setattr(api_main, "llm_api_key", lambda: "k")
    monkeypatch.setattr(api_main, "CoursePipeline", FakeCoursePipeline)
    FakeCoursePipeline.last_instance = None
    app = api_main.create_app(load_settings(data_root=tmp_path), knowledge_repository=repo)
    with TestClient(app) as test_client:
        yield test_client
    engine.dispose()


def test_course_dry_run_returns_report_and_calls(course_client) -> None:
    response = course_client.post(
        "/api/v1/courses/01_math_analysis/prompt-explores/dry-run",
        json={"mode": "direct"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["report"]["course"]["course_id"] == "01_math_analysis"
    assert body["report"]["course"]["name"] == "数学分析"
    tutorial = body["report"]["tutorials"][0]
    assert tutorial["proposal_id"].startswith("pp_")
    assert tutorial["textbook"]["title"] == "微积分学教程"
    assert body["calls"][0]["template_id"] == "course-explore/tutorials@v1"
    instance = FakeCoursePipeline.last_instance
    assert instance is not None
    assert instance.last_call["course"]["description"] == "分析学地基"
    assert getattr(instance, "closed", False)


def test_course_dry_run_unknown_course_404(course_client) -> None:
    response = course_client.post("/api/v1/courses/nope/prompt-explores/dry-run", json={})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "COURSE_NOT_FOUND"


def test_course_dry_run_rejects_unknown_mode(course_client) -> None:
    response = course_client.post(
        "/api/v1/courses/01_math_analysis/prompt-explores/dry-run", json={"mode": "web"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_PARAMS"


def test_course_dry_run_doc_mode_missing_file_maps_invalid_params(course_client, tmp_path) -> None:
    missing = str(tmp_path / "nope.txt")
    response = course_client.post(
        "/api/v1/courses/01_math_analysis/prompt-explores/dry-run",
        json={"mode": "doc", "ref_doc_path": missing},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_PARAMS"
    assert getattr(FakeCoursePipeline.last_instance, "closed", False)


def test_course_dry_run_unconfigured_key_maps_409(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(api_main, "llm_api_key", lambda: "")
    app = api_main.create_app(load_settings(data_root=tmp_path))
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/courses/01_math_analysis/prompt-explores/dry-run", json={}
        )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "LLM_UNAVAILABLE"


def test_course_dry_run_llm_failure_maps_502(course_client, monkeypatch) -> None:
    """QED-047 502 覆盖：LLM 层异常映射为502 + 原始错误码。"""

    class BoomCoursePipeline(FakeCoursePipeline):
        def explore(self, course, **kw):
            raise PipelineError("模型网络请求失败", code="LLM_UNAVAILABLE")

    monkeypatch.setattr(api_main, "CoursePipeline", BoomCoursePipeline)
    response = course_client.post(
        "/api/v1/courses/01_math_analysis/prompt-explores/dry-run",
        json={"mode": "direct"},
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LLM_UNAVAILABLE"
