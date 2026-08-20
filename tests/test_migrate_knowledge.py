"""五层模型一次性存量迁移（math.json + 三表 → 五表）幂等与映射定向测试（SQLite 文件库）。"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, inspect, text
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


@pytest.fixture
def empty_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
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


def test_tutorial_name_rule():
    """QED-036 命名规则纯函数：教程{set_no}：书名（作者）；en 套 / 兜底 / 无作者退化。"""
    from qed_tracker.db.knowledge_repository import tutorial_name

    assert tutorial_name("1", "数学分析", ["Rudin"]) == "教程1：数学分析（Rudin）"
    assert tutorial_name("en", "Principles", ["Rudin"]) == "教程en：Principles（Rudin）"
    assert tutorial_name("2", "微积分学教程", ["菲赫金哥尔茨"]) == "教程2：微积分学教程（菲赫金哥尔茨）"
    assert tutorial_name("3", "数学分析", ["陈纪修", "於崇华", "金路"]) == "教程3：数学分析（陈纪修、於崇华、金路）"
    assert tutorial_name("", "延展资料", ["X"]) == "教程：延展资料（X）"  # 空 set_no 兜底
    assert tutorial_name("1", "数学分析", []) == "教程1：数学分析"  # 无作者省略
    # 存量书行 title 已含「（作者）」后缀时不重复拼接（真实存量 套3 陈纪修）
    assert tutorial_name("3", "数学分析（陈纪修）", ["陈纪修"]) == "教程3：数学分析（陈纪修）"


def test_migrate_legacy_maps_selection_to_knowledge_and_books(db, tmp_path):
    engine, factory = db
    _seed_legacy(engine)
    migrate_curriculum(factory, tmp_path / "courses")  # 课程表为空时跳过（无 math.json 目录）
    migrate_legacy_data(factory)
    with factory() as session:
        knowledge = session.execute(text(
            "SELECT knowledge_id, course_id, kind, set_no, name, status, textbook_ref FROM qt_knowledge"
        )).fetchone()
        assert knowledge[0].startswith("kn_")
        assert knowledge[2] == "tutorial"
        assert knowledge[4] == "教程2：微积分学教程（菲赫金哥尔茨）"  # QED-036 规范命名
        assert knowledge[5] == KnowledgeStatus.CONFIRMED.value  # 旧 confirmed → confirmed
        assert json.loads(knowledge[6]) == {
            "title": "微积分学教程", "version": {"edition": "第8版"}, "authors": ["菲赫金哥尔茨"],
        }  # QED-036：textbook_ref 回填 authors
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


def test_migrate_reuses_old_format_row_after_rename(db, tmp_path):
    """QED-036：存量行改名后重放不产生重复行——按 (course, kind, set_no) 先查后建。

    knowledge_id 幂等键含 name；旧版迁移生成的行 id 由旧格式 name 计算。新版迁移
    （新格式 name）重放时若按 id 直接 create 会生成新 id 产生重复行，必须先按
    course+kind+set_no 查既有行复用（存量改名由一次性数据修正脚本负责）。
    """
    from qed_tracker.db.knowledge_repository import _id

    engine, factory = db
    old_id = _id("kn", "math", "01_math_analysis", "tutorial", "2", "微积分学教程 套2")
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO qed_domain (domain_id, name, description, stages, created_by, updated_by,"
            " created_at, updated_at) VALUES"
            " ('math','数学','d',json_array('本科基础'),'','','2026-08-01 10:00:00','2026-08-01 10:00:00')"
        ))
        conn.execute(text(
            "INSERT INTO qed_course (course_id, domain_id, sort_order, name, aliases, stage, prerequisites,"
            " related_targets, note, created_by, updated_by, created_at, updated_at) VALUES"
            " ('01_math_analysis','math',0,'数学分析',json_array(),'本科基础',json_array(),json_array(),'n',"
            " '','','2026-08-01 10:00:00','2026-08-01 10:00:00')"
        ))
        conn.execute(text(
            "INSERT INTO qt_knowledge (knowledge_id, domain_id, course_id, kind, set_no, name,"
            " textbook_ref, exercise_ref, textbook_intro, exercise_intro, materials_intro, status,"
            " reject_reason, supersede_reason, created_by, updated_by, created_at, updated_at) VALUES"
            " (:id,'math','01_math_analysis','tutorial','2','微积分学教程 套2','{}','{}','','','',"
            " 'draft','','','','','2026-08-01 10:00:00','2026-08-01 10:00:00')"
        ), {"id": old_id})
    _seed_legacy(engine)
    migrate_legacy_data(factory)
    with factory() as session:
        rows = session.execute(text(
            "SELECT knowledge_id, name FROM qt_knowledge WHERE course_id='01_math_analysis'"
        )).fetchall()
        assert len(rows) == 1  # 复用旧行，不新建
        assert rows[0][0] == old_id
        assert rows[0][1] == "微积分学教程 套2"  # 存量改名由一次性脚本负责，migrate 不覆盖


def test_migrate_legacy_prefixed_vol_maps_to_part(db, tmp_path):
    """真实存量 vol 形如 '教材-v1'/'微积分-v3'/'教材-answers'：归一化到 第一册/第三册/答案册。"""
    engine, factory = db
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO qt_selections VALUES"
            " ('cand_9','01_math_analysis','数学分析（陈纪修）',"
            " json_array('陈纪修'),json_array('textbook'),json_object('edition','第2版'),"
            " json_array('教材-v2','教材-v1','教材-answers'),'3','', '', 'confirmed','','','',"
            " '2026-08-01 10:00:00','2026-08-02 10:00:00',NULL,NULL)"
        ))
        conn.execute(text(
            "INSERT INTO qt_downloads VALUES"
            " ('dl_a','cand_9','教材-v1',json_array('textbook'),'',"
            " 'aaaa','raw/books/math-qe/01_math_analysis/x_v1.pdf',100,'approved','','','',"
            " '2026-08-01 10:00:00','2026-08-03 10:00:00','2026-08-04 10:00:00',NULL),"
            " ('dl_b','cand_9','教材-v2',json_array('textbook'),'',"
            " 'bbbb','raw/books/math-qe/01_math_analysis/x_v2.pdf',120,'approved','','','',"
            " '2026-08-01 10:00:00','2026-08-03 10:00:00','2026-08-04 10:00:00',NULL),"
            " ('dl_c','cand_9','教材-answers',json_array('textbook'),'',"
            " 'cccc','raw/books/math-qe/01_math_analysis/x_answers.pdf',80,'approved','','','',"
            " '2026-08-01 10:00:00','2026-08-03 10:00:00','2026-08-04 10:00:00',NULL)"
        ))
    migrate_curriculum(factory, tmp_path / "courses")
    migrate_legacy_data(factory)
    with factory() as session:
        books = session.execute(text(
            "SELECT part, sha256 FROM qt_books ORDER BY part"
        )).fetchall()
        assert [row[0] for row in books] == ["第一册", "第二册", "答案册"]
        assert {row[1] for row in books} == {"aaaa", "bbbb", "cccc"}  # 三册 sha256 全保留


def test_migrate_legacy_empty_vol_multivol_keeps_every_sha256(db, tmp_path):
    """真实存量 Rudin 套 3 册 vol 全空：按出现序编号 第一/二/三册，不丢 sha256。"""
    engine, factory = db
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO qt_selections VALUES"
            " ('tut_7','01_math_analysis','数学分析原理（Rudin）',"
            " json_array('Rudin'),json_array('textbook'),json_object(),"
            " json_array(''),'1','', '', 'confirmed','','','',"
            " '2026-08-01 10:00:00','2026-08-02 10:00:00',NULL,NULL)"
        ))
        conn.execute(text(
            "INSERT INTO qt_downloads VALUES"
            " ('dl_1','tut_7','',json_array('textbook'),'',"
            " 's1','raw/books/math-qe/01_math_analysis/r1.pdf',100,'approved','','','',"
            " '2026-08-01 10:00:00','2026-08-03 10:00:00','2026-08-04 10:00:00',NULL),"
            " ('dl_2','tut_7','',json_array('textbook'),'',"
            " 's2','raw/books/math-qe/01_math_analysis/r2.pdf',110,'approved','','','',"
            " '2026-08-01 10:00:00','2026-08-03 10:00:00','2026-08-04 10:00:00',NULL),"
            " ('dl_3','tut_7','',json_array('textbook'),'',"
            " 's3','raw/books/math-qe/01_math_analysis/r3.pdf',120,'approved','','','',"
            " '2026-08-01 10:00:00','2026-08-03 10:00:00','2026-08-04 10:00:00',NULL)"
        ))
    migrate_curriculum(factory, tmp_path / "courses")
    migrate_legacy_data(factory)
    with factory() as session:
        books = session.execute(text(
            "SELECT part, sha256 FROM qt_books ORDER BY part"
        )).fetchall()
        assert {row[0] for row in books} == {"第一册", "第二册", "第三册"}
        assert {row[1] for row in books} == {"s1", "s2", "s3"}


def test_migrate_legacy_jiangyi_vol_does_not_collide(db, tmp_path):
    """套内讲义-vN（谢惠民习题课讲义）与主教材 vN 分册：vol 前缀独立成书，不撞唯一约束不丢册。"""
    engine, factory = db
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO qt_selections VALUES"
            " ('tut_8','01_math_analysis','微积分学教程（菲赫金哥尔茨）',"
            " json_array('菲赫金哥尔茨'),json_array('textbook'),json_object(),"
            " json_array('微积分-v1','微积分-v2','讲义-v1','讲义-v2'),'2','', '', 'confirmed','','','',"
            " '2026-08-01 10:00:00','2026-08-02 10:00:00',NULL,NULL)"
        ))
        conn.execute(text(
            "INSERT INTO qt_downloads VALUES"
            " ('dl_1','tut_8','微积分-v1',json_array('textbook'),'',"
            " 'w1','raw/books/math-qe/01_math_analysis/w1.pdf',100,'approved','','','',"
            " '2026-08-01 10:00:00','2026-08-03 10:00:00','2026-08-04 10:00:00',NULL),"
            " ('dl_2','tut_8','微积分-v2',json_array('textbook'),'',"
            " 'w2','raw/books/math-qe/01_math_analysis/w2.pdf',110,'approved','','','',"
            " '2026-08-01 10:00:00','2026-08-03 10:00:00','2026-08-04 10:00:00',NULL),"
            " ('dl_3','tut_8','讲义-v1',json_array('exercises'),'',"
            " 'j1','raw/books/math-qe/01_math_analysis/j1.pdf',120,'approved','','','',"
            " '2026-08-01 10:00:00','2026-08-03 10:00:00','2026-08-04 10:00:00',NULL),"
            " ('dl_4','tut_8','讲义-v2',json_array('exercises'),'',"
            " 'j2','raw/books/math-qe/01_math_analysis/j2.pdf',130,'approved','','','',"
            " '2026-08-01 10:00:00','2026-08-03 10:00:00','2026-08-04 10:00:00',NULL)"
        ))
    migrate_curriculum(factory, tmp_path / "courses")
    migrate_legacy_data(factory)
    with factory() as session:
        books = session.execute(text(
            "SELECT title, part, roles, sha256, status FROM qt_books ORDER BY title, part"
        )).fetchall()
        assert len(books) == 4  # 不丢册
        assert books[0][0] == "微积分学教程（菲赫金哥尔茨）" and books[0][1] == "第一册"
        assert books[1][0] == "微积分学教程（菲赫金哥尔茨）" and books[1][1] == "第二册"
        assert books[2][0] == "数学分析习题课讲义（谢惠民）" and books[2][1] == "上册"
        assert books[3][0] == "数学分析习题课讲义（谢惠民）" and books[3][1] == "下册"
        assert {row[3] for row in books} == {"w1", "w2", "j1", "j2"}  # sha256 全保留
        assert {row[4] for row in books} == {BookStatus.VERIFIED.value}
    # 幂等重跑：仍 4 本
    migrate_legacy_data(factory)
    with factory() as session:
        assert session.execute(text("SELECT COUNT(*) FROM qt_books")).fetchone()[0] == 4


def test_migrate_legacy_drops_old_tables_only_when_marker(db, tmp_path):
    engine, factory = db
    _seed_legacy(engine)
    migrate_legacy_data(factory)
    # 默认不 drop：旧表仍可读（备份快照语义）
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM qt_selections")).fetchone()[0] == 1


def test_migrate_legacy_preserves_sources_legacy_without_drop_flag(db, tmp_path):
    engine, factory = db
    _seed_legacy(engine)
    migrate_curriculum(factory, tmp_path / "courses")  # 无 math.json 目录时跳过
    migrate_legacy_data(factory)
    # Fix 1：默认不 drop qt_sources_legacy —— 备份快照语义，与 qt_selections/qt_downloads 一致
    with factory() as session:
        legacy = session.execute(
            text("SELECT source_id, download_id FROM qt_sources_legacy")
        ).fetchall()
        assert len(legacy) == 1
        assert legacy[0][0] == "src_1"
        assert legacy[0][1] == "dl_1"
        new = session.execute(text("SELECT source_id, book_id FROM qt_sources")).fetchall()
        assert len(new) == 1
        assert new[0][0].startswith("src_")


def test_migrate_legacy_drop_legacy_drops_all_old_tables(db, tmp_path):
    engine, factory = db
    _seed_legacy(engine)
    migrate_legacy_data(factory, drop_legacy=True)
    for old in ("qt_selections", "qt_downloads", "qt_sources_legacy"):
        assert not inspect(engine).has_table(old)
    for new in ("qt_sources", "qt_knowledge", "qt_books"):
        assert inspect(engine).has_table(new)


def test_migrate_legacy_fresh_db_creates_qt_sources(empty_db):
    engine, factory = empty_db
    stats = migrate_legacy_data(factory)
    # Fix 3：全新库无旧表也要补建新结构 qt_sources（0006 未建），供 add_source 使用
    assert stats == {"knowledge": 0, "books": 0, "sources": 0}
    assert inspect(engine).has_table("qt_sources")
    with factory() as session:
        cols = session.execute(text("PRAGMA table_info(qt_sources)")).fetchall()
        assert any(row[1] == "book_id" for row in cols)


def test_migrate_legacy_resumes_from_qt_sources_legacy(db, tmp_path):
    engine, factory = db
    _seed_legacy(engine)
    migrate_curriculum(factory, tmp_path / "courses")
    migrate_legacy_data(factory)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM qt_sources"))  # 模拟改名后写入中途失败：新表清空
    # Fix 2：续跑从 qt_sources_legacy 读旧行重放，knowledge/books 走已有幂等门跳过
    migrate_legacy_data(factory)
    with factory() as session:
        sources = session.execute(text("SELECT source_id, book_id FROM qt_sources")).fetchall()
        assert len(sources) == 1
        assert sources[0][0].startswith("src_")
        assert session.execute(text("SELECT COUNT(*) FROM qt_knowledge")).fetchone()[0] == 1
        assert session.execute(text("SELECT COUNT(*) FROM qt_books")).fetchone()[0] == 2