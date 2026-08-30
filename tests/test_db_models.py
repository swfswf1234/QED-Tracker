"""五表模型（qed_domain/qed_course/qt_knowledge/qt_books/qt_sources）ORM 断言。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.db.models import (
    Base,
    BookStatus,
    KnowledgeStatus,
    QedCourse,
    QedDomain,
    QtBook,
    QtSource,
)

# qed_domain 新增探索字段（2026-08-27 表重构；2026-08-30 REQ-067 B8 增 explore_pending）
_DOMAIN_EXPLORE_COLUMNS = {
    "level", "scope", "exploration_stage", "classic_tracks", "path_results", "explore_pending",
}
_DOMAIN_EXPECTED_COLUMNS = {
    "domain_id", "name", "description", "level", "scope", "exploration_stage",
    "classic_tracks", "stages", "path_results", "explore_pending",
    "created_by", "updated_by", "created_at", "updated_at",
}
_EXPLORATION_STAGES = {"未开始", "已生成", "探索中", "已完成", "失败"}


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory()
    engine.dispose()


def test_enums_complete() -> None:
    assert {s.value for s in KnowledgeStatus} == {"draft", "confirmed", "completed", "rejected", "superseded"}
    assert {s.value for s in BookStatus} == {
        "candidate", "decided", "downloading", "downloaded", "verified",
        "failed", "rejected", "superseded",
    }


def test_legacy_three_tables_gone() -> None:
    """替换重构：旧三表模型不再存在（drop 由迁移/脚本负责，ORM 无残留）。"""
    tables = {t.name for t in Base.metadata.sorted_tables}
    assert "qt_selections" not in tables
    assert "qt_downloads" not in tables


def test_shared_tables_exist(session) -> None:
    tables = {t.name for t in Base.metadata.sorted_tables}
    assert {QedDomain.__tablename__, QedCourse.__tablename__} <= tables
    now = __import__("qed_tracker.database", fromlist=["utc_now"]).utc_now()
    domain = QedDomain(domain_id="math", name="数学", description="d", stages=["本科基础"], created_at=now, updated_at=now)
    session.add(domain)
    session.commit()
    assert session.get(QedDomain, "math") is not None


def test_qed_domain_explore_columns(session) -> None:
    """qed_domain 新增探索字段（2026-08-27 表重构 + 2026-08-30 explore_pending）。"""
    columns = {c.name for c in QedDomain.__table__.columns}
    assert _DOMAIN_EXPECTED_COLUMNS == columns
    # 新增的探索列全部存在
    assert _DOMAIN_EXPLORE_COLUMNS <= columns


def test_qed_domain_explore_defaults(session) -> None:
    """新字段默认值：exploration_stage=未开始, classic_tracks=[], path_results=null, level/scope=''。"""
    now = __import__("qed_tracker.database", fromlist=["utc_now"]).utc_now()
    domain = QedDomain(
        domain_id="math", name="数学", description="d",
        stages=[], created_at=now, updated_at=now,
    )
    session.add(domain)
    session.commit()
    row = session.get(QedDomain, "math")
    assert row.exploration_stage == "未开始"
    assert row.classic_tracks == []
    assert row.path_results is None
    assert row.level == ""
    assert row.scope == ""


def test_qed_domain_stages_no_default(session) -> None:
    """stages 字段无默认值——不传 stages 时 ORM 不自动填充。"""
    col = QedDomain.__table__.c.stages
    # 无 server_default 且无 Python default
    assert col.default is None or col.default.arg is None


def test_qed_domain_explore_full_roundtrip(session) -> None:
    """完整写入+读出：探索字段写入后原样返回。"""
    now = __import__("qed_tracker.database", fromlist=["utc_now"]).utc_now()
    domain = QedDomain(
        domain_id="math", name="数学", description="学科介绍",
        level="本科-硕士", scope="大学以上数学专业课程",
        exploration_stage="已生成",
        classic_tracks=[{"name": "分析学", "summary": "研究连续与变化的数学"}],
        stages=["本科基础", "本科进阶"],
        path_results={"notes": "", "edges": [{"from": "a", "to": "b"}], "graph_td": "graph TD\n"},
        created_at=now, updated_at=now,
    )
    session.add(domain)
    session.commit()
    session.expire_all()
    row = session.get(QedDomain, "math")
    assert row.level == "本科-硕士"
    assert row.scope == "大学以上数学专业课程"
    assert row.exploration_stage == "已生成"
    assert row.classic_tracks == [{"name": "分析学", "summary": "研究连续与变化的数学"}]
    assert row.stages == ["本科基础", "本科进阶"]
    assert row.path_results["edges"] == [{"from": "a", "to": "b"}]


def test_qed_domain_explore_pending_defaults(session) -> None:
    """explore_pending 默认 None（REQ-067 B8）。"""
    now = __import__("qed_tracker.database", fromlist=["utc_now"]).utc_now()
    domain = QedDomain(domain_id="math", name="数学", description="d",
                       stages=[], created_at=now, updated_at=now)
    session.add(domain)
    session.commit()
    row = session.get(QedDomain, "math")
    assert row.explore_pending is None
    assert row.exploration_stage == "未开始"


def test_qed_domain_explore_pending_roundtrip(session) -> None:
    """explore_pending 写入后原样返回（name_confirm/failed 两种形态）。"""
    now = __import__("qed_tracker.database", fromlist=["utc_now"]).utc_now()
    domain = QedDomain(domain_id="math", name="数学", description="d",
                       stages=[], created_at=now, updated_at=now)
    session.add(domain)
    session.commit()
    domain.explore_pending = {
        "kind": "name_confirm",
        "name_check": {"suggested_name": "高等数学", "valid": False, "reason": "r"},
    }
    session.commit()
    session.expire_all()
    row = session.get(QedDomain, "math")
    assert row.explore_pending["kind"] == "name_confirm"
    assert row.explore_pending["name_check"]["suggested_name"] == "高等数学"


def test_qt_books_unique_constraints() -> None:
    table = QtBook.__table__
    names = {c.name for c in table.constraints}
    assert "uq_qt_books_knowledge_title_part" in names
    assert "uq_qt_books_sha256" in names


def test_qt_sources_foreign_key_to_books() -> None:
    fk = next(fk for fk in QtSource.__table__.foreign_keys if fk.parent.name == "book_id")
    assert fk.column.table.name == "qt_books"


# qed_course 重构断言（2026-08-27：note→description + track + exploration_stage）
_COURSE_EXPECTED_COLUMNS = {
    "course_id", "domain_id", "sort_order", "name", "aliases", "track", "stage",
    "prerequisites", "related_targets", "description", "exploration_stage",
    "created_by", "updated_by", "created_at", "updated_at",
}


def test_qed_course_columns(session) -> None:
    """qed_course 重构后列集合：note→description + track + exploration_stage。"""
    columns = {c.name for c in QedCourse.__table__.columns}
    assert _COURSE_EXPECTED_COLUMNS == columns
    assert "note" not in columns, "note 已重命名为 description"
    assert "track" in columns
    assert "exploration_stage" in columns


def test_qed_course_defaults(session) -> None:
    """新字段默认值：exploration_stage=未开始, track='', description=''。"""
    now = __import__("qed_tracker.database", fromlist=["utc_now"]).utc_now()
    domain = QedDomain(domain_id="math", name="数学", description="d",
                       stages=[], created_at=now, updated_at=now)
    session.add(domain)
    course = QedCourse(
        course_id="01_math_analysis", domain_id="math", sort_order=0,
        name="数学分析", aliases=[], stage="本科基础",
        prerequisites=[], related_targets=[],
        created_at=now, updated_at=now,
    )
    session.add(course)
    session.commit()
    row = session.get(QedCourse, "01_math_analysis")
    assert row.exploration_stage == "未开始"
    assert row.track == ""
    assert row.description == ""


def test_qed_course_full_roundtrip(session) -> None:
    """完整写入+读出：重构字段写入后原样返回。"""
    now = __import__("qed_tracker.database", fromlist=["utc_now"]).utc_now()
    domain = QedDomain(domain_id="math", name="数学", description="d",
                       stages=[], created_at=now, updated_at=now)
    session.add(domain)
    course = QedCourse(
        course_id="01_math_analysis", domain_id="math", sort_order=0,
        name="数学分析", aliases=["微积分"], track="分析学", stage="本科基础",
        prerequisites=[], related_targets=["LAG1"],
        description="数学系的第一门严格分析课",
        exploration_stage="已生成",
        created_at=now, updated_at=now,
    )
    session.add(course)
    session.commit()
    session.expire_all()
    row = session.get(QedCourse, "01_math_analysis")
    assert row.track == "分析学"
    assert row.description == "数学系的第一门严格分析课"
    assert row.exploration_stage == "已生成"
    assert row.aliases == ["微积分"]
    assert row.related_targets == ["LAG1"]