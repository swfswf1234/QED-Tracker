from __future__ import annotations

import json
from pathlib import Path

import pytest

from qed_tracker.main_line.store import EntryStore, MainLineStatus


def _entry() -> dict:
    return {
        "entry_id": "01-rudin-zh",
        "course_id": "01_math_analysis",
        "title": "数学分析原理",
        "authors": ["Rudin"],
        "version": {"edition": "第3版", "publisher": "机械工业出版社", "year": "2003", "language": "zh", "detail": "中译本"},
        "evaluation": {"source": "llm", "text": "经典教材", "authority": "高", "set_candidate": "套一"},
        "advice": {"download": "recommended", "reason": "经典中文翻译版"},
        "channels": [],
        "status": "draft",
        "updated_at": "2026-08-12T10:00:00+00:00",
    }


def test_create_entry_writes_json(tmp_path: Path) -> None:
    store = EntryStore(tmp_path)
    entry = store.create(_entry())
    assert entry.status == MainLineStatus.DRAFT
    path = tmp_path / "meta" / "main-line" / "01_math_analysis" / "01-rudin-zh.json"
    assert path.is_file()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1
    assert raw["title"] == "数学分析原理"


def test_get_entry_roundtrip(tmp_path: Path) -> None:
    store = EntryStore(tmp_path)
    store.create(_entry())
    entry = store.get("01_math_analysis", "01-rudin-zh")
    assert entry is not None
    assert entry.title == "数学分析原理"
    assert entry.version["edition"] == "第3版"


def test_transition_review_download_approve(tmp_path: Path) -> None:
    store = EntryStore(tmp_path)
    store.create(_entry())
    store.transition("01_math_analysis", "01-rudin-zh", MainLineStatus.REVIEWED)
    store.transition("01_math_analysis", "01-rudin-zh", MainLineStatus.DOWNLOADING)
    store.transition("01_math_analysis", "01-rudin-zh", MainLineStatus.DOWNLOADED)
    entry = store.get("01_math_analysis", "01-rudin-zh")
    assert entry.status == MainLineStatus.DOWNLOADED


def test_illegal_transition_raises(tmp_path: Path) -> None:
    store = EntryStore(tmp_path)
    store.create(_entry())
    with pytest.raises(ValueError):
        store.transition("01_math_analysis", "01-rudin-zh", MainLineStatus.APPROVED)  # draft 不能直接 approved


def test_list_course_entries(tmp_path: Path) -> None:
    store = EntryStore(tmp_path)
    store.create(_entry())
    entries = store.list_course("01_math_analysis")
    assert [e.entry_id for e in entries] == ["01-rudin-zh"]


def test_missing_entry_returns_none(tmp_path: Path) -> None:
    store = EntryStore(tmp_path)
    assert store.get("01_math_analysis", "nope") is None


def test_create_preserves_channels_resource_and_path(tmp_path: Path) -> None:
    data = _entry()
    channel = {"kind": "book", "url": "https://example.com/book.pdf"}
    data["channels"] = [channel]
    data["resource_id"] = "res-123"
    data["final_path"] = "books/01-rudin-zh.pdf"
    store = EntryStore(tmp_path)
    entry = store.create(data)
    assert entry.channels == (channel,)
    assert entry.resource_id == "res-123"
    assert entry.final_path == "books/01-rudin-zh.pdf"
    raw = json.loads((tmp_path / "meta" / "main-line" / "01_math_analysis" / "01-rudin-zh.json").read_text(encoding="utf-8"))
    assert raw["channels"] == [channel]
    assert raw["resource_id"] == "res-123"
    assert raw["final_path"] == "books/01-rudin-zh.pdf"


def test_transition_rejected_persists_reason(tmp_path: Path) -> None:
    store = EntryStore(tmp_path)
    store.create(_entry())
    entry = store.transition("01_math_analysis", "01-rudin-zh", MainLineStatus.REJECTED, reason="非经典")
    assert entry.reject_reason == "非经典"
    reloaded = store.get("01_math_analysis", "01-rudin-zh")
    assert reloaded is not None
    assert reloaded.reject_reason == "非经典"


def test_transition_non_rejected_ignores_reason(tmp_path: Path) -> None:
    store = EntryStore(tmp_path)
    store.create(_entry())
    entry = store.transition("01_math_analysis", "01-rudin-zh", MainLineStatus.REVIEWED, reason="不应保留")
    assert entry.reject_reason == ""


def test_reject_reason_roundtrip(tmp_path: Path) -> None:
    data = _entry()
    data["reject_reason"] = "非经典教材"
    store = EntryStore(tmp_path)
    store.create(data)
    entry = store.get("01_math_analysis", "01-rudin-zh")
    assert entry is not None
    assert entry.reject_reason == "非经典教材"
    raw = json.loads((tmp_path / "meta" / "main-line" / "01_math_analysis" / "01-rudin-zh.json").read_text(encoding="utf-8"))
    assert raw["reject_reason"] == "非经典教材"


