"""CLI `knowledge import` 导入即确认流程测试（QED-050 手动轨 / 数据文件版契约）。

fake httpx.post 模拟 8901 adopt/confirm 端点语义（后端落真 SQLite KnowledgeRepository），
断言 CLI 编排后的最终事实：知识 confirmed、refs 回填 book_id、重放幂等、confirm 失败记录错误。
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
from qed_tracker.db.engine import utc_now
from qed_tracker.db.knowledge_repository import InvalidTransition, KnowledgeRepository
from qed_tracker.db.models import Base, QedCourse, QedDomain

COURSE = "math_analysis"


@pytest.fixture
def repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'cli.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    now = utc_now()
    session.add(QedDomain(domain_id="math-advanced", name="数学（高等数学）", description="d",
                          stages=["基础", "主干", "分支", "前沿"], created_at=now, updated_at=now))
    session.add(QedCourse(course_id=COURSE, domain_id="math-advanced", sort_order=1,
                          name="数学分析", aliases=[], stage="基础", prerequisites=[],
                          related_targets=[], created_at=now, updated_at=now))
    session.commit()
    yield KnowledgeRepository(factory)
    engine.dispose()


def _ref(title: str, author: str, roles: list[str]) -> dict:
    return {"title": title, "part": "", "authors": [{"name": author, "role": "author"}],
            "publisher": "", "edition": "", "year": None, "language": "zh", "roles": roles}


def _course_payload() -> dict:
    return {
        "domain_id": "math-advanced",
        "course_id": COURSE,
        "course_name": "数学分析",
        "tutorials": [
            {"knowledge_id": "kt-mathanalysis-1", "kind": "tutorial", "set_no": "1",
             "name": "教程1：测试教程", "position": "beginner", "intro": "教材简介。" * 40,
             "textbook_ref": [_ref("测试教材", "Tester", ["textbook", "exercises"])],
             "exercise_ref": None, "parallel_ref": None},
            {"knowledge_id": "kt-mathanalysis-2", "kind": "tutorial", "set_no": "2",
             "name": "教程2：配置", "position": "advanced", "intro": "教材简介之二。" * 40,
             "textbook_ref": [_ref("配置教材", "Tester2", ["textbook"])],
             "exercise_ref": [_ref("测试习题集", "Tester3", ["exercises"])],
             "parallel_ref": None},
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
    """用真 repo 模拟 8901 adopt/confirm 端点语义；记录请求轨迹。"""
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
                row = repo.confirm_knowledge(knowledge_id)
            except InvalidTransition as exc:  # 真实端点映射：非法迁移 → 409
                return _FakeResponse(409, {"detail": str(exc)})
            return _FakeResponse(200, row.to_dict())
        return _FakeResponse(404, {"detail": f"unexpected path: {path}"})

    monkeypatch.setattr("httpx.post", handler)
    return calls


def _args(path: Path) -> SimpleNamespace:
    return SimpleNamespace(path=path, json=True, tracker_url="http://127.0.0.1:8901")


def test_import_lands_confirmed_with_books(repo, fake_8901, tmp_path) -> None:
    course_file = tmp_path / f"{COURSE}.json"
    course_file.write_text(json.dumps(_course_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = _knowledge_import(_args(course_file), load_settings(data_root=tmp_path))

    assert exit_code == 0
    knowledge_rows = repo.list_knowledge(course_id=COURSE)
    assert {row.status for row in knowledge_rows} == {"confirmed"}
    assert {row.set_no for row in knowledge_rows} == {"1", "2"}
    set1 = next(row for row in knowledge_rows if row.set_no == "1")
    assert set1.textbook_ref[0]["book_id"].startswith("mathanalysis-b")
    # 采纳即建 decided 书行：套1 教材（含习题）+ 套2 教材 + 套2 习题集
    books = repo.list_books()
    assert {(b.title, b.status) for b in books} == {
        ("测试教材", "decided"),
        ("配置教材", "decided"),
        ("测试习题集", "decided"),
    }
    confirm_calls = [c for c in fake_8901 if "/confirm" in c[0]]
    assert len(confirm_calls) == 2


def test_import_replay_is_idempotent(repo, fake_8901, tmp_path, capsys) -> None:
    course_file = tmp_path / f"{COURSE}.json"
    course_file.write_text(json.dumps(_course_payload(), ensure_ascii=False), encoding="utf-8")
    assert _knowledge_import(_args(course_file), load_settings(data_root=tmp_path)) == 0
    capsys.readouterr()  # 丢弃首跑输出，只断言重放这一轮

    exit_code = _knowledge_import(_args(course_file), load_settings(data_root=tmp_path))
    captured = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert captured["sets"] == 2
    assert captured["confirmed"] == 0
    assert captured["confirm_skipped"] == 2
    assert captured["books_created"] == 0
    assert captured["errors"] == []
    assert len(repo.list_books()) == 3  # 不重复建册


def test_import_records_confirm_409_but_continues(repo, fake_8901, tmp_path, capsys) -> None:
    def broken_confirm(*_a, **_kw):
        raise InvalidTransition("教程状态迁移非法：confirmed → confirmed")

    repo.confirm_knowledge = broken_confirm  # 模拟仓储侧确认故障（端点会映射 409）
    course_file = tmp_path / f"{COURSE}.json"
    course_file.write_text(json.dumps(_course_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = _knowledge_import(_args(course_file), load_settings(data_root=tmp_path))
    captured = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert len(captured["errors"]) == 2
    assert all("409" in message for message in captured["errors"])
    assert captured["books_created"] == 3
    assert {row.status for row in repo.list_knowledge(course_id=COURSE)} == {"draft"}
