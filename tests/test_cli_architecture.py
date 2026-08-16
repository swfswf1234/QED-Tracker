from pathlib import Path
from types import SimpleNamespace

from qed_tracker.application.books import RankedCandidate
from qed_tracker.cli import build_parser, main
from qed_tracker.models import Candidate


def test_cli_exposes_focused_commands():
    parser = build_parser()
    assert parser.parse_args(["books", "get", "Topology"]).books_command == "get"
    assert parser.parse_args(["papers", "get", "2401.00001"]).papers_command == "get"
    recommend = parser.parse_args(["papers", "recommend", "RAG", "--profile", "llm-engineering", "--top", "5"])
    assert recommend.papers_command == "recommend" and recommend.top == 5
    selection = parser.parse_args(["papers", "selections", "download", "sel-20260730T000000Z-12345678", "--pick", "1"])
    assert selection.selections_command == "download" and selection.pick == [1]
    assert parser.parse_args(["catalog", "run", "math-qe", "--download"]).download
    assert parser.parse_args(["axiom", "push", "sha256:abc", "--parse"]).parse


def test_removed_cli_commands_are_not_exposed():
    parser = build_parser()
    for argv in (["books", "search", "Topology"], ["inventory", "export"]):
        try:
            parser.parse_args(argv)
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError(f"removed command still accepted: {argv}")


def test_books_get_previews_without_pick_and_downloads_with_pick(monkeypatch, tmp_path, capsys):
    services = []

    class FakeBookService:
        failures = []

        def __init__(self):
            self.candidate = Candidate("open", "1", "Open Textbook", download_url="https://example.test/book.pdf")
            self.downloaded = []
            self.closed = False

        def search(self, query, *, limit=10):
            return [RankedCandidate(self.candidate)]

        def download(self, candidate, *, kind):
            self.downloaded.append((candidate, kind))
            return SimpleNamespace(to_dict=lambda: {"resource_id": "sha256:test"})

        def close(self):
            self.closed = True

    def factory(settings, names=None):
        service = FakeBookService()
        services.append(service)
        return service

    monkeypatch.setattr("qed_tracker.cli._book_service", factory)

    assert main(["--data-root", str(tmp_path), "books", "get", "Topology"]) == 0
    assert "Open Textbook" in capsys.readouterr().out
    assert services[0].downloaded == []
    assert services[0].closed

    assert main(["--data-root", str(tmp_path), "books", "get", "Topology", "--pick", "1"]) == 0
    assert services[1].downloaded[0][0].title == "Open Textbook"
    assert services[1].closed


def test_cli_catalog_and_config_are_usable(tmp_path, capsys):
    assert main(["--data-root", str(tmp_path), "catalog", "list"]) == 0
    assert "math-qe" in capsys.readouterr().out
    assert main(["--data-root", str(tmp_path), "config", "show"]) == 0
    assert "data_root" in capsys.readouterr().out
    assert main(["papers", "profiles", "list"]) == 0
    assert "llm-engineering" in capsys.readouterr().out


def test_axiom_page_range_requires_parse(tmp_path, capsys):
    result = main(["--data-root", str(tmp_path), "axiom", "push", "sha256:abc", "--page-start", "2"])
    assert result == 5
    assert "只能与 --parse" in capsys.readouterr().err


