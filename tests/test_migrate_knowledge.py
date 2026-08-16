"""五层模型一次性存量迁移（math.json + 三表 → 五表）幂等与映射定向测试（SQLite 文件库）。"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from qed_tracker.application.migrate_knowledge import migrate_curriculum, migrate_legacy_data
from qed_tracker.db.models import Base, BookStatus, KnowledgeStatus


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'migrate.db'}")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    # 先手工建旧三表（模型已退役，用原生 DDL 模拟存量），再 create_all：
    # checkfirst 跳过已存在的 qt_sources，只补建 4 张新表（qed_domain/qed_course/qt_knowledge/qt_books）。
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE qt_selections (selection_id VARCHAR(100) PRIMARY KEY, course_id VARCHAR(64),"
            " title VARCHAR(500), authors JSON, roles JSON, version JSON, vols JSON, set_no VARCHAR(4),"
            " evaluation JSON, note VARCHAR(1000), status VARCHAR(24), reject_reason VARCHAR(1000),"
            " rejected_by VARCHAR(16), supersede_reason VARCHAR(1000), created_at DATETIME,"
            " confirmed_at DATETIME, superseded_at DATETIME, rejected_at DATETIME)"
        ))
        conn.execute(text(
            "CREATE TABLE qt_downloads (download_id VARCHAR(100) PRIMARY KEY, selection_id VARCHAR(100),"
            " vol VARCHAR(32), roles JSON, file_hint VARCHAR(200), sha256 VARCHAR(64),"
            " relative_path VARCHAR(500), page_count INT, status VARCHAR(24), reject_reason VARCHAR(1000),"
            " rejected_by VARCHAR(16), review_note VARCHAR(1000), created_at DATETIME,"
            " downloaded_at DATETIME, approved_at DATETIME, rejected_at DATETIME)"
        ))
        conn.execute(text(
            "CREATE TABLE qt_sources (source_id VARCHAR(100) PRIMARY KEY, download_id VARCHAR(100),"
            " channel VARCHAR(24), provider_id VARCHAR(200), page_url VARCHAR(1000),"
            " download_url VARCHAR(1000), file_keywords VARCHAR(500), ok TINYINT(1),"
            " note VARCHAR(1000), attempted_at DATETIME)"
        ))
    Base.metadata.create_all(engine)
    yield engine, factory
    engine.dispose()


def _seed_legacy(engine):
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO qt_selections VALUES"
            " ('cand_1','01_math_analysis','微积分学教程',"
            " json_array('菲赫金哥尔茨'),json_array('textbook'),json_object('edition','第8版'),"
            " json_array('v1','v2','v3'),'2','', '', 'confirmed','','','',"
            " '2026-08-01 10:00:00','2026-08-02 10:00:00',NULL,NULL)"
        ))
        conn.execute(text(
            "INSERT INTO qt_downloads VALUES"
            " ('dl_1','cand_1','v1',json_array('textbook'),'',"
            " 'aaaa','raw/books/math-qe/01_math_analysis/x_v1.pdf',100,'downloaded','','','',"
            " '2026-08-01 10:00:00','2026-08-03 10:00:00',NULL,NULL),"
            " ('dl_2','cand_1','v2',json_array('textbook'),'',"
            " 'bbbb','raw/books/math-qe/01_math_analysis/x_v2.pdf',120,'approved','','','',"
            " '2026-08-01 10:00:00','2026-08-03 10:00:00','2026-08-04 10:00:00',NULL)"
        ))
        conn.execute(text(
            "INSERT INTO qt_sources VALUES"
            " ('src_1','dl_1','manual','','','http://x','',1,'','2026-08-03 10:00:00')"
        ))


def test_migrate_curriculum_seeds_domain_and_courses(db, tmp_path):
    engine, factory = db
    courses_dir = tmp_path / "courses"
    courses_dir.mkdir()
    (courses_dir / "math.json").write_text(json.dumps({
        "schema_version": 1, "subject": "math", "name": "数学", "description": "体系",
        "stages": ["本科基础", "QE冲刺"],
        "courses": [
            {"course_id": "01_math_analysis", "name": "数学分析", "aliases": ["高等数学"],
             "stage": "本科基础", "prerequisites": [], "related_targets": [], "note": "n1"},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    migrate_curriculum(factory, courses_dir)
    with factory() as session:
        domain = session.execute(text("SELECT domain_id, stages FROM qed_domain")).fetchone()
        assert domain[0] == "math"
        assert json.loads(domain[1]) == ["本科基础", "QE冲刺"]
        course = session.execute(text(
            "SELECT course_id, sort_order, name FROM qed_course ORDER BY sort_order"
        )).fetchone()
        assert course[0] == "01_math_analysis"
        assert course[1] == 0
        assert course[2] == "数学分析"
    # 幂等：重跑不产生重复行
    migrate_curriculum(factory, courses_dir)
    with factory() as session:
        assert session.execute(text("SELECT COUNT(*) FROM qed_course")).fetchone()[0] == 1


def test_migrate_legacy_maps_selection_to_knowledge_and_books(db, tmp_path):
    engine, factory = db
    _seed_legacy(engine)
    migrate_curriculum(factory, tmp_path / "courses")  # 课程表为空时跳过（无 math.json 目录）
    migrate_legacy_data(factory)
    with factory() as session:
        knowledge = session.execute(text(
            "SELECT knowledge_id, course_id, kind, set_no, status FROM qt_knowledge"
        )).fetchone()
        assert knowledge[0].startswith("kn_")
        assert knowledge[2] == "tutorial"
        assert knowledge[4] == KnowledgeStatus.CONFIRMED.value  # 旧 confirmed → confirmed
        books = session.execute(text(
            "SELECT book_id, title, part, status, sha256, relative_path FROM qt_books ORDER BY part"
        )).fetchall()
        assert len(books) == 2
        assert books[0][1] == "微积分学教程"
        assert books[0][2] == "第一册"  # vol v1 → part 第一册
        assert books[1][3] == BookStatus.VERIFIED.value  # 旧 approved → verified
        sources = session.execute(text("SELECT source_id, book_id FROM qt_sources")).fetchall()
        assert len(sources) == 1
        assert sources[0][1] == books[0][0]  # 外键改挂书行
    # 幂等：重跑不产生重复行
    migrate_legacy_data(factory)
    with factory() as session:
        assert session.execute(text("SELECT COUNT(*) FROM qt_knowledge")).fetchone()[0] == 1
        assert session.execute(text("SELECT COUNT(*) FROM qt_books")).fetchone()[0] == 2


def test_migrate_legacy_drops_old_tables_only_when_marker(db, tmp_path):
    engine, factory = db
    _seed_legacy(engine)
    migrate_legacy_data(factory)
    # 默认不 drop：旧表仍可读（备份快照语义）
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM qt_selections")).fetchone()[0] == 1