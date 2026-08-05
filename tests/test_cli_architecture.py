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


def test_production_package_has_no_removed_runtime_dependencies():
    root = Path(__file__).parents[1]
    source = "\n".join(path.read_text(encoding="utf-8") for path in (root / "src" / "qed_tracker").rglob("*.py"))
    for forbidden in ("psycopg2", "from app", "import app"):
        assert forbidden not in source.lower()
    assert not list((root / "app").rglob("*.py"))
    assert not list((root / "scripts").rglob("*.py"))
