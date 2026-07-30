from datetime import UTC, datetime

import pytest

from qed_tracker.profiles import list_paper_profiles, load_paper_profile
from qed_tracker.selection_store import SelectionStore, SelectionStoreError


def test_builtin_profiles_are_valid_and_listed():
    assert list_paper_profiles() == ("llm-engineering", "math-research")
    assert "cs.CL" in load_paper_profile("llm-engineering").allowed_categories
    assert "math.FA" in load_paper_profile("math-research").allowed_categories


def test_custom_profile_rejects_unknown_fields(tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text('{"id":"x","unknown":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="未知字段"):
        load_paper_profile(profile)


def test_selection_store_is_atomic_and_rejects_path_escape(tmp_path):
    store = SelectionStore(tmp_path)
    selection_id = store.new_id(datetime(2026, 7, 30, tzinfo=UTC))
    report = {"selection_id": selection_id, "schema_version": 1, "status": "ranked", "created_at": "2026-07-30T00:00:00+00:00"}
    store.save(report)
    assert store.load(selection_id) == report
    assert store.list()[0]["selection_id"] == selection_id
    assert not list(store.root.glob("*.tmp"))
    with pytest.raises(ValueError, match="非法"):
        store.load("../outside")

    stored = store.root / f"{selection_id}.json"
    stored.write_text("not json", encoding="utf-8")
    with pytest.raises(SelectionStoreError, match="损坏"):
        store.load(selection_id)


def test_missing_selection_is_a_runtime_store_error(tmp_path):
    store = SelectionStore(tmp_path)
    selection_id = store.new_id(datetime(2026, 7, 30, tzinfo=UTC))
    with pytest.raises(SelectionStoreError, match="不存在"):
        store.load(selection_id)
