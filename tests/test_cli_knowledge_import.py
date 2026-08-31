"""CLI `knowledge import` 导入即确认流程测试（QED-050 手动轨，2026-08-31）。

fake httpx.post 模拟 8901 三个端点语义（adopt→201 created[]/confirm→200/books→200，
InvalidTransition→409 与真实端点映射一致），后端行为落真 SQLite KnowledgeRepository——
断言 CLI 编排后的最终事实：知识 confirmed 且 refs 未被 confirm 清空、candidate 册与
refs 一一对应、重放幂等（confirm 跳过 + 册不重复）、confirm 失败记录错误且建册继续。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.cli import _knowledge_import
from qed_tracker.config import load_settings
from qed_tracker.database import utc_now
from qed_tracker.db.knowledge_repository import InvalidTransition, KnowledgeRepository
from qed_tracker.db.models import Base, QedCourse, QedDomain


@pytest.fixture
def repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'cli.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    now = utc_now()
    session.add(QedDomain(domain_id="math-advanced", name="数学（高等数学）", description="d",
                          stages=["基础", "主干", "分支", "前沿"], created_at=now, updated_at=now))
    session.add(QedCourse(course_id="01_math_analysis", domain_id="math-advanced", sort_order=1,
                          name="数学分析", aliases=[], stage="基础", prerequisites=[],
                          related_targets=[], created_at=now, updated_at=now))
    session.commit()
    yield KnowledgeRepository(factory)
    engine.dispose()


def _course_payload() -> dict:
    return {
        "meta": {"contract": "course-knowledge/manual@v1", "confirmed_at": "2026-08-31"},
        "domain": "math-advanced",
        "course": {"course_id": "01_math_analysis", "name": "数学分析", "aliases": ["微积分"]},
        "tutorials": [
            {"set_no": "1", "set_name": "教程1：测试教程",
             "textbook": {"title": "测试教材", "original_title": "Test", "authors": ["Tester"],
                          "version": {"edition": "第1版"}, "roles": ["textbook", "exercises"],
                          "position": "beginner", "intro": "教材简介。",
                          "target_path": "raw/math-advanced/01_math_analysis/测试教材.pdf"},
             "exercise": None, "reason": "理由"},
            {"set_no": "2", "set_name": "教程2：配置",
             "textbook": {"title": "配置教材", "authors": ["Tester2"], "roles": ["textbook"],
                          "position": "advanced", "intro": "教材简介之二。"},
             "exercise": {"title": "测试习题集", "authors": ["Tester3"], "roles": ["exercises"],
                          "position": "advanced", "intro": "习题集简介。"},
             "reason": ""},
        ],
    }


class _FakeResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body

    def json(self) -> dict:
        return self._body


@pytest.fixture
def fake_8901(repo, monkeypatch):
    """用真 repo 模拟 8901 adopt/confirm/books 三端点语义；记录请求轨迹。"""
    calls: list[tuple[str, dict]] = []

    def handler(url: str, json: dict | None = None, **_kw) -> _FakeResponse:  # noqa: A002
        calls.append((url, json or {}))
        path = url.split("/api/v1/", 1)[-1]
        if path.startswith("courses/") and path.endswith("/knowledge"):
            course_id = path.split("/")[1]
            results = repo.adopt_tutorials(course_id, json["tutorials"])
            return _FakeResponse(201, {"created": results})
        if "/confirm" in path:
            knowledge_id = path.split("/")[1]
            try:
                row = repo.confirm_knowledge(
                    knowledge_id,
                    textbook_ref=json.get("textbook_ref"),
                    exercise_ref=json.get("exercise_ref"),
                    textbook_intro=json.get("textbook_intro", ""),
                    exercise_intro=json.get("exercise_intro", ""),
                )
            except InvalidTransition as exc:  # 真实端点映射：非法迁移 → 409
                return _FakeResponse(409, {"detail": str(exc)})
            return _FakeResponse(200, row.to_dict())
        if path == "books":
            row = repo.create_book(
                json["knowledge_id"], kind=json.get("kind", "textbook"), roles=json.get("roles") or [],
                title=json["title"], part=json.get("part", ""), display_title=json.get("display_title", ""),
                authors=json.get("authors") or [], language=json.get("language", ""),
                version=json.get("version"),
            )
            return _FakeResponse(200, row.to_dict())
        return _FakeResponse(404, {"detail": f"unexpected path: {path}"})

    monkeypatch.setattr("httpx.post", handler)
    return calls


def _args(path: Path) -> SimpleNamespace:
    return SimpleNamespace(path=path, json=True, tracker_url="http://127.0.0.1:8901")


def test_import_lands_confirmed_with_candidate_books(repo, fake_8901, tmp_path) -> None:
    course_file = tmp_path / "01_math_analysis.json"
    course_file.write_text(json.dumps(_course_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = _knowledge_import(_args(course_file), load_settings(data_root=tmp_path))

    assert exit_code == 0
    # 知识全部确认，refs 未被 confirm 清空（target_path 保留）
    knowledge_rows = repo.list_knowledge(course_id="01_math_analysis")
    assert {row.status for row in knowledge_rows} == {"confirmed"}
    assert {row.set_no for row in knowledge_rows} == {"1", "2"}
    set1 = next(row for row in knowledge_rows if row.set_no == "1")
    assert set1.textbook_ref["target_path"] == "raw/math-advanced/01_math_analysis/测试教材.pdf"
    assert set1.textbook_intro == "教材简介。"
    # 候选册与 refs 一一对应：套1 教材（无独立习题）+ 套2 教材 + 套2 习题集
    books = repo.list_books(include_hidden=True)
    assert {(b.kind, b.title) for b in books} == {
        ("textbook", "测试教材"),
        ("textbook", "配置教材"),
        ("exercise", "测试习题集"),
    }
    assert all(b.status == "candidate" for b in books)
    exercise_book = next(b for b in books if b.kind == "exercise")
    assert exercise_book.roles == ["exercises"]
    # 请求轨迹：2 次确认、3 次建册，确认 body 显式带 refs（规避 confirm 空 body 清 refs 隐患）
    confirm_calls = [c for c in fake_8901 if "/confirm" in c[0]]
    book_calls = [c for c in fake_8901 if c[0].endswith("/books")]
    assert len(confirm_calls) == 2
    assert len(book_calls) == 3
    assert confirm_calls[0][1]["textbook_ref"]["target_path"].startswith("raw/math-advanced/")
    assert book_calls[0][1]["kind"] == "textbook"


def test_import_replay_is_idempotent(repo, fake_8901, tmp_path, capsys) -> None:
    course_file = tmp_path / "01_math_analysis.json"
    course_file.write_text(json.dumps(_course_payload(), ensure_ascii=False), encoding="utf-8")
    assert _knowledge_import(_args(course_file), load_settings(data_root=tmp_path)) == 0
    capsys.readouterr()  # 丢弃首跑输出，只断言重放这一轮

    exit_code = _knowledge_import(_args(course_file), load_settings(data_root=tmp_path))
    captured = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert captured["sets"] == 2
    assert captured["confirmed"] == 0
    assert captured["confirm_skipped"] == 2
    assert captured["books_ensured"] == 3
    assert captured["errors"] == []
    assert len(repo.list_books(include_hidden=True)) == 3  # 不重复建册


def test_import_records_confirm_409_but_continues_books(repo, fake_8901, tmp_path, capsys) -> None:
    def broken_confirm(*_a, **_kw):
        raise InvalidTransition("教程状态迁移非法：confirmed → confirmed")

    repo.confirm_knowledge = broken_confirm  # 模拟仓储侧确认故障（端点会映射 409）
    course_file = tmp_path / "01_math_analysis.json"
    course_file.write_text(json.dumps(_course_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = _knowledge_import(_args(course_file), load_settings(data_root=tmp_path))
    captured = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert len(captured["errors"]) == 2
    assert all("409" in message for message in captured["errors"])
    # 确认失败不阻断建册：候选册仍然就绪，重放可续（知识仍为 draft，重跑会再次确认）
    assert captured["books_ensured"] == 3
    assert {row.status for row in repo.list_knowledge(course_id="01_math_analysis")} == {"draft"}