def test_rejected_to_draft_retry(tmp_path: Path) -> None:
    store = EntryStore(tmp_path)
    store.create(_entry())
    store.transition("01_math_analysis", "01-rudin-zh", MainLineStatus.REJECTED)
    entry = store.transition("01_math_analysis", "01-rudin-zh", MainLineStatus.DRAFT)
    assert entry.status == MainLineStatus.DRAFT


def test_approved_is_terminal(tmp_path: Path) -> None:
    store = EntryStore(tmp_path)
    store.create(_entry())
    for status in (MainLineStatus.REVIEWED, MainLineStatus.DOWNLOADING, MainLineStatus.DOWNLOADED):
        store.transition("01_math_analysis", "01-rudin-zh", status)
    store.transition("01_math_analysis", "01-rudin-zh", MainLineStatus.APPROVED)
    for status in MainLineStatus:
        with pytest.raises(ValueError):
            store.transition("01_math_analysis", "01-rudin-zh", status)


def test_duplicate_create_raises(tmp_path: Path) -> None:
    store = EntryStore(tmp_path)
    store.create(_entry())
    with pytest.raises(ValueError):
        store.create(_entry())


def test_update_persists_title_and_advice(tmp_path: Path) -> None:
    store = EntryStore(tmp_path)
    store.create(_entry())
    updated = store.update("01_math_analysis", "01-rudin-zh", title="新标题", advice={"download": "required", "reason": "更新"})
    assert updated.title == "新标题"
    entry = store.get("01_math_analysis", "01-rudin-zh")
    assert entry is not None
    assert entry.title == "新标题"
    assert entry.advice["download"] == "required"


def test_create_rejects_path_traversal_ids(tmp_path: Path) -> None:
    store = EntryStore(tmp_path)
    bad_entry = _entry()
    bad_entry["entry_id"] = "../escape"
    with pytest.raises(ValueError):
        store.create(bad_entry)
    bad_course = _entry()
    bad_course["course_id"] = "a/b"
    with pytest.raises(ValueError):
        store.create(bad_course)


def test_path_methods_reject_path_traversal_ids(tmp_path: Path) -> None:
    store = EntryStore(tmp_path)
    with pytest.raises(ValueError):
        store.get("..", "escape")
    with pytest.raises(ValueError):
        store.transition("01_math_analysis", "a/b", MainLineStatus.REVIEWED)


def test_create_rejects_unknown_status(tmp_path: Path) -> None:
    data = _entry()
    data["status"] = "bogus"
    store = EntryStore(tmp_path)
    with pytest.raises(ValueError):
        store.create(data)


def test_create_accepts_explicit_valid_status(tmp_path: Path) -> None:
    data = _entry()
    data["status"] = "reviewed"
    store = EntryStore(tmp_path)
    entry = store.create(data)
    assert entry.status == MainLineStatus.REVIEWED


def test_record_channel_appends_and_persists(tmp_path: Path) -> None:
    store = EntryStore(tmp_path)
    store.create(_entry())
    updated = store.record_channel("01_math_analysis", "01-rudin-zh", "internet_archive", True, "sha256:abc")
    assert len(updated.channels) == 1
    assert updated.channels[0]["channel"] == "internet_archive"
    assert updated.channels[0]["ok"] is True
    assert updated.channels[0]["note"] == "sha256:abc"
    assert "attempted_at" in updated.channels[0]
    reloaded = store.get("01_math_analysis", "01-rudin-zh")
    assert reloaded is not None
    assert reloaded.channels[0] == updated.channels[0]
    store.record_channel("01_math_analysis", "01-rudin-zh", "google_books", False, "429")
    reloaded = store.get("01_math_analysis", "01-rudin-zh")
    assert reloaded is not None
    assert [item["channel"] for item in reloaded.channels] == ["internet_archive", "google_books"]
    assert reloaded.channels[1]["ok"] is False


def test_record_channel_missing_entry_raises(tmp_path: Path) -> None:
    store = EntryStore(tmp_path)
    with pytest.raises(ValueError):
        store.record_channel("01_math_analysis", "nope", "internet_archive", True)


def test_channel_stats_aggregates_across_courses(tmp_path: Path) -> None:
    store = EntryStore(tmp_path)
    first = _entry()
    first["channels"] = [
        {"channel": "internet_archive", "ok": True, "note": ""},
        {"channel": "google_books", "ok": False, "note": "429"},
    ]
    store.create(first)
    second = _entry()
    second["entry_id"] = "02-rudin-en"
    second["course_id"] = "02_linear_algebra"
    second["channels"] = [
        {"channel": "internet_archive", "ok": False, "note": "404"},
        {"channel": "google_books", "ok": True, "note": ""},
        {"channel": "libgen_li", "ok": True, "note": ""},
    ]
    store.create(second)
    stats = store.channel_stats()
    assert stats == {
        "internet_archive": {"ok": 1, "fail": 1},
        "google_books": {"ok": 1, "fail": 1},
        "libgen_li": {"ok": 1, "fail": 0},
    }


def test_channel_stats_empty_when_no_entries(tmp_path: Path) -> None:
    assert EntryStore(tmp_path).channel_stats() == {}
