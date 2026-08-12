from __future__ import annotations

from qed_tracker.cli import build_parser, main


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


def test_courses_show_resolves_course_id_to_subject(tmp_path, capsys) -> None:
    assert main(["--data-root", str(tmp_path), "courses", "show", "01_math_analysis"]) == 0
    out = capsys.readouterr().out
    assert "数学" in out
    assert out.count("\n") >= 14


def test_courses_show_unknown_errors(tmp_path, capsys) -> None:
    assert main(["--data-root", str(tmp_path), "courses", "show", "nope"]) == 2
    assert "未知" in capsys.readouterr().err
