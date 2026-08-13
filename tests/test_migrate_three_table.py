"""存量迁移（qt_resources + meta/resources JSON + 主链路 JSON → 三表）定向测试。

用 SQLite 内存模拟 qt_resources + tmp_path 模拟数据根 meta 目录；
断言映射规则、幂等可重放、rejected 隐藏、marker 标志。
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.application.migrate_three_table import migrate_legacy_to_three_table
from qed_tracker.database import utc_now
from qed_tracker.db.models import Base, DownloadStatus, QtResource, SelectionStatus
from qed_tracker.db.selection_repository import ThreeTableRepository


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _add_resource(
    session_factory,
    *,
    resource_id: str,
    status: str,
    title: str,
    target_id: str,
    course_id: str = "01_math_analysis",
    sha256: str = "",
    kind: str = "book",
    edition: str = "",
    language: str = "zh",
    reject_reason: str = "",
    rejected_by: str = "",
    source: dict | None = None,
    roles: list | None = None,
):
    with session_factory() as session:
        row = QtResource(
            resource_id=resource_id,
            kind=kind,
            title=title,
            language=language,
            edition=edition,
            status=status,
            sha256=sha256 or None,
            reject_reason=reject_reason,
            rejected_by=rejected_by,
            source=source or {},
            catalog_ref={"catalog_id": "math-qe", "target_id": target_id, "course_id": course_id},
            created_at=utc_now(),
        )
        session.add(row)
        session.commit()


def _write_meta_json(tmp_path, name: str, payload: dict):
    target = tmp_path / "meta" / "resources" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _approved_meta_json(sha256: str, roles: list, target_id: str) -> dict:
    return {
        "authors": ["作者"],
        "catalog_ref": {"catalog_id": "math-qe", "course_id": "01_math_analysis", "target_id": target_id},
        "created_at": "2026-08-10T00:00:00+00:00",
        "file": {
            "relative_path": f"raw/books/math-qe/01_math_analysis/x_{sha256[:8]}.pdf",
            "sha256": sha256,
            "page_count": 100,
            "mime_type": "application/pdf",
        },
        "kind": "book",
        "language": "zh",
        "resource_id": f"sha256:{sha256}",
        "roles": roles,
        "source": {
            "provider": "internet_archive",
            "provider_id": "ia-1",
            "page_url": "https://archive.org/details/ia-1",
            "download_url": "https://archive.org/download/ia-1/x.pdf",
            "retrieved_at": "2026-08-10T00:00:00+00:00",
        },
        "title": "数学分析",
        "year": "2020",
    }


def test_approved_resources_map_to_confirmed_selection_and_approved_downloads(session_factory, tmp_path):
    _add_resource(
        session_factory, resource_id="cand_a", status="candidate", title="数学分析", target_id="01-chenjixiu-v1"
    )
    _add_resource(
        session_factory,
        resource_id="sha256:aa" + "a" * 62,
        status="approved",
        title="数学分析（上册）",
        target_id="01-chenjixiu-v1",
        sha256="aa" + "a" * 62,
    )
    _add_resource(
        session_factory,
        resource_id="sha256:bb" + "b" * 62,
        status="approved",
        title="数学分析（下册）",
        target_id="01-chenjixiu-v2",
        sha256="bb" + "b" * 62,
    )
    _add_resource(
        session_factory,
        resource_id="sha256:cc" + "c" * 62,
        status="approved",
        title="数学分析习题解答",
        target_id="01-chenjixiu-answers",
        sha256="cc" + "c" * 62,
        kind="supplement",
    )
    _write_meta_json(
        tmp_path, "aa" + "a" * 62 + ".json", _approved_meta_json("aa" + "a" * 62, ["textbook"], "01-chenjixiu-v1")
    )
    _write_meta_json(
        tmp_path, "bb" + "b" * 62 + ".json", _approved_meta_json("bb" + "b" * 62, ["textbook"], "01-chenjixiu-v2")
    )
    _write_meta_json(
        tmp_path, "cc" + "c" * 62 + ".json", _approved_meta_json("cc" + "c" * 62, ["solutions"], "01-chenjixiu-answers")
    )

    report = migrate_legacy_to_three_table(session_factory, tmp_path)

    repo = ThreeTableRepository(session_factory)
    selections = repo.list_selections()
    assert len(selections) == 1
    selection = selections[0]
    assert selection.status == SelectionStatus.CONFIRMED.value
    assert selection.vols == ["v1", "v2", "answers"]
    downloads = repo.list_downloads(selection.selection_id)
    by_vol = {d.vol: d for d in downloads}
    assert set(by_vol) == {"v1", "v2", "answers"}
    assert by_vol["v1"].status == DownloadStatus.APPROVED.value
    assert by_vol["v1"].roles == ["textbook"]
    assert by_vol["answers"].roles == ["solutions"]  # 册级 roles 覆盖
    assert by_vol["answers"].sha256 == "cc" + "c" * 62
    assert by_vol["answers"].relative_path.startswith("raw/books/math-qe")
    assert report.selections == 1 and report.downloads == 3


def test_backup_and_rejected_map_and_hidden(session_factory, tmp_path):
    _add_resource(session_factory, resource_id="cand_b", status="backup", title="备选书", target_id="02-backup-book")
    _add_resource(
        session_factory,
        resource_id="cand_r",
        status="rejected",
        title="否决书",
        target_id="03-rejected-book",
        reject_reason="版本旧",
        rejected_by="cli",
    )
    _add_resource(
        session_factory, resource_id="cand_n", status="not_found", title="找不到", target_id="04-missing-book"
    )

    migrate_legacy_to_three_table(session_factory, tmp_path)

    repo = ThreeTableRepository(session_factory)
    visible = repo.list_selections()
    assert {s.title for s in visible} == {"备选书"}
    assert visible[0].status == SelectionStatus.BACKUP.value
    hidden = repo.list_selections(include_hidden=True)
    rejected_rows = {s.title: s for s in hidden if s.status == SelectionStatus.REJECTED.value}
    assert "否决书" in rejected_rows
    assert rejected_rows["否决书"].reject_reason == "版本旧"
    assert "找不到" in rejected_rows  # not_found → rejected 留痕
    assert repo.list_selections(status="rejected") == []  # 显式查询同样隐藏


@pytest.mark.skip(reason="marker 防重跑语义改为 skip：断言见 test_migrate_marker_skips_second_run")
def test_migration_idempotent_and_marker(session_factory, tmp_path):
    _add_resource(
        session_factory,
        resource_id="sha256:aa" + "a" * 62,
        status="approved",
        title="数学分析（上册）",
        target_id="01-chenjixiu-v1",
        sha256="aa" + "a" * 62,
    )
    _write_meta_json(
        tmp_path, "aa" + "a" * 62 + ".json", _approved_meta_json("aa" + "a" * 62, ["textbook"], "01-chenjixiu-v1")
    )

    first = migrate_legacy_to_three_table(session_factory, tmp_path)
    second = migrate_legacy_to_three_table(session_factory, tmp_path)

    repo = ThreeTableRepository(session_factory)
    assert len(repo.list_selections(include_hidden=True)) == 1
    assert len(repo.list_downloads(repo.list_selections()[0].selection_id, include_hidden=True)) == 1
    assert first.selections == second.selections == 1
    assert first.downloads == second.downloads == 1
    marker = tmp_path / "meta" / "migrations" / "three_table.marker"
    assert marker.is_file()


def test_migrate_marker_skips_second_run(session_factory, tmp_path):
    """成功迁移写入 marker；重跑跳过（保护迁移后人工作业），--force 可重放。"""
    _add_resource(
        session_factory,
        resource_id="sha256:aa" + "a" * 62,
        status="approved",
        title="数学分析（上册）",
        target_id="01-chenjixiu-v1",
        sha256="aa" + "a" * 62,
    )
    _write_meta_json(
        tmp_path, "aa" + "a" * 62 + ".json", _approved_meta_json("aa" + "a" * 62, ["textbook"], "01-chenjixiu-v1")
    )

    first = migrate_legacy_to_three_table(session_factory, tmp_path)
    assert first.skipped is False and first.selections == 1
    second = migrate_legacy_to_three_table(session_factory, tmp_path)
    assert second.skipped is True
    # _force 重放仍幂等（确定性主键 + merge）
    forced = migrate_legacy_to_three_table(session_factory, tmp_path, force=True)
    assert forced.skipped is False and forced.selections == 1
    repo = ThreeTableRepository(session_factory)
    assert len(repo.list_selections(include_hidden=True)) == 1
    assert len(repo.list_downloads(repo.list_selections()[0].selection_id, include_hidden=True)) == 1


def test_zh_en_versions_are_separate_selections(session_factory, tmp_path):
    _add_resource(
        session_factory,
        resource_id="sha256:aa" + "a" * 62,
        status="approved",
        title="数学分析原理",
        target_id="01-rudin-zh",
        sha256="aa" + "a" * 62,
    )
    _add_resource(
        session_factory,
        resource_id="sha256:bb" + "b" * 62,
        status="approved",
        title="Principles of Mathematical Analysis",
        target_id="01-rudin-en",
        sha256="bb" + "b" * 62,
        language="en",
    )
    _write_meta_json(
        tmp_path, "aa" + "a" * 62 + ".json", _approved_meta_json("aa" + "a" * 62, ["textbook"], "01-rudin-zh")
    )
    _write_meta_json(
        tmp_path, "bb" + "b" * 62 + ".json", _approved_meta_json("bb" + "b" * 62, ["textbook"], "01-rudin-en")
    )

    migrate_legacy_to_three_table(session_factory, tmp_path)

    repo = ThreeTableRepository(session_factory)
    assert len(repo.list_selections()) == 2  # zh/en 不同版本独立条目
