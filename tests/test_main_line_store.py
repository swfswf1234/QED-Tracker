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
