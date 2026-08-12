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


def _run_mainline_new(tmp_path: Path, monkeypatch, handler, title: str = "数学分析原理") -> int:
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
    return cli_main(
        ["--data-root", str(tmp_path), "mainline", "new",
         "--course", "01_math_analysis", "--title", title],
    )


def _prefill_response() -> dict:
    return {
        "evaluation": {"text": "经典教材", "authority": "高", "set_candidate": "套一"},
        "advice": {"download": "recommended", "reason": "MIT 指定"},
    }


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


def test_mainline_new_chinese_title_unique_slug(tmp_path: Path, monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(_prefill_response(), ensure_ascii=False)}, "finish_reason": "stop"}]})

    result = _run_mainline_new(tmp_path, monkeypatch, handler, title="数学分析原理")
    assert result == 0
    result = _run_mainline_new(tmp_path, monkeypatch, handler, title="数学分析教程")
    assert result == 0
    store = EntryStore(tmp_path)
    entries = store.list_course("01_math_analysis")
    assert len(entries) == 2
    assert entries[0].entry_id != entries[1].entry_id


def test_mainline_new_duplicate_entry_no_llm_call(tmp_path: Path, monkeypatch) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(_prefill_response(), ensure_ascii=False)}, "finish_reason": "stop"}]})

    result = _run_mainline_new(tmp_path, monkeypatch, handler)
    assert result == 0
    assert len(calls) == 1
    result = _run_mainline_new(tmp_path, monkeypatch, handler)
    assert result == 2
    assert len(calls) == 1


def test_mainline_review_transitions_to_reviewed(tmp_path: Path) -> None:
    from qed_tracker.cli import main as cli_main

    store = EntryStore(tmp_path)
    store.create({"entry_id": "e1", "course_id": "01_math_analysis", "title": "T1", "authors": []})
    result = cli_main(["--data-root", str(tmp_path), "mainline", "review", "01_math_analysis", "e1"])
    assert result == 0
    entry = store.get("01_math_analysis", "e1")
    assert entry.status == "reviewed"


def test_mainline_reject_persists_reason(tmp_path: Path) -> None:
    from qed_tracker.cli import main as cli_main

    store = EntryStore(tmp_path)
    store.create({"entry_id": "e1", "course_id": "01_math_analysis", "title": "T1", "authors": []})
    result = cli_main(["--data-root", str(tmp_path), "mainline", "reject", "01_math_analysis", "e1", "--reason", "非经典"])
    assert result == 0
    entry = store.get("01_math_analysis", "e1")
    assert entry.status == "rejected"
    assert entry.reject_reason == "非经典"


def test_channel_summary_aggregates(tmp_path: Path) -> None:
    store = EntryStore(tmp_path)
    store.create({
        "entry_id": "e1", "course_id": "01_math_analysis", "title": "T1", "authors": [],
        "channels": [
            {"channel": "internet_archive", "ok": True, "note": ""},
            {"channel": "google_books", "ok": False, "note": "429"},
        ],
    })
    stats = store.channel_stats()
    assert stats["internet_archive"] == {"ok": 1, "fail": 0}
    assert stats["google_books"] == {"ok": 0, "fail": 1}


def _record_with(path: str):
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
        file={"sha256": "0" * 64, "relative_path": path},
    )


def test_mainline_download_success(tmp_path: Path, monkeypatch, capsys) -> None:
    from qed_tracker.application.books import RankedCandidate
    from qed_tracker.cli import main as cli_main
    from qed_tracker.main_line.store import MainLineStatus
    from qed_tracker.models import Candidate

    candidate = Candidate("internet_archive", "ia-1", "数学分析原理", download_url="https://example.test/book.pdf")

    class FakeBookService:
        failures: list[tuple[str, str]] = []

        def search(self, query, *, limit=10):
            return [RankedCandidate(candidate)]

        def download(self, candidate, *, kind):
            return _record_with("raw/books/inbox/math_analysis.pdf")

        def close(self):
            pass

    import qed_tracker.cli as cli_module

    monkeypatch.setattr(cli_module, "_book_service", lambda settings: FakeBookService())
    store = EntryStore(tmp_path)
    store.create({"entry_id": "e1", "course_id": "01_math_analysis", "title": "数学分析原理", "authors": ["Rudin"]})
    store.transition("01_math_analysis", "e1", MainLineStatus.REVIEWED)
    result = cli_main(["--data-root", str(tmp_path), "mainline", "download", "01_math_analysis", "e1"])
    assert result == 0
    assert "已下载" in capsys.readouterr().out
    entry = store.get("01_math_analysis", "e1")
    assert entry.status == MainLineStatus.DOWNLOADED.value
    assert entry.resource_id == "sha256:test"
    assert entry.final_path == str(tmp_path / "raw/books/inbox/math_analysis.pdf")
    assert entry.channels[-1]["channel"] == "internet_archive"
    assert entry.channels[-1]["ok"] is True
    assert entry.channels[-1]["note"] == "sha256:test"


