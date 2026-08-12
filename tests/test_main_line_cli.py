from __future__ import annotations

import json
from pathlib import Path

import httpx

from qed_tracker.cli import build_parser, main
from qed_tracker.main_line.store import EntryStore


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


def test_mainline_list_empty_returns_0(tmp_path, capsys) -> None:
    assert main(["--data-root", str(tmp_path), "mainline", "list", "--course", "01_math_analysis"]) == 0
    assert capsys.readouterr().out == ""


def _run_mainline_new(tmp_path: Path, monkeypatch, handler) -> dict:
    import qed_tracker.cli as cli_module
    from qed_tracker.cli import main as cli_main

    monkeypatch.setenv("QWEN_API_KEY", "test-key")

    def fake_advisor(*, api_key, model, base_url, timeout, call_budget, max_tokens, client=None):
        from qed_tracker.main_line.advisor import MainLineAdvisor
        return MainLineAdvisor(
            api_key=api_key, model=model, base_url=base_url, timeout=timeout,
            call_budget=call_budget, max_tokens=max_tokens,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr(cli_module, "_mainline_advisor", fake_advisor)
    result = cli_main(
        ["--data-root", str(tmp_path), "mainline", "new",
         "--course", "01_math_analysis", "--title", "数学分析原理"],
    )
    return result


def test_mainline_new_creates_entry_with_llm_prefill(tmp_path: Path, monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = {
            "evaluation": {"text": "经典教材", "authority": "高", "set_candidate": "套一"},
            "advice": {"download": "recommended", "reason": "MIT 指定"},
        }
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}, "finish_reason": "stop"}]})

    result = _run_mainline_new(tmp_path, monkeypatch, handler)
    assert result == 0
    store = EntryStore(tmp_path)
    entries = store.list_course("01_math_analysis")
    assert len(entries) == 1
    entry = entries[0]
    assert entry.evaluation["authority"] == "高"
    assert entry.evaluation["source"] == "llm"
    assert entry.status == "draft"


def test_mainline_review_transitions_to_reviewed(tmp_path: Path) -> None:
    from qed_tracker.cli import main as cli_main

    store = EntryStore(tmp_path)
    store.create({"entry_id": "e1", "course_id": "01_math_analysis", "title": "T1", "authors": []})
    result = cli_main(["--data-root", str(tmp_path), "mainline", "review", "01_math_analysis", "e1"])
    assert result == 0
    entry = store.get("01_math_analysis", "e1")
    assert entry.status == "reviewed"


def test_mainline_reject_with_reason(tmp_path: Path) -> None:
    from qed_tracker.cli import main as cli_main

    store = EntryStore(tmp_path)
    store.create({"entry_id": "e1", "course_id": "01_math_analysis", "title": "T1", "authors": []})
    result = cli_main(["--data-root", str(tmp_path), "mainline", "reject", "01_math_analysis", "e1", "--reason", "非经典"])
    assert result == 0
    entry = store.get("01_math_analysis", "e1")
    assert entry.status == "rejected"