def test_serve_runs_uvicorn_with_created_app(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr("qed_tracker.cli._load_root_env", lambda start: None)
    monkeypatch.setattr("qed_tracker.cli.upgrade_database", lambda settings: None)
    monkeypatch.setattr("qed_tracker.cli._configure_serve_logging", lambda log_dir: None)
    fake_app = object()
    monkeypatch.setattr("qed_tracker.api.main.create_app", lambda settings, **kwargs: fake_app)
    monkeypatch.setattr("qed_tracker.cli.uvicorn.run", lambda app, **kwargs: captured.update({"app": app} | kwargs))
    assert main(["--data-root", str(tmp_path), "serve", "--port", "8901"]) == 0
    assert captured["app"] is fake_app
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8901


def test_serve_continues_when_database_migration_fails(monkeypatch, tmp_path, capsys):
    def boom(settings):
        raise RuntimeError("MySQL 不可用")

    monkeypatch.setattr("qed_tracker.cli._load_root_env", lambda start: None)
    monkeypatch.setattr("qed_tracker.cli.upgrade_database", boom)
    monkeypatch.setattr("qed_tracker.cli._configure_serve_logging", lambda log_dir: None)
    monkeypatch.setattr("qed_tracker.api.main.create_app", lambda settings, **kwargs: object())
    monkeypatch.setattr("qed_tracker.cli.uvicorn.run", lambda app, **kwargs: None)
    assert main(["--data-root", str(tmp_path), "serve", "--port", "8901"]) == 0
    assert "MySQL" in capsys.readouterr().err


def test_configure_serve_logging_writes_to_logs_dir(tmp_path):
    """serve 日志落盘传入 log_dir（生产为仓库根 logs/），root 挂 FileHandler 后幂等跳过。"""
    import logging

    from qed_tracker.cli import _configure_serve_logging

    root = logging.getLogger()
    original_handlers = list(root.handlers)
    try:
        root.handlers.clear()  # 隔离其他测试已挂的 handler，防止幂等跳过
        _configure_serve_logging(tmp_path)
        log_file = tmp_path / "qed-tracker.log"
        assert log_file.exists()
        logging.getLogger().info("serve-log-probe")
        assert "serve-log-probe" in log_file.read_text(encoding="utf-8")
        # 幂等：再次调用不重复挂 handler
        before = len(logging.getLogger().handlers)
        _configure_serve_logging(tmp_path)
        assert len(logging.getLogger().handlers) == before
    finally:
        root.handlers[:] = original_handlers


def test_serve_loads_root_env_into_environment(monkeypatch, tmp_path):
    """serve 独立启动时自动注入根 .env 的 QED_* 与密钥（不覆盖已显式设置的环境变量）。"""
    import os as os_module

    from qed_tracker import cli as cli_module

    monkeypatch.delenv("QED_DB_PASSWORD", raising=False)
    (tmp_path / ".env").write_text("QED_DB_PASSWORD=secret123\nQWEN_API_KEY=sk-env\n", encoding="utf-8")
    monkeypatch.setenv("QWEN_API_KEY", "explicit")
    try:
        assert cli_module._load_root_env(tmp_path) == tmp_path / ".env"
        assert os_module.environ["QED_DB_PASSWORD"] == "secret123"
    finally:
        os_module.environ.pop("QED_DB_PASSWORD", None)  # 清理注入，避免污染其他测试
    assert os_module.environ["QWEN_API_KEY"] == "explicit"  # 已有值不被覆盖

    # main(serve) 以 cwd 为查找起点调用 _load_root_env
    seen = []
    monkeypatch.setattr("qed_tracker.cli._load_root_env", lambda start: seen.append(start) or None)
    monkeypatch.setattr("qed_tracker.cli.upgrade_database", lambda settings: None)
    monkeypatch.setattr("qed_tracker.cli._configure_serve_logging", lambda log_dir: None)
    monkeypatch.setattr("qed_tracker.api.main.create_app", lambda settings, **kwargs: object())
    monkeypatch.setattr("qed_tracker.cli.uvicorn.run", lambda app, **kwargs: None)
    assert main(["--data-root", str(tmp_path), "serve"]) == 0
    assert seen == [Path.cwd()]
    os_module.environ.pop("QED_DB_PASSWORD", None)  # 清理注入，避免污染其他测试


def test_production_package_has_no_removed_runtime_dependencies():
    root = Path(__file__).parents[1]
    source = "\n".join(path.read_text(encoding="utf-8") for path in (root / "src" / "qed_tracker").rglob("*.py"))
    for forbidden in ("psycopg2", "from app", "import app"):
        assert forbidden not in source.lower()
    assert not list((root / "app").rglob("*.py"))
    assert not list((root / "scripts").rglob("*.py"))
