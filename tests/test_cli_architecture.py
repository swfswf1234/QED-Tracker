from pathlib import Path

from qed_tracker.cli import build_parser, main


def test_cli_exposes_focused_commands():
    parser = build_parser()
    assert parser.parse_args(["books", "search", "Topology"]).books_command == "search"
    assert parser.parse_args(["papers", "get", "2401.00001"]).papers_command == "get"
    assert parser.parse_args(["catalog", "run", "math-qe", "--download"]).download
    assert parser.parse_args(["axiom", "push", "sha256:abc", "--parse"]).parse


def test_cli_catalog_and_config_are_usable(tmp_path, capsys):
    assert main(["--data-root", str(tmp_path), "catalog", "list"]) == 0
    assert "math-qe" in capsys.readouterr().out
    config = tmp_path / "local.toml"
    assert main(["config", "init", "--path", str(config), "--data-root", str(tmp_path)]) == 0
    assert config.exists()
    assert "data_root" in config.read_text(encoding="utf-8")


def test_axiom_page_range_requires_parse(tmp_path, capsys):
    result = main(["--data-root", str(tmp_path), "axiom", "push", "sha256:abc", "--page-start", "2"])
    assert result == 5
    assert "只能与 --parse" in capsys.readouterr().err


def test_production_package_has_no_removed_runtime_dependencies():
    root = Path(__file__).parents[1]
    source = "\n".join(path.read_text(encoding="utf-8") for path in (root / "src" / "qed_tracker").rglob("*.py"))
    for forbidden in ("fastapi", "sqlalchemy", "pymysql", "psycopg2", "from app", "import app"):
        assert forbidden not in source.lower()
    assert not list((root / "app").rglob("*.py"))
    assert not list((root / "scripts").rglob("*.py"))
