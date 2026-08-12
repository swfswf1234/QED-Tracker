from __future__ import annotations

import json

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


def test_courses_list_outputs_subjects(tmp_path, capsys) -> None:
    assert main(["--data-root", str(tmp_path), "courses", "list"]) == 0
    out = capsys.readouterr().out
    assert "math" in out


def test_courses_show_unknown_json_structured_error(tmp_path, capsys) -> None:
    assert main(["--data-root", str(tmp_path), "--json", "courses", "show", "nope"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"].startswith("未知学科课程体系")
    assert "nope" in payload["error"]


def test_mainline_list_placeholder_returns_2(tmp_path, capsys) -> None:
    assert main(["--data-root", str(tmp_path), "mainline", "list", "--course", "01_math_analysis"]) == 2
    assert "未实现" in capsys.readouterr().err
