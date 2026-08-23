"""主链路 CLI（mainline 五层状态机映射）与 migrate 子命令测试（QED-031 任务 7）。

行为断言直接调用 `_mainline_impl(args, repo, settings)`（SQLite repo 注入），
解析断言走 `build_parser`；DB 门禁（db_configured=False → exit 2）走 `main`。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from qed_tracker.application.books import RankedCandidate
from qed_tracker.cli import build_parser, main
from qed_tracker.config import load_settings
from qed_tracker.database import utc_now
from qed_tracker.db.knowledge_repository import KnowledgeRepository
from qed_tracker.db.models import Base, QedCourse, QedDomain
from qed_tracker.models import Availability, Candidate, DownloadLink


@pytest.fixture
def repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'cli.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    now = utc_now()
    session.add(QedDomain(domain_id="math", name="数学", description="d", stages=["本科基础"],
                          created_at=now, updated_at=now))
    session.add(QedCourse(course_id="01_math_analysis", domain_id="math", sort_order=1, name="数学分析",
                          aliases=[], stage="本科基础", prerequisites=[], related_targets=[],
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
        "intro": None,
        "version": None,
        "reason": "",
        "book": "",
        "json": False,
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


def _record_with(path: str, page_count: int = 1):
    from qed_tracker.models import ResourceRecord

    return ResourceRecord(
        resource_id="sha256:test",
        kind="book",
        title="数学分析原理",
        authors=[],
        language="zh",
        year="",
        identifiers={},
        source={},
        file={"sha256": "0" * 64, "relative_path": path, "page_count": page_count},
    )


class _FakeBookService:
    """无 three_table 依赖的书籍服务替身：search/download/close。"""

    failures: list[tuple[str, str]] = []

    def __init__(self, candidates=None, *, error=None, data_root=None, pdf_bytes=None):
        self.candidates = candidates if candidates is not None else []
        self.error = error
        self.data_root = data_root
        self.pdf_bytes = pdf_bytes

    def search(self, query, *, limit=10):
        if self.error:
            raise RuntimeError(self.error)
        return [RankedCandidate(c) for c in self.candidates]

    def download(self, candidate, *, kind):
        rel = "raw/books/inbox/math_analysis.pdf"
        if self.data_root is not None and self.pdf_bytes is not None:
            path = self.data_root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.pdf_bytes)
        return _record_with(rel)

    def close(self):
        pass


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


def test_mainline_review_parses_with_intro_and_version() -> None:
    parser = build_parser()
    args = parser.parse_args([
        "mainline", "review", "kn_1", "--intro", "经典教材。", "--version", "第8版",
    ])
    assert args.mainline_command == "review"
    assert args.knowledge_id == "kn_1"
    assert args.intro == "经典教材。"
    assert args.version == "第8版"


def test_mainline_new_parses_set_no() -> None:
    """QED-036：mainline new --set-no 与 review --title/--author 解析。"""
    parser = build_parser()
    new_args = parser.parse_args(["mainline", "new", "--course", "01_math_analysis",
                                  "--title", "数学分析原理", "--author", "Rudin", "--set-no", "1"])
    assert new_args.set_no == "1"
    assert new_args.author == ["Rudin"]
    review = parser.parse_args(["mainline", "review", "kn_1",
                                "--title", "数学分析原理", "--author", "Rudin"])
    assert review.title == "数学分析原理"
    assert review.author == ["Rudin"]
    plain = parser.parse_args(["mainline", "review", "kn_1"])
    assert plain.title is None
    assert plain.author == []


def test_mainline_download_uses_knowledge_id() -> None:
    parser = build_parser()
    args = parser.parse_args(["mainline", "download", "kn_1"])
    assert args.mainline_command == "download"
    assert args.knowledge_id == "kn_1"


def test_mainline_verify_approve_book_option_parses() -> None:
    parser = build_parser()
    verify = parser.parse_args(["mainline", "verify", "kn_1", "--book", "bk_1"])
    assert verify.mainline_command == "verify"
    assert verify.knowledge_id == "kn_1"
    assert verify.book == "bk_1"
    approve = parser.parse_args(["mainline", "approve", "kn_1", "--book", "bk_2"])
    assert approve.mainline_command == "approve"
    assert approve.knowledge_id == "kn_1"
    assert approve.book == "bk_2"
    no_book = parser.parse_args(["mainline", "approve", "kn_1"])
    assert no_book.book is None


def test_migrate_subcommand_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["migrate"])
    assert args.command == "migrate"
    assert args.drop_legacy is False


def test_migrate_subcommand_parses_drop_legacy() -> None:
    parser = build_parser()
    args = parser.parse_args(["migrate", "--drop-legacy"])
    assert args.command == "migrate"
    assert args.drop_legacy is True


# ---------------- DB 门禁 ----------------

def test_courses_show_requires_db(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)  # 隔离真实 .env：模拟无凭据环境
    assert main(["--data-root", str(tmp_path), "courses", "show", "01_math_analysis"]) == 2
    assert "数据库未配置" in capsys.readouterr().err


def test_mainline_list_requires_db(tmp_path, monkeypatch, capsys) -> None:
    # 隔离本机根 .env（注入后 db_configured 为真，会连真实库）：模拟无凭据环境
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("qed_tracker.cli._load_root_env", lambda start: None)
    assert main(["--data-root", str(tmp_path), "mainline", "list", "--course", "01_math_analysis"]) == 2
    assert "数据库未配置" in capsys.readouterr().err


def test_migrate_requires_db(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("qed_tracker.cli._load_root_env", lambda start: None)
    assert main(["--data-root", str(tmp_path), "migrate"]) == 2
    assert "数据库未配置" in capsys.readouterr().err


def test_mainline_db_error_returns_2(tmp_path, monkeypatch, capsys) -> None:
    from sqlalchemy.exc import OperationalError

    import qed_tracker.cli as cli_module
    import qed_tracker.database as database_module

    engine = create_engine(f"sqlite:///{tmp_path / 'mainline.db'}")

    def _boom(args, repo, settings):
        raise OperationalError("SELECT", {}, "server closed connection")

    monkeypatch.setattr(database_module, "create_engine_for", lambda settings: engine)
    monkeypatch.setattr(cli_module, "_mainline_impl", _boom)
    monkeypatch.setenv("QED_DB_PASSWORD", "test")
    assert main(["--data-root", str(tmp_path), "mainline", "list", "--course", "01_math_analysis"]) == 2
    assert "数据库错误" in capsys.readouterr().err
    engine.dispose()


def test_migrate_db_error_returns_2(tmp_path, monkeypatch, capsys) -> None:
    from sqlalchemy.exc import OperationalError

    import qed_tracker.database as database_module

    engine = create_engine(f"sqlite:///{tmp_path / 'migrate.db'}")

    def boom():
        raise OperationalError("SELECT", {}, "server closed connection")

    monkeypatch.setattr(database_module, "create_engine_for", lambda settings: engine)
    monkeypatch.setattr(database_module, "session_factory", lambda engine: boom)
    monkeypatch.setenv("QED_DB_PASSWORD", "test")
    assert main(["--data-root", str(tmp_path), "migrate"]) == 2
    assert "数据库错误" in capsys.readouterr().err
    engine.dispose()


# ---------------- new ----------------

def test_mainline_new_creates_draft_knowledge(tmp_path, repo, monkeypatch, capsys) -> None:
    import qed_tracker.cli as cli_module

    calls: list = []
    monkeypatch.setattr(cli_module, "_mainline_advisor", lambda **kw: _FakeAdvisor(calls))
    args = _args(mainline_command="new", course="01_math_analysis", title="数学分析原理", author=["Rudin"])
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0

    items = repo.list_knowledge(course_id="01_math_analysis")
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
    args = _args(mainline_command="new", course="01_math_analysis", title="数学分析原理")
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
    args = _args(mainline_command="new", course="01_math_analysis", title="数学分析原理",
                 author=["Rudin"], set_no="1")
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0

    items = repo.list_knowledge(course_id="01_math_analysis")
    assert len(items) == 1
    assert items[0].set_no == "1"
    assert items[0].name == "教程1：数学分析原理（Rudin）"


def test_mainline_new_without_set_no_keeps_title(tmp_path, repo, monkeypatch) -> None:
    """QED-036：不带 --set-no 时保持原始 title（draft 期命名）。"""
    import qed_tracker.cli as cli_module

    monkeypatch.setattr(cli_module, "_mainline_advisor", lambda **kw: _FakeAdvisor())
    args = _args(mainline_command="new", course="01_math_analysis", title="数学分析原理")
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0
    items = repo.list_knowledge(course_id="01_math_analysis")
    assert items[0].name == "数学分析原理"


# ---------------- review / reject ----------------

def test_mainline_review_confirms_knowledge(tmp_path, repo, capsys) -> None:
    import qed_tracker.cli as cli_module

    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="", name="数学分析原理")
    args = _args(mainline_command="review", knowledge_id=knowledge.knowledge_id)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0

    updated = repo.get_knowledge(knowledge.knowledge_id)
    assert updated.status == "confirmed"
    assert updated.textbook_ref["title"] == "数学分析原理"
    assert "教材与习题集配套资源" in updated.textbook_intro
    assert "已定稿" in capsys.readouterr().out


def test_mainline_review_custom_intro_and_version(tmp_path, repo) -> None:
    import qed_tracker.cli as cli_module

    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="", name="数学分析原理")
    args = _args(mainline_command="review", knowledge_id=knowledge.knowledge_id,
                 intro="MIT 指定教材。", version="第8版")
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0

    updated = repo.get_knowledge(knowledge.knowledge_id)
    assert updated.textbook_intro == "MIT 指定教材。"
    assert updated.textbook_ref["version"] == "第8版"


def test_mainline_review_with_title_and_author_sets_textbook_ref(tmp_path, repo) -> None:
    """QED-036：review 带 --title/--author 时 textbook_ref={title, version, authors}。"""
    import qed_tracker.cli as cli_module

    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="1", name="教程1：数学分析原理（Rudin）")
    args = _args(mainline_command="review", knowledge_id=knowledge.knowledge_id,
                 title="数学分析原理", author=["Rudin"], version="第8版")
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0

    updated = repo.get_knowledge(knowledge.knowledge_id)
    assert updated.textbook_ref == {"title": "数学分析原理", "version": "第8版", "authors": ["Rudin"]}


def test_mainline_review_falls_back_raw_title_from_standard_name(tmp_path, repo) -> None:
    """QED-036：review 不带 --title 时从规范名剥离「教程{set_no}：」前缀与（作者）后缀回退。"""
    import qed_tracker.cli as cli_module

    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="1", name="教程1：数学分析（Rudin）")
    args = _args(mainline_command="review", knowledge_id=knowledge.knowledge_id)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0

    updated = repo.get_knowledge(knowledge.knowledge_id)
    assert updated.textbook_ref["title"] == "数学分析"
    assert updated.textbook_ref["authors"] == []


def test_mainline_review_invalid_transition_returns_2(tmp_path, repo, capsys) -> None:
    import qed_tracker.cli as cli_module

    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="", name="数学分析原理")
    repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref={}, textbook_intro="x")
    args = _args(mainline_command="review", knowledge_id=knowledge.knowledge_id)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 2
    assert "状态迁移非法" in capsys.readouterr().err


def test_mainline_reject_persists_reason(tmp_path, repo, capsys) -> None:
    import qed_tracker.cli as cli_module

    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="", name="数学分析原理")
    args = _args(mainline_command="reject", knowledge_id=knowledge.knowledge_id, reason="非经典")
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0
    assert repo.get_knowledge(knowledge.knowledge_id) is None  # rejected 彻底隐藏
    assert repo.get_knowledge(knowledge.knowledge_id, include_hidden=True).reject_reason == "非经典"
    assert "已否定" in capsys.readouterr().out


def test_mainline_review_missing_knowledge_returns_2(tmp_path, repo, capsys) -> None:
    import qed_tracker.cli as cli_module

    args = _args(mainline_command="review", knowledge_id="kn_missing")
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 2
    assert "知识行不存在" in capsys.readouterr().err


def test_reject_missing_knowledge_returns_2(tmp_path, repo, capsys) -> None:
    import qed_tracker.cli as cli_module

    args = _args(mainline_command="reject", knowledge_id="kn_missing", reason="测试")
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 2
    assert "不存在" in capsys.readouterr().err


# ---------------- download ----------------

def test_mainline_download_happy_path(tmp_path, repo, monkeypatch, capsys) -> None:
    import qed_tracker.cli as cli_module

    monkeypatch.setattr(cli_module, "_book_service", lambda s: _FakeBookService(
        candidates=[Candidate("internet_archive", "ia-1", "数学分析原理",
                              download_url="https://example.test/book.pdf")],
    ))
    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="", name="数学分析原理")
    repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref={"title": "数学分析原理"}, textbook_intro="x")

    args = _args(mainline_command="download", knowledge_id=knowledge.knowledge_id)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0

    book = repo.list_books(knowledge.knowledge_id)[0]
    assert book.status == "downloaded"
    assert book.sha256 == "0" * 64
    assert book.relative_path == "raw/books/inbox/math_analysis.pdf"
    assert book.file_name == "math_analysis.pdf"
    assert book.page_count == 1
    assert "已下载" in capsys.readouterr().out
    sources = repo.list_sources(book.book_id)
    assert sources[-1].channel == "internet_archive"
    assert sources[-1].ok is True


def test_mainline_download_requires_confirmed(tmp_path, repo, monkeypatch, capsys) -> None:
    import qed_tracker.cli as cli_module

    monkeypatch.setattr(cli_module, "_book_service", lambda s: _FakeBookService())
    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="", name="数学分析原理")
    args = _args(mainline_command="download", knowledge_id=knowledge.knowledge_id)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 2
    assert "confirmed" in capsys.readouterr().err
    assert repo.list_books(knowledge.knowledge_id) == []


def test_mainline_download_no_candidates_returns_3(tmp_path, repo, monkeypatch, capsys) -> None:
    import qed_tracker.cli as cli_module

    candidate = Candidate(
        "libgen_li", "lg-1", "数学分析原理",
        availability=Availability.METADATA_ONLY,
        links=(DownloadLink("torrent", "https://example.test/book.torrent"),),
    )
    monkeypatch.setattr(cli_module, "_book_service", lambda s: _FakeBookService(candidates=[candidate]))
    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="", name="数学分析原理")
    repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref={"title": "数学分析原理"}, textbook_intro="x")

    args = _args(mainline_command="download", knowledge_id=knowledge.knowledge_id)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 3
    assert "人工下载指引" in capsys.readouterr().out

    book = repo.list_books(knowledge.knowledge_id)[0]
    assert book.status == "failed"  # 无候选也落 failed，可重试
    sources = repo.list_sources(book.book_id)
    assert sources[-1].channel == "search"
    assert sources[-1].ok is False


def test_mainline_download_failure_fails_book(tmp_path, repo, monkeypatch, capsys) -> None:
    import qed_tracker.cli as cli_module

    monkeypatch.setattr(cli_module, "_book_service", lambda s: _FakeBookService(error="来源不可用"))
    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="", name="数学分析原理")
    repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref={"title": "数学分析原理"}, textbook_intro="x")

    args = _args(mainline_command="download", knowledge_id=knowledge.knowledge_id)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 2
    assert "下载失败" in capsys.readouterr().err

    book = repo.list_books(knowledge.knowledge_id)[0]
    assert book.status == "failed"
    sources = repo.list_sources(book.book_id)
    assert sources[-1].channel == "download"
    assert sources[-1].ok is False
    assert "来源不可用" in sources[-1].note


def test_mainline_download_missing_knowledge_returns_2(tmp_path, repo, monkeypatch, capsys) -> None:
    import qed_tracker.cli as cli_module

    monkeypatch.setattr(cli_module, "_book_service", lambda s: _FakeBookService())
    args = _args(mainline_command="download", knowledge_id="kn_missing")
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 2
    assert "知识行不存在" in capsys.readouterr().err


def test_mainline_download_retry_from_failed(tmp_path, repo, monkeypatch) -> None:
    import qed_tracker.cli as cli_module

    calls: list[str] = []

    def fake(settings):
        calls.append("search")
        if len(calls) == 1:
            raise RuntimeError("首次失败")
        return _FakeBookService(candidates=[Candidate("internet_archive", "ia-1", "数学分析原理",
                                                      download_url="https://example.test/book.pdf")])

    monkeypatch.setattr(cli_module, "_book_service", fake)
    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="", name="数学分析原理")
    repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref={"title": "数学分析原理"}, textbook_intro="x")

    args = _args(mainline_command="download", knowledge_id=knowledge.knowledge_id)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 2
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0

    book = repo.list_books(knowledge.knowledge_id)[0]
    assert book.status == "downloaded"  # failed → downloading 重试成功


def test_download_already_downloaded_shortcircuits(tmp_path, repo, capsys) -> None:
    import qed_tracker.cli as cli_module

    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="", name="数学分析原理")
    repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref={"title": "数学分析原理"}, textbook_intro="x")
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", roles=["textbook"],
                            title="数学分析原理", authors=[])
    repo.decide_book(book.book_id)
    repo.start_download(book.book_id)
    repo.complete_download(book.book_id, sha256="0" * 64, relative_path="raw/books/inbox/math_analysis.pdf",
                           page_count=1, file_name="math_analysis.pdf")

    before = len(repo.list_sources(book.book_id))
    args = _args(mainline_command="download", knowledge_id=knowledge.knowledge_id)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0
    assert "已下载，请执行 verify" in capsys.readouterr().out
    assert len(repo.list_sources(book.book_id)) == before  # 已下载短路，不重新搜索
    assert repo.get_book(book.book_id).status == "downloaded"

    repo.verify_book(book.book_id)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0
    assert "已下载，请执行 approve" in capsys.readouterr().out


# ---------------- verify / approve ----------------

def test_mainline_verify_success(tmp_path, repo, monkeypatch, pdf_bytes, capsys) -> None:
    import qed_tracker.cli as cli_module

    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="", name="数学分析原理")
    repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref={"title": "数学分析原理"}, textbook_intro="x")
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", roles=["textbook"],
                            title="数学分析原理", authors=[])
    repo.decide_book(book.book_id)
    repo.start_download(book.book_id)
    pdf = tmp_path / "raw" / "books" / "inbox" / "math_analysis.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(pdf_bytes)
    repo.complete_download(book.book_id, sha256="0" * 64, relative_path="raw/books/inbox/math_analysis.pdf",
                           page_count=1, absolute_path=str(pdf), file_name=pdf.name)

    args = _args(mainline_command="verify", knowledge_id=knowledge.knowledge_id)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0
    assert repo.get_book(book.book_id).status == "verified"
    assert "已校验" in capsys.readouterr().out


def test_mainline_verify_missing_downloaded_book_returns_2(tmp_path, repo, monkeypatch, capsys) -> None:
    import qed_tracker.cli as cli_module

    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="", name="数学分析原理")
    repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref={"title": "数学分析原理"}, textbook_intro="x")
    args = _args(mainline_command="verify", knowledge_id=knowledge.knowledge_id)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 2
    assert "请先执行 download" in capsys.readouterr().err


def test_mainline_verify_missing_file_returns_3(tmp_path, repo, capsys) -> None:
    import qed_tracker.cli as cli_module

    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="", name="数学分析原理")
    repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref={"title": "数学分析原理"}, textbook_intro="x")
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", roles=["textbook"],
                            title="数学分析原理", authors=[])
    repo.decide_book(book.book_id)
    repo.start_download(book.book_id)
    repo.complete_download(book.book_id, sha256="0" * 64, relative_path="raw/books/inbox/missing.pdf")

    args = _args(mainline_command="verify", knowledge_id=knowledge.knowledge_id)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 3
    assert "文件不存在" in capsys.readouterr().err


def test_mainline_approve_copies_and_completes(tmp_path, repo, monkeypatch, pdf_bytes, capsys) -> None:
    import qed_tracker.cli as cli_module

    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="", name="数学分析原理")
    repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref={"title": "数学分析原理"}, textbook_intro="x")
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", roles=["textbook"],
                            title="数学分析原理", authors=[])
    repo.decide_book(book.book_id)
    repo.start_download(book.book_id)
    pdf = tmp_path / "raw" / "books" / "inbox" / "math_analysis.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(pdf_bytes)
    repo.complete_download(book.book_id, sha256="0" * 64, relative_path="raw/books/inbox/math_analysis.pdf",
                           page_count=1, absolute_path=str(pdf), file_name=pdf.name)
    repo.verify_book(book.book_id)

    args = _args(mainline_command="approve", knowledge_id=knowledge.knowledge_id)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0

    # ARCH-019 共享布局：移交目标 raw/<domain>/<course>/
    target = tmp_path / "raw" / "math" / "01_math_analysis" / "math_analysis.pdf"
    assert target.is_file()
    assert target.read_bytes() == pdf_bytes
    assert repo.get_knowledge(knowledge.knowledge_id).status == "completed"  # 全部书行 verified 后自动完成
    assert "验收通过" in capsys.readouterr().out


def test_mainline_approve_requires_verified_book(tmp_path, repo, monkeypatch, capsys) -> None:
    import qed_tracker.cli as cli_module

    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="", name="数学分析原理")
    repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref={"title": "数学分析原理"}, textbook_intro="x")
    args = _args(mainline_command="approve", knowledge_id=knowledge.knowledge_id)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 2
    assert "请先执行 verify" in capsys.readouterr().err


def test_approve_verify_specific_book_multi_volume(tmp_path, repo, monkeypatch, pdf_bytes, capsys) -> None:
    import qed_tracker.cli as cli_module

    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="", name="数学分析原理")
    repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref={"title": "数学分析原理"}, textbook_intro="x")
    first = repo.create_book(knowledge.knowledge_id, kind="textbook", roles=["textbook"],
                             title="数学分析原理", part="第一册", authors=[])
    second = repo.create_book(knowledge.knowledge_id, kind="textbook", roles=["textbook"],
                              title="数学分析原理", part="第二册", authors=[])
    vol1 = tmp_path / "raw" / "books" / "inbox" / "vol1.pdf"
    vol2 = tmp_path / "raw" / "books" / "inbox" / "vol2.pdf"
    vol1.parent.mkdir(parents=True, exist_ok=True)
    vol1.write_bytes(pdf_bytes)
    vol2.write_bytes(pdf_bytes)
    for book, pdf, digest in ((first, vol1, "1" * 64), (second, vol2, "2" * 64)):
        repo.decide_book(book.book_id)
        repo.start_download(book.book_id)
        repo.complete_download(book.book_id, sha256=digest, relative_path=f"raw/books/inbox/{pdf.name}",
                               page_count=1, absolute_path=str(pdf), file_name=pdf.name)

    settings = _settings(tmp_path)
    # 指定书行 verify → approve：vol1 移交，但 vol2 未 verified，知识行不完成（提示）
    assert cli_module._mainline_impl(
        _args(mainline_command="verify", knowledge_id=knowledge.knowledge_id, book=first.book_id),
        repo, settings) == 0
    assert repo.get_book(first.book_id).status == "verified"
    assert cli_module._mainline_impl(
        _args(mainline_command="approve", knowledge_id=knowledge.knowledge_id, book=first.book_id),
        repo, settings) == 0
    target1 = tmp_path / "raw" / "math" / "01_math_analysis" / "vol1.pdf"
    assert target1.is_file()
    assert target1.read_bytes() == pdf_bytes
    assert repo.get_knowledge(knowledge.knowledge_id).status == "confirmed"
    assert "书行全 verified 后可再次 approve" in capsys.readouterr().err
    # 缺省 approve：唯一 verified 的 vol1 已移交 → 无新目标，exit 2（死锁防护，不重复复制）
    assert cli_module._mainline_impl(
        _args(mainline_command="approve", knowledge_id=knowledge.knowledge_id),
        repo, settings) == 2
    assert "移交目标已存在" in capsys.readouterr().err
    assert target1.is_file()
    assert target1.read_bytes() == pdf_bytes
    assert repo.get_knowledge(knowledge.knowledge_id).status == "confirmed"
    # 第二册 verify → approve → 全部书行 verified，知识行完成
    assert cli_module._mainline_impl(
        _args(mainline_command="verify", knowledge_id=knowledge.knowledge_id, book=second.book_id),
        repo, settings) == 0
    assert cli_module._mainline_impl(
        _args(mainline_command="approve", knowledge_id=knowledge.knowledge_id, book=second.book_id),
        repo, settings) == 0
    target2 = tmp_path / "raw" / "math" / "01_math_analysis" / "vol2.pdf"
    assert target2.is_file()
    assert target2.read_bytes() == pdf_bytes
    assert repo.get_knowledge(knowledge.knowledge_id).status == "completed"


def test_approve_missing_source_file_returns_3(tmp_path, repo, monkeypatch, capsys) -> None:
    import qed_tracker.cli as cli_module

    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="", name="数学分析原理")
    repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref={"title": "数学分析原理"}, textbook_intro="x")
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", roles=["textbook"],
                            title="数学分析原理", authors=[])
    repo.decide_book(book.book_id)
    repo.start_download(book.book_id)
    repo.complete_download(book.book_id, sha256="0" * 64, relative_path="raw/books/inbox/missing.pdf",
                           page_count=1, absolute_path=str(tmp_path / "raw" / "books" / "inbox" / "missing.pdf"),
                           file_name="missing.pdf")
    repo.verify_book(book.book_id)

    args = _args(mainline_command="approve", knowledge_id=knowledge.knowledge_id)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 3
    assert "文件不存在" in capsys.readouterr().err


# ---------------- 全链路 ----------------

def test_mainline_full_flow(tmp_path, repo, monkeypatch, pdf_bytes) -> None:
    import qed_tracker.cli as cli_module

    monkeypatch.setattr(cli_module, "_book_service", lambda s: _FakeBookService(
        candidates=[Candidate("internet_archive", "ia-1", "数学分析原理",
                              download_url="https://example.test/book.pdf")],
        data_root=tmp_path, pdf_bytes=pdf_bytes,
    ))
    monkeypatch.setattr(cli_module, "_mainline_advisor", lambda **kw: _FakeAdvisor())
    settings = _settings(tmp_path)

    assert cli_module._mainline_impl(
        _args(mainline_command="new", course="01_math_analysis", title="数学分析原理", author=["Rudin"]),
        repo, settings) == 0
    knowledge = repo.list_knowledge(course_id="01_math_analysis")[0]
    assert knowledge.status == "draft"

    assert cli_module._mainline_impl(
        _args(mainline_command="review", knowledge_id=knowledge.knowledge_id), repo, settings) == 0
    assert repo.get_knowledge(knowledge.knowledge_id).status == "confirmed"

    assert cli_module._mainline_impl(
        _args(mainline_command="download", knowledge_id=knowledge.knowledge_id), repo, settings) == 0
    book = repo.list_books(knowledge.knowledge_id)[0]
    assert book.status == "downloaded"

    assert cli_module._mainline_impl(
        _args(mainline_command="verify", knowledge_id=knowledge.knowledge_id), repo, settings) == 0
    assert repo.get_book(book.book_id).status == "verified"

    assert cli_module._mainline_impl(
        _args(mainline_command="approve", knowledge_id=knowledge.knowledge_id), repo, settings) == 0
    assert repo.get_knowledge(knowledge.knowledge_id).status == "completed"
    target = tmp_path / "raw" / "math" / "01_math_analysis" / "math_analysis.pdf"
    assert target.is_file()
    assert target.read_bytes() == pdf_bytes


# ---------------- list / channels ----------------

def test_mainline_list_shows_books(tmp_path, repo, capsys) -> None:
    import qed_tracker.cli as cli_module

    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="1", name="数学分析 套一")
    repo.create_book(knowledge.knowledge_id, kind="textbook", roles=["textbook"],
                     title="数学分析 套一", authors=[])
    args = _args(mainline_command="list", course="01_math_analysis")
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0
    out = capsys.readouterr().out
    assert knowledge.knowledge_id in out
    assert "数学分析 套一" in out


def test_mainline_list_json(tmp_path, repo, capsys) -> None:
    import qed_tracker.cli as cli_module

    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="", name="数学分析原理")
    repo.create_book(knowledge.knowledge_id, kind="textbook", roles=["textbook"],
                     title="数学分析原理", authors=[])
    args = _args(mainline_command="list", course="01_math_analysis", json=True)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["knowledge_id"] == knowledge.knowledge_id
    assert payload[0]["books"][0]["status"] == "candidate"


def test_mainline_channels_aggregates(tmp_path, repo, capsys) -> None:
    import qed_tracker.cli as cli_module

    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="", name="数学分析原理")
    repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref={"title": "数学分析原理"}, textbook_intro="x")
    first = repo.create_book(knowledge.knowledge_id, kind="textbook", roles=["textbook"],
                             title="数学分析原理", authors=[])
    second = repo.create_book(knowledge.knowledge_id, kind="textbook", roles=["textbook"],
                              title="数学分析原理", part="第一册", authors=[])
    repo.add_source(first.book_id, channel="internet_archive", ok=True, note="sha256:a")
    repo.add_source(first.book_id, channel="google_books", ok=False, note="429")
    repo.add_source(second.book_id, channel="internet_archive", ok=False, note="404")

    args = _args(mainline_command="channels")
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0
    out = capsys.readouterr().out
    assert "internet_archive" in out
    assert "google_books" in out
    assert "成功" in out


def test_mainline_channels_json(tmp_path, repo, capsys) -> None:
    import qed_tracker.cli as cli_module

    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="", name="数学分析原理")
    first = repo.create_book(knowledge.knowledge_id, kind="textbook", roles=["textbook"],
                             title="数学分析原理", authors=[])
    second = repo.create_book(knowledge.knowledge_id, kind="textbook", roles=["textbook"],
                              title="数学分析原理", part="第一册", authors=[])
    repo.add_source(first.book_id, channel="internet_archive", ok=True, note="")
    repo.add_source(second.book_id, channel="internet_archive", ok=False, note="404")

    args = _args(mainline_command="channels", json=True)
    assert cli_module._mainline_impl(args, repo, _settings(tmp_path)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["channels"]["internet_archive"] == {"ok": 1, "fail": 1}


# ---------------- migrate ----------------

def test_migrate_command_happy_path(tmp_path, monkeypatch, capsys) -> None:
    import qed_tracker.database as database_module

    engine = create_engine(f"sqlite:///{tmp_path / 'migrate.db'}")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE qt_selections (selection_id VARCHAR(100) PRIMARY KEY, course_id VARCHAR(64),"
            " title VARCHAR(500), authors JSON, roles JSON, version JSON, vols JSON, set_no VARCHAR(4),"
            " evaluation JSON, note VARCHAR(1000), status VARCHAR(24), reject_reason VARCHAR(1000),"
            " rejected_by VARCHAR(16), supersede_reason VARCHAR(1000), created_at DATETIME,"
            " confirmed_at DATETIME, superseded_at DATETIME, rejected_at DATETIME)"
        ))
        conn.execute(text(
            "CREATE TABLE qt_downloads (download_id VARCHAR(100) PRIMARY KEY, selection_id VARCHAR(100),"
            " vol VARCHAR(32), roles JSON, file_hint VARCHAR(200), sha256 VARCHAR(64),"
            " relative_path VARCHAR(500), page_count INT, status VARCHAR(24), reject_reason VARCHAR(1000),"
            " rejected_by VARCHAR(16), review_note VARCHAR(1000), created_at DATETIME,"
            " downloaded_at DATETIME, approved_at DATETIME, rejected_at DATETIME)"
        ))
        conn.execute(text(
            "CREATE TABLE qt_sources (source_id VARCHAR(100) PRIMARY KEY, download_id VARCHAR(100),"
            " channel VARCHAR(24), provider_id VARCHAR(200), page_url VARCHAR(1000),"
            " download_url VARCHAR(1000), file_keywords VARCHAR(500), ok TINYINT(1),"
            " note VARCHAR(1000), attempted_at DATETIME)"
        ))
        conn.execute(text(
            "INSERT INTO qt_selections VALUES"
            " ('cand_1','01_math_analysis','微积分学教程',"
            " json_array('菲赫金哥尔茨'),json_array('textbook'),json_object('edition','第8版'),"
            " json_array('v1'),'2','', '', 'confirmed','','','',"
            " '2026-08-01 10:00:00','2026-08-02 10:00:00',NULL,NULL)"
        ))
        conn.execute(text(
            "INSERT INTO qt_downloads VALUES"
            " ('dl_1','cand_1','v1',json_array('textbook'),'',"
            " 'aaaa','raw/books/math-qe/01_math_analysis/x_v1.pdf',100,'downloaded','','','',"
            " '2026-08-01 10:00:00','2026-08-03 10:00:00',NULL,NULL)"
        ))
        conn.execute(text(
            "INSERT INTO qt_sources VALUES"
            " ('src_1','dl_1','manual','','','http://x','',1,'','2026-08-03 10:00:00')"
        ))
    Base.metadata.create_all(engine)
    monkeypatch.setattr(database_module, "create_engine_for", lambda settings: engine)
    monkeypatch.setenv("QED_DB_PASSWORD", "test")

    assert main(["--data-root", str(tmp_path), "migrate"]) == 0
    assert "迁移完成" in capsys.readouterr().out

    with engine.begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM qt_knowledge")).fetchone()[0] == 1
        assert conn.execute(text("SELECT COUNT(*) FROM qt_books")).fetchone()[0] == 1
        assert conn.execute(text("SELECT COUNT(*) FROM qt_sources")).fetchone()[0] == 1
        assert conn.execute(text("SELECT COUNT(*) FROM qed_domain")).fetchone()[0] >= 1
    engine.dispose()
