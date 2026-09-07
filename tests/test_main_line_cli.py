"""主链路 CLI（mainline）命令测试：解析、DB 门禁与行为。

覆盖当前 CLI 契约（QED-050-D）：`mainline list/new/review/verify/channels`。
已退役命令（migrate / approve / reject）与旧下载编排不再测试；`mainline
download` 与 `books fetch` 行为依赖 8901 后台任务链，由 tests/test_book_api.py
（任务提交+轮询）与 QED-010 冒烟覆盖，本文件仅保留其 parser 断言。

行为断言直接调用 `_mainline_impl(args, repo, settings)`（SQLite repo 注入），
解析断言走 `build_parser`；DB 门禁（db_configured=False → exit 2）走 `main`。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.cli import build_parser, main
from qed_tracker.config import load_settings
from qed_tracker.db.engine import utc_now
from qed_tracker.db.knowledge_repository import KnowledgeRepository
from qed_tracker.db.models import Base, QedCourse, QedDomain

COURSE = "01_math_analysis"
ABBR = "01mathanalysis"


@pytest.fixture
def repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'cli.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    now = utc_now()
    session.add(QedDomain(domain_id="math", name="数学", description="d", stages=["基础"],
                          created_at=now, updated_at=now))
    session.add(QedCourse(course_id=COURSE, domain_id="math", sort_order=1, name="数学分析",
                          aliases=[], stage="基础", prerequisites=[], related_targets=[],
                          created_at=now, updated_at=now))
    session.commit()
    yield KnowledgeRepository(factory)
    engine.dispose()


@pytest.fixture(autouse=True)
def _courses_repository(repo):
    from qed_tracker.courses import set_repository

    set_repository(repo)
    yield
    set_repository(None)


def _args(**kw) -> SimpleNamespace:
    defaults = {
        "mainline_command": None,
        "course": "",
        "title": None,
        "author": [],
        "set_no": "",
        "knowledge_id": "",
        "book": "",
        "json": False,
        "intro": None,
        "version": None,
        "reason": "",
    }
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _settings(tmp_path: Path):
    return load_settings(data_root=tmp_path)


def _prefill_response() -> dict:
    return {
        "evaluation": {"source": "llm", "text": "经典教材", "authority": "高", "set_candidate": "套一"},
        "advice": {"download": "recommended", "reason": "MIT 指定"},
    }


class _FakeAdvisor:
    def __init__(self, calls: list | None = None):
        self.calls = calls if calls is not None else []

    def prefill(self, *, course, title, authors, **kw):
        self.calls.append({"course": course, "title": title, "authors": authors})
        return _prefill_response()

    def close(self):
        pass


def _ref(title: str, *, roles: list[str] | None = None, **kw) -> dict:
    value: dict = {
        "title": title, "part": "", "language": "zh", "edition": "",
        "authors": [{"name": "鲁丁", "role": "author"}],
        "roles": roles or ["textbook"],
    }
    value.update(kw)
    return value


def _adopt_tutorial(repo: KnowledgeRepository, *, set_no: str = "1",
                    name: str = "教程1：数学分析原理", title: str = "数学分析原理") -> dict:
    """adopt 一个教程 + 一本 textbook 书；返回 adopt 结果 dict。"""
    results = repo.adopt_tutorials(COURSE, [{
        "set_no": set_no, "name": name, "position": "beginner",
        "intro": "测试教程" * 20,
        "textbook_ref": [_ref(title)],
        "exercise_ref": [], "parallel_ref": [],
    }])
    return results[0]


# ---------------- 解析 ----------------

def test_courses_list_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["courses", "list"])
    assert args.command == "courses"
    assert args.courses_command == "list"


def test_courses_show_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["courses", "show", "01_math_analysis"])
    assert args.courses_command == "show"
    assert args.course_id == "01_math_analysis"


def test_mainline_list_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["mainline", "list", "--course", "01_math_analysis"])
    assert args.command == "mainline"
    assert args.mainline_command == "list"
    assert args.course == "01_math_analysis"


def test_mainline_review_parses_knowledge_id() -> None:
    parser = build_parser()
    args = parser.parse_args(["mainline", "review", "kt-01ma-3"])
    assert args.mainline_command == "review"
    assert args.knowledge_id == "kt-01ma-3"


def test_mainline_new_parses_set_no() -> None:
    """QED-036：mainline new --set-no 解析。"""
    parser = build_parser()
    new_args = parser.parse_args(["mainline", "new", "--course", "01_math_analysis",
                                  "--title", "数学分析原理", "--author", "Rudin", "--set-no", "1"])
    assert new_args.set_no == "1"
    assert new_args.author == ["Rudin"]


def test_mainline_download_parses_knowledge_id() -> None:
    parser = build_parser()
    args = parser.parse_args(["mainline", "download", "kt-01ma-3", "--include-parallel"])
    assert args.mainline_command == "download"
    assert args.knowledge_id == "kt-01ma-3"
    assert args.include_parallel is True


def test_mainline_verify_parses_book_option() -> None:
    parser = build_parser()
    verify = parser.parse_args(["mainline", "verify", "kt-01ma-3", "--book", "01ma-b05"])
    assert verify.mainline_command == "verify"
    assert verify.knowledge_id == "kt-01ma-3"
    assert verify.book == "01ma-b05"
    plain = parser.parse_args(["mainline", "verify", "kt-01ma-3"])
    assert plain.book is None


# ---------------- DB 门禁 ----------------

def test_courses_show_requires_db(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)  # 隔离真实 .env：模拟无凭据环境
    assert main(["--data-root", str(tmp_path), "courses", "show", "01_math_analysis"]) == 2
    assert "数据库未配置" in capsys.readouterr().err


def test_mainline_list_requires_db(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("qed_tracker.cli._load_root_env", lambda start: None)
    assert main(["--data-root", str(tmp_path), "mainline", "list", "--course", "01_math_analysis"]) == 2
    assert "数据库未配置" in capsys.readouterr().err


def test_mainline_db_error_returns_2(tmp_path, monkeypatch, capsys) -> None:
    from sqlalchemy.exc import OperationalError

    import qed_tracker.cli as cli_module
    import qed_tracker.db.engine as database_module

    engine = create_engine(f"sqlite:///{tmp_path / 'mainline.db'}")

    def _boom(args, repo, settings):
        raise OperationalError("SELECT", {}, "server closed connection")

    monkeypatch.setattr(database_module, "create_engine_for", lambda settings: engine)
    monkeypatch.setattr(cli_module, "_mainline_impl", _boom)
    monkeypatch.setenv("QED_DB_PASSWORD", "test")
    assert main(["--data-root", str(tmp_path), "mainline", "list", "--course", "01_math_analysis"]) == 2
    assert "数据库错误" in capsys.readouterr().err
    engine.dispose()


# ---------------- new（LLM 预填 draft） ----------------

def test_mainline_new_creates_draft_knowledge(tmp_path, repo, monkeypatch, capsys) -> None:
    import qed_tracker.cli as cli_module

    calls: list = []
    monkeypatch.setattr(cli_module, "_mainline_advisor", lambda **kw: _FakeAdvisor(calls))
    args = _args(mainline_command="new", course=COURSE, title="数学分析原理", author=["Rudin"])
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0

    items = repo.list_knowledge(course_id=COURSE)
    assert len(items) == 1
    assert items[0].status == "draft"
    assert items[0].kind == "tutorial"
    assert len(calls) == 1  # LLM 预填只出建议，不落 evaluation 字段
    out = capsys.readouterr().out
    assert "已创建条目" in out
    assert "MIT 指定" in out


def test_mainline_new_duplicate_returns_2_no_llm_call(tmp_path, repo, monkeypatch) -> None:
    import qed_tracker.cli as cli_module

    calls: list = []
    monkeypatch.setattr(cli_module, "_mainline_advisor", lambda **kw: _FakeAdvisor(calls))
    args = _args(mainline_command="new", course=COURSE, title="数学分析原理")
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 2
    assert len(calls) == 1  # 重复检测在 LLM 调用之前


def test_mainline_new_unknown_course_returns_2(tmp_path, repo, monkeypatch) -> None:
    import qed_tracker.cli as cli_module

    calls: list = []
    monkeypatch.setattr(cli_module, "_mainline_advisor", lambda **kw: _FakeAdvisor(calls))
    args = _args(mainline_command="new", course="99_nope", title="数学分析原理")
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 2
    assert len(calls) == 0


def test_mainline_new_with_set_no_generates_standard_name(tmp_path, repo, monkeypatch) -> None:
    """QED-036：mainline new 带 --set-no 时 name 按「教程{set_no}：书名（作者）」规范生成。"""
    import qed_tracker.cli as cli_module

    calls: list = []
    monkeypatch.setattr(cli_module, "_mainline_advisor", lambda **kw: _FakeAdvisor(calls))
    args = _args(mainline_command="new", course=COURSE, title="数学分析原理",
                 author=["Rudin"], set_no="1")
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0

    items = repo.list_knowledge(course_id=COURSE)
    assert len(items) == 1
    assert items[0].set_no == "1"
    assert items[0].name == "教程1：数学分析原理（Rudin）"


def test_mainline_new_without_set_no_keeps_title(tmp_path, repo, monkeypatch) -> None:
    """QED-036：不带 --set-no 时保持原始 title（draft 期命名）。"""
    import qed_tracker.cli as cli_module

    monkeypatch.setattr(cli_module, "_mainline_advisor", lambda **kw: _FakeAdvisor())
    args = _args(mainline_command="new", course=COURSE, title="数学分析原理")
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0
    items = repo.list_knowledge(course_id=COURSE)
    assert items[0].name == "数学分析原理"


# ---------------- review（draft → confirmed） ----------------

def test_mainline_review_confirms_knowledge(tmp_path, repo, capsys) -> None:
    import qed_tracker.cli as cli_module

    knowledge = repo.create_knowledge(course_id=COURSE, set_no="1", name="教程1：数学分析原理")
    args = _args(mainline_command="review", knowledge_id=knowledge.knowledge_id)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0

    updated = repo.get_knowledge(knowledge.knowledge_id)
    assert updated.status == "confirmed"
    assert "已定稿" in capsys.readouterr().out


def test_mainline_review_missing_knowledge_returns_2(tmp_path, repo, capsys) -> None:
    import qed_tracker.cli as cli_module

    args = _args(mainline_command="review", knowledge_id="kt-none-9")
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 2
    assert "教程不存在" in capsys.readouterr().err


def test_mainline_review_invalid_transition_returns_2(tmp_path, repo, capsys) -> None:
    import qed_tracker.cli as cli_module

    knowledge = repo.create_knowledge(course_id=COURSE, set_no="1", name="教程1：数学分析原理")
    repo.confirm_knowledge(knowledge.knowledge_id)
    args = _args(mainline_command="review", knowledge_id=knowledge.knowledge_id)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 2
    assert "状态迁移非法" in capsys.readouterr().err


# ---------------- list ----------------

def test_mainline_list_shows_books(tmp_path, repo, capsys) -> None:
    import qed_tracker.cli as cli_module

    _adopt_tutorial(repo, set_no="1", name="教程1：数学分析原理", title="数学分析原理")
    args = _args(mainline_command="list", course=COURSE)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0

    out = capsys.readouterr().out
    assert f"kt-{ABBR}-1" in out
    assert "教程1：数学分析原理" in out
    assert "[decided/missing]" in out  # 书行 decided、未取书 holding=missing


def test_mainline_list_json(tmp_path, repo, capsys) -> None:
    import qed_tracker.cli as cli_module

    result = _adopt_tutorial(repo, set_no="1", name="教程1：数学分析原理", title="数学分析原理")
    knowledge_id = result["knowledge_id"]
    args = _args(mainline_command="list", course=COURSE, json=True)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0

    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 1
    item = payload[0]
    assert item["knowledge_id"] == knowledge_id
    assert item["status"] == "draft"
    books = item["books"]
    assert len(books) == 1
    assert books[0]["title"] == "数学分析原理"
    assert books[0]["status"] == "decided"


# ---------------- verify（只读复核 owned 书） ----------------

def _seed_owned(repo: KnowledgeRepository, tmp_path: Path, pdf_bytes: bytes) -> tuple[str, str]:
    """adopt 教程 + 书，mark_owned 并落盘合法 PDF；返回 (knowledge_id, book_id)。"""
    result = _adopt_tutorial(repo, set_no="1", name="教程1：数学分析原理", title="数学分析原理")
    knowledge_id = result["knowledge_id"]
    book = repo.list_books(knowledge_id)[0]
    rel = f"raw/math/{COURSE}/数学分析原理.pdf"
    repo.mark_owned(book.book_id, file_path=rel)
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(pdf_bytes)
    return knowledge_id, book.book_id


def test_mainline_verify_success(tmp_path, repo, pdf_bytes, capsys) -> None:
    import qed_tracker.cli as cli_module

    knowledge_id, _ = _seed_owned(repo, tmp_path, pdf_bytes)
    args = _args(mainline_command="verify", knowledge_id=knowledge_id)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0

    out = capsys.readouterr().out
    assert "[ok]" in out
    assert "数学分析原理" in out


def test_mainline_verify_no_owned_returns_2(tmp_path, repo, capsys) -> None:
    import qed_tracker.cli as cli_module

    result = _adopt_tutorial(repo, set_no="1", name="教程1：数学分析原理", title="数学分析原理")
    args = _args(mainline_command="verify", knowledge_id=result["knowledge_id"])
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 2
    assert "没有已登记" in capsys.readouterr().err


def test_mainline_verify_missing_file_returns_3(tmp_path, repo, pdf_bytes, capsys) -> None:
    import qed_tracker.cli as cli_module

    result = _adopt_tutorial(repo, set_no="1", name="教程1：数学分析原理", title="数学分析原理")
    knowledge_id = result["knowledge_id"]
    book = repo.list_books(knowledge_id)[0]
    repo.mark_owned(book.book_id, file_path="raw/math/01_math_analysis/不存在.pdf")  # 不落盘
    args = _args(mainline_command="verify", knowledge_id=knowledge_id)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 3


def test_mainline_verify_invalid_pdf_returns_2(tmp_path, repo, capsys) -> None:
    import qed_tracker.cli as cli_module

    result = _adopt_tutorial(repo, set_no="1", name="教程1：数学分析原理", title="数学分析原理")
    knowledge_id = result["knowledge_id"]
    book = repo.list_books(knowledge_id)[0]
    rel = "raw/math/01_math_analysis/损坏.pdf"
    repo.mark_owned(book.book_id, file_path=rel)
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"not a pdf")
    args = _args(mainline_command="verify", knowledge_id=knowledge_id)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 2


def test_mainline_verify_specific_book(tmp_path, repo, pdf_bytes, capsys) -> None:
    import qed_tracker.cli as cli_module

    # 教程含两本书：只 owned 一本，指定 --book 复核该本 → ok
    results = repo.adopt_tutorials(COURSE, [{
        "set_no": "1", "name": "教程1：Apostol", "position": "advanced", "intro": "i" * 20,
        "textbook_ref": [_ref("Calculus", language="en"),
                         _ref("Calculus", part="Vol.2", language="en")],
        "exercise_ref": [], "parallel_ref": [],
    }])
    knowledge_id = results[0]["knowledge_id"]
    books = repo.list_books(knowledge_id)
    owned = books[0]
    rel = "raw/math/01_math_analysis/Calculus.pdf"
    repo.mark_owned(owned.book_id, file_path=rel)
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(pdf_bytes)

    args = _args(mainline_command="verify", knowledge_id=knowledge_id, book=owned.book_id)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0
    out = capsys.readouterr().out
    assert "[ok]" in out and owned.book_id in out


# ---------------- channels（渠道有效性汇总） ----------------

def test_mainline_channels_json(tmp_path, repo, capsys) -> None:
    import qed_tracker.cli as cli_module

    result = _adopt_tutorial(repo, set_no="1", name="教程1：数学分析原理", title="数学分析原理")
    book = repo.list_books(result["knowledge_id"])[0]
    repo.add_source(book.book_id, channel="internet_archive", ok=True)
    repo.add_source(book.book_id, channel="internet_archive", ok=False)

    args = _args(mainline_command="channels", json=True)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["channels"]["internet_archive"] == {"ok": 1, "fail": 1}