def test_mainline_download_no_candidates_returns_3(tmp_path: Path, monkeypatch, capsys) -> None:
    from qed_tracker.application.books import RankedCandidate
    from qed_tracker.cli import main as cli_main
    from qed_tracker.main_line.store import MainLineStatus
    from qed_tracker.models import Availability, Candidate, DownloadLink

    candidate = Candidate(
        "libgen_li", "lg-1", "数学分析原理",
        availability=Availability.METADATA_ONLY,
        links=(DownloadLink("torrent", "https://example.test/book.torrent"),),
    )

    class FakeBookService:
        failures: list[tuple[str, str]] = []

        def search(self, query, *, limit=10):
            return [RankedCandidate(candidate)]

        def close(self):
            pass

    import qed_tracker.cli as cli_module

    monkeypatch.setattr(cli_module, "_book_service", lambda settings: FakeBookService())
    store = EntryStore(tmp_path)
    store.create({"entry_id": "e1", "course_id": "01_math_analysis", "title": "数学分析原理", "authors": []})
    store.transition("01_math_analysis", "e1", MainLineStatus.REVIEWED)
    result = cli_main(["--data-root", str(tmp_path), "mainline", "download", "01_math_analysis", "e1"])
    assert result == 3
    assert "人工下载指引" in capsys.readouterr().out
    entry = store.get("01_math_analysis", "e1")
    assert entry.channels[-1]["channel"] == "search"
    assert entry.channels[-1]["ok"] is False
    assert entry.channels[-1]["note"] == "无自动可下载候选"


def test_mainline_download_failure_records_channel(tmp_path: Path, monkeypatch) -> None:
    from qed_tracker.cli import main as cli_main
    from qed_tracker.main_line.store import MainLineStatus

    class FakeBookService:
        failures: list[tuple[str, str]] = []

        def search(self, query, *, limit=10):
            raise RuntimeError("来源不可用")

        def close(self):
            pass

    import qed_tracker.cli as cli_module

    monkeypatch.setattr(cli_module, "_book_service", lambda settings: FakeBookService())
    store = EntryStore(tmp_path)
    store.create({"entry_id": "e1", "course_id": "01_math_analysis", "title": "数学分析原理", "authors": []})
    store.transition("01_math_analysis", "e1", MainLineStatus.REVIEWED)
    result = cli_main(["--data-root", str(tmp_path), "mainline", "download", "01_math_analysis", "e1"])
    assert result == 2
    entry = store.get("01_math_analysis", "e1")
    assert entry.channels[-1]["channel"] == "download"
    assert entry.channels[-1]["ok"] is False
    assert "来源不可用" in entry.channels[-1]["note"]


def test_mainline_download_missing_entry_returns_2(tmp_path: Path, capsys) -> None:
    from qed_tracker.cli import main as cli_main

    result = cli_main(["--data-root", str(tmp_path), "mainline", "download", "01_math_analysis", "nope"])
    assert result == 2
    assert "条目不存在" in capsys.readouterr().err


def test_mainline_verify_success(tmp_path: Path, capsys, pdf_bytes: bytes) -> None:
    from qed_tracker.cli import main as cli_main

    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(pdf_bytes)
    store = EntryStore(tmp_path)
    store.create({"entry_id": "e1", "course_id": "01_math_analysis", "title": "T1", "authors": [], "final_path": str(pdf)})
    result = cli_main(["--data-root", str(tmp_path), "mainline", "verify", "01_math_analysis", "e1"])
    assert result == 0
    out = capsys.readouterr().out
    assert "sha256=" in out
    assert "页" in out


def test_mainline_verify_missing_file_returns_3(tmp_path: Path, capsys) -> None:
    from qed_tracker.cli import main as cli_main

    store = EntryStore(tmp_path)
    store.create({
        "entry_id": "e1", "course_id": "01_math_analysis", "title": "T1", "authors": [],
        "final_path": str(tmp_path / "missing.pdf"),
    })
    result = cli_main(["--data-root", str(tmp_path), "mainline", "verify", "01_math_analysis", "e1"])
    assert result == 3
    assert "文件不存在" in capsys.readouterr().err


def test_mainline_verify_invalid_pdf_returns_2(tmp_path: Path, capsys) -> None:
    from qed_tracker.cli import main as cli_main

    pdf = tmp_path / "fake.pdf"
    pdf.write_text("not a pdf", encoding="utf-8")
    store = EntryStore(tmp_path)
    store.create({"entry_id": "e1", "course_id": "01_math_analysis", "title": "T1", "authors": [], "final_path": str(pdf)})
    result = cli_main(["--data-root", str(tmp_path), "mainline", "verify", "01_math_analysis", "e1"])
    assert result == 2
    assert "校验失败" in capsys.readouterr().err


def test_mainline_channels_command_prints_summary(tmp_path: Path, capsys) -> None:
    from qed_tracker.cli import main as cli_main

    store = EntryStore(tmp_path)
    store.create({
        "entry_id": "e1", "course_id": "01_math_analysis", "title": "T1", "authors": [],
        "channels": [{"channel": "internet_archive", "ok": True, "note": ""}],
    })
    store.create({
        "entry_id": "e2", "course_id": "02_linear_algebra", "title": "T2", "authors": [],
        "channels": [{"channel": "internet_archive", "ok": False, "note": "404"}, {"channel": "google_books", "ok": True, "note": ""}],
    })
    assert cli_main(["--data-root", str(tmp_path), "mainline", "channels"]) == 0
    out = capsys.readouterr().out
    assert "internet_archive" in out
    assert "google_books" in out
    assert "成功" in out


def test_mainline_channels_json_output(tmp_path: Path, capsys) -> None:
    from qed_tracker.cli import main as cli_main

    store = EntryStore(tmp_path)
    store.create({
        "entry_id": "e1", "course_id": "01_math_analysis", "title": "T1", "authors": [],
        "channels": [{"channel": "internet_archive", "ok": True, "note": ""}],
    })
    store.create({
        "entry_id": "e2", "course_id": "02_linear_algebra", "title": "T2", "authors": [],
        "channels": [{"channel": "internet_archive", "ok": False, "note": "404"}],
    })
    assert cli_main(["--data-root", str(tmp_path), "--json", "mainline", "channels"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["channels"]["internet_archive"] == {"ok": 1, "fail": 1}
