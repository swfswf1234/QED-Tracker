from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.db.models import Base
from qed_tracker.profiles import list_paper_profiles, load_paper_profile
from qed_tracker.selection_store import SelectionStore, SelectionStoreError


def _make_store():
    """创建基于 SQLite in-memory 的 SelectionStore（测试用）。"""
    engine = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return SelectionStore(lambda: factory())


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
    store = _make_store()
    selection_id = store.new_id(datetime(2026, 7, 30, tzinfo=UTC))
    report = {"selection_id": selection_id, "schema_version": 1, "status": "ranked", "created_at": "2026-07-30T00:00:00+00:00"}
    store.save(report)
    loaded = store.load(selection_id)
    assert loaded["selection_id"] == selection_id
    assert loaded["schema_version"] == 1
    assert loaded["status"] == "ranked"
    assert store.list()[0]["selection_id"] == selection_id
    with pytest.raises(ValueError, match="非法"):
        store.load("../outside")


def test_missing_selection_is_a_runtime_store_error(tmp_path):
    store = _make_store()
    selection_id = store.new_id(datetime(2026, 7, 30, tzinfo=UTC))
    with pytest.raises(SelectionStoreError, match="不存在"):
        store.load(selection_id)
