"""手动知识导入链路（QED-050）：领域 JSON 校验器 + POST /domains/import 契约。

守护面：
- validate_domain manual@v1：slug/方向 kind/stages 值域/track=main/前置引用与无环/一句话；
- /domains/import：内联与 file_path 两模式、幂等 upsert、exploration_stage=已完成、错误码；
- 知识正本合规：docs/knowledge/math-advanced.json 及其课程 JSON 均通过对应校验器（正本=契约守护）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.api.main import create_app
from qed_tracker.application.knowledge_import import KnowledgeImportError, validate_course, validate_domain
from qed_tracker.config import load_settings
from qed_tracker.db.knowledge_repository import KnowledgeRepository
from qed_tracker.db.models import Base, QedCourse, QedDomain

ROOT = Path(__file__).resolve().parent.parent

# ---------------- 校验器（validate_domain） ----------------


def _domain_ok(**overrides) -> dict:
    value = {
        "domain": "test-math",
        "name": "测试数学",
        "scope": "大学以上数学专业课程",
        "description": "测试领域描述。",
        "level": "本科-硕士",
        "entry_requirements": "入门基础扎实",
        "classic_tracks": [
            {"name": "分析学", "summary": "连续与变化", "kind": "main"},
            {"name": "计算数学", "summary": "可计算化", "kind": "branch"},
        ],
        "stages": ["基础", "主干", "分支", "前沿"],
        "anchor_courses": ["数学分析"],
        "courses": [
            {"slug": "test_analysis", "name": "数学分析", "track": "分析学", "stage": "基础",
             "aliases": ["微积分"], "summary": "测试课程简介。", "prerequisites": []},
            {"slug": "test_advanced", "name": "高等数学", "track": "", "stage": "主干",
             "aliases": [], "summary": "测试课程简介之二。", "prerequisites": ["test_analysis"]},
        ],
        "extensions_planned": [],
    }
    value.update(overrides)
    return value


def test_validate_domain_happy_path() -> None:
    value = _domain_ok()
    assert validate_domain(value) is value


@pytest.mark.parametrize(
    "overrides, needle",
    [
        ({"domain": "Math"}, "domain 必须匹配"),
        ({"name": ""}, "name 不能为空"),
        ({"entry_requirements": ["微积分基础"]}, "entry_requirements 必须是字符串"),
        ({"classic_tracks": [{"name": "t", "summary": "s", "kind": "invalid"}]}, "kind 必须是 main"),
        ({"classic_tracks": [{"name": "t", "summary": "s"}]}, "kind 必须是 main"),
        ({"classic_tracks": [{"name": "t", "summary": f"{'s' * 201}"}]}, "超长"),
        ({"stages": ["本科基础"]}, "stages 值域"),
        ({"stages": ["基础", "基础"]}, "stages 存在重复值"),
        ({"courses": []}, "courses 必须为非空数组"),
        ({"courses": [{"slug": "course_x", "name": "n", "track": "", "stage": "主", "summary": "简介",
                       "prerequisites": []}]}, "stage 必须是 stages"),
        ({"courses": [{"slug": "course_y", "name": "n", "track": "不存在的方向", "stage": "基础",
                       "summary": "简介", "prerequisites": []}]}, "track 必须逐字取自 classic_tracks"),
        ({"courses": [{"slug": "a1", "name": "n", "track": "", "stage": "基础", "summary": "s",
                      "prerequisites": ["ghost"]},
                      {"slug": "a2", "name": "n2", "track": "", "stage": "基础", "summary": "s",
                       "prerequisites": []}]}, "引用不在本批课程"),
        ({"courses": [{"slug": "a1", "name": "n", "track": "", "stage": "基础", "summary": "s",
                      "prerequisites": ["a2"]},
                      {"slug": "a2", "name": "n2", "track": "", "stage": "基础", "summary": "s",
                       "prerequisites": ["a1"]}]}, "存在循环"),
    ],
)
def test_validate_domain_rejects(overrides, needle: str) -> None:
    with pytest.raises(KnowledgeImportError, match=needle):
        validate_domain(_domain_ok(**overrides))


def test_validate_course_happy_path() -> None:
    value = _course_ok()
    assert validate_course(value) is value


def _course_ok(**overrides) -> dict:
    value = {
        "meta": {"contract": "course-knowledge/manual@v1", "confirmed_at": "2026-08-29"},
        "domain": "math-advanced",
        "course": {"course_id": "01_math_analysis", "name": "数学分析", "aliases": ["微积分"]},
        "tutorials": [
            {"set_no": "1", "set_name": "教程1：测试教程",
             "textbook": {"title": "测试教材", "original_title": "Test", "authors": ["Tester"],
                          "version": {"edition": "第1版"}, "roles": ["textbook", "exercises"],
                          "position": "beginner", "intro": "教材简介。",
                          "target_path": "raw/math-advanced/01_math_analysis/测试教材.pdf"},
             "exercise": None, "reason": "理由"},
            {"set_no": "2", "set_name": "教程2：配置",
             "textbook": {"title": "配置教材", "authors": ["Tester2"], "roles": ["textbook"],
                          "position": "advanced", "intro": "教材简介之二。"},
             "exercise": {"title": "测试习题集", "authors": ["Tester3"], "roles": ["exercises"],
                          "position": "advanced", "intro": "习题集简介。"},
             "reason": ""},
        ],
    }
    value.update(overrides)
    return value


@pytest.mark.parametrize(
    "overrides, needle",
    [
        ({"tutorials": []}, "tutorials 必须为 1~4 套"),
        ({"tutorials": [{"set_no": "1", "set_name": "s", "textbook": {"title": "t", "authors": [],
                                                                     "roles": ["textbook"], "intro": "i"},
                        "exercise": None, "reason": "r"}]}, "textbook.authors"),
        ({"tutorials": [{"set_no": "1", "set_name": "s",
                         "textbook": {"title": "t", "authors": ["a"], "roles": ["exercises"],
                                      "intro": "i"},
                         "exercise": None, "reason": "r"}]}, "textbook.roles"),
        ({"tutorials": [{"set_no": "1", "set_name": "s",
                         "textbook": {"title": "t", "authors": ["a"], "roles": ["textbook"],
                                      "intro": "i", "target_path": "/abs/out.pdf"},
                         "exercise": None, "reason": "r"}]}, "数据根相对路径"),
        ({"tutorials": [{"set_no": "1", "set_name": "s",
                         "textbook": {"title": "t", "authors": ["a"], "roles": ["textbook"],
                                      "intro": "i"},
                         "exercise": {"title": "x"}, "reason": "r"}]}, "exercise.authors"),
    ],
)
def test_validate_course_rejects(overrides, needle: str) -> None:
    with pytest.raises(KnowledgeImportError, match=needle):
        validate_course(_course_ok(**overrides))


# ---------------- API：POST /domains/import ----------------


@pytest.fixture
def repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'kn.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    from qed_tracker.database import utc_now

    now = utc_now()
    session.add(QedDomain(domain_id="math", name="数学", description="d", stages=["本科基础"],
                          created_at=now, updated_at=now))
    session.add(QedCourse(course_id="01_math_analysis", domain_id="math", sort_order=1, name="数学分析",
                          aliases=[], stage="本科基础", prerequisites=[], related_targets=[],
                          created_at=now, updated_at=now))
    session.commit()
    yield KnowledgeRepository(lambda: factory())
    engine.dispose()


@pytest.fixture
def client(tmp_path, repo):
    settings = load_settings(data_root=tmp_path)
    app = create_app(settings, knowledge_repository=repo)
    with TestClient(app) as test_client:
        yield test_client


def test_domain_import_creates_domain_and_courses(client, repo) -> None:
    response = client.post("/api/v1/domains/import", json={"domain": _domain_ok()})
    assert response.status_code == 200
    body = response.json()
    assert body["domain_id"] == "test-math"
    assert body["courses_created"] == 2
    assert body["courses_updated"] == 0
    assert body["exploration_stage"] == "已完成"

    domain = repo.get_domain("test-math")
    assert domain.name == "测试数学"
    assert domain.exploration_stage == "已完成"
    assert domain.classic_tracks[0]["kind"] == "main"
    course = repo.get_course("test_analysis")
    assert course.stage == "基础"
    assert course.description == "测试课程简介。"


def test_domain_import_is_idempotent_upsert(client, repo) -> None:
    payload = _domain_ok()
    assert client.post("/api/v1/domains/import", json={"domain": payload}).status_code == 200
    payload["description"] = "更新后的描述。"
    response = client.post("/api/v1/domains/import", json={"domain": payload})
    assert response.status_code == 200
    body = response.json()
    assert body["courses_created"] == 0
    assert body["courses_updated"] == 2
    assert repo.get_domain("test-math").description == "更新后的描述。"


def test_domain_import_accepts_file_path_mode(client, tmp_path) -> None:
    file_path = tmp_path / "domain.json"
    file_path.write_text(json.dumps(_domain_ok(), ensure_ascii=False), encoding="utf-8")
    response = client.post("/api/v1/domains/import", json={"file_path": str(file_path)})
    assert response.status_code == 200
    assert response.json()["domain_id"] == "test-math"


def test_domain_import_rejects_invalid_payload(client) -> None:
    payload = _domain_ok(courses=[{"slug": "x", "name": "n", "track": "", "stage": "坏档",
                                   "summary": "s", "prerequisites": []}])
    response = client.post("/api/v1/domains/import", json={"domain": payload})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_PARAMS"


def test_domain_import_requires_domain_or_file_path(client) -> None:
    response = client.post("/api/v1/domains/import", json={})
    assert response.status_code == 422


def test_domain_import_unreadable_file_400(client) -> None:
    response = client.post("/api/v1/domains/import", json={"file_path": "N:/not/exist.json"})
    assert response.status_code == 400


def test_domain_import_no_db_409(tmp_path) -> None:
    from dataclasses import replace

    settings = replace(load_settings(data_root=tmp_path), db_password="")
    app = create_app(settings)
    with TestClient(app) as test_client:
        response = test_client.post("/api/v1/domains/import", json={"domain": _domain_ok()})
        assert response.status_code == 409


# ---------------- API：A2 source=manual 扩展（QED-050 M5） ----------------


def _tutorial_import(set_no: str = "1", **overrides) -> dict:
    item = {
        "set_no": set_no,
        "set_name": f"教程{set_no}：测试教程",
        "textbook": {"title": "测试教材", "authors": ["Tester"], "roles": ["textbook", "exercises"],
                     "position": "beginner", "intro": f"教材简介{set_no}。",
                     "target_path": f"raw/math-advanced/01_math_analysis/测试教材_{set_no}.pdf"},
        "exercise": None,
        "reason": "理由",
    }
    item.update(overrides)
    return item


def test_manual_source_adopt_persists_target_path(client, repo) -> None:
    response = client.post("/api/v1/courses/01_math_analysis/knowledge",
                           json={"tutorials": [_tutorial_import("1")], "source": "manual"})
    assert response.status_code == 201
    assert response.json()["created"][0]["status"] == "draft"
    rows = client.get("/api/v1/knowledge", params={"course_id": "01_math_analysis"}).json()
    ref = rows[0]["textbook_ref"]
    assert ref["target_path"] == "raw/math-advanced/01_math_analysis/测试教材_1.pdf"


def test_manual_source_requires_textbook_roles(client) -> None:
    bad = _tutorial_import("1", textbook={"title": "无角色教材"})
    response = client.post("/api/v1/courses/01_math_analysis/knowledge",
                           json={"tutorials": [bad], "source": "manual"})
    assert response.status_code == 422


def test_manual_source_rejects_unknown_source(client) -> None:
    response = client.post("/api/v1/courses/01_math_analysis/knowledge",
                           json={"tutorials": [_tutorial_import("1")], "source": "scheduled"})
    assert response.status_code == 422


def test_manual_source_exercise_roles_required(client) -> None:
    bad_exercise = _tutorial_import(
        "1",
        textbook={"title": "教材", "roles": ["textbook"], "intro": "简介。"},
        exercise={"title": "习题集", "roles": ["notes"]},
    )
    response = client.post("/api/v1/courses/01_math_analysis/knowledge",
                           json={"tutorials": [bad_exercise], "source": "manual"})
    assert response.status_code == 422


# ---------------- API：POST /books/{id}/import（QED-050 M6） ----------------


def _make_pdf(path: Path) -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(612, 792)
    with path.open("wb") as stream:
        writer.write(stream)


def _seed_book(repo: KnowledgeRepository) -> str:
    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="9", name="教程9：导入测试")
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="导入测试教材",
                            authors=["Tester"])
    return book.book_id


def test_book_import_local_pdf_to_data_root(client, repo, tmp_path_factory) -> None:
    external = tmp_path_factory.mktemp("src")
    pdf = external / "manual.pdf"
    _make_pdf(pdf)
    book_id = _seed_book(repo)
    response = client.post(f"/api/v1/books/{book_id}/import", json={"file_path": str(pdf)})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "downloaded"
    assert body["relative_path"].startswith("raw/math/01_math_analysis/")
    assert body["relative_path"].endswith(".pdf")
    local = client.get("/api/v1/books/" + book_id + "/sources").json()
    assert any(s["channel"] == "local_import" and s["ok"] for s in local)


def test_book_import_target_path_override(client, repo, tmp_path_factory) -> None:
    external = tmp_path_factory.mktemp("src2")
    pdf = external / "custom.pdf"
    _make_pdf(pdf)
    book_id = _seed_book(repo)
    response = client.post(
        f"/api/v1/books/{book_id}/import",
        json={"file_path": str(pdf), "target_path": "raw/math-advanced/01_math_analysis/自定义.pdf"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["relative_path"].startswith("raw/math-advanced/01_math_analysis/自定义_")
    assert body["relative_path"].endswith(".pdf")


def test_book_import_rejects_path_escape(client, repo, tmp_path_factory) -> None:
    external = tmp_path_factory.mktemp("src3")
    pdf = external / "esc.pdf"
    _make_pdf(pdf)
    book_id = _seed_book(repo)
    response = client.post(
        f"/api/v1/books/{book_id}/import",
        json={"file_path": str(pdf), "target_path": "../escape.pdf"},
    )
    assert response.status_code == 400


def test_book_import_missing_file_404(client, repo) -> None:
    book_id = _seed_book(repo)
    response = client.post(f"/api/v1/books/{book_id}/import", json={"file_path": "N:/no.pdf"})
    assert response.status_code == 404


def test_book_import_non_pdf_400(client, repo, tmp_path_factory) -> None:
    external = tmp_path_factory.mktemp("src4")
    txt = external / "not.pdf"
    txt.write_text("hello", encoding="utf-8")
    book_id = _seed_book(repo)
    response = client.post(f"/api/v1/books/{book_id}/import", json={"file_path": str(txt)})
    assert response.status_code == 400


def test_book_import_requires_file_path(client, repo) -> None:
    book_id = _seed_book(repo)
    response = client.post(f"/api/v1/books/{book_id}/import", json={})
    assert response.status_code == 422


# ---------------- G2 修复：knowledge complete 回写课程探索状态 ----------------


def test_complete_knowledge_updates_course_stage(client, repo) -> None:
    knowledge = repo.create_knowledge(domain_id="math", course_id="01_math_analysis",
                                      kind="tutorial", set_no="8", name="教程8：回写测试")
    repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref={"title": "教材"})
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="回写测试教材",
                            authors=["T"])
    repo.complete_download(book.book_id, sha256="a" * 64,
                           relative_path="raw/math/01_math_analysis/回写测试.pdf")
    repo.verify_book(book.book_id)
    response = client.post(f"/api/v1/knowledge/{knowledge.knowledge_id}/complete")
    assert response.status_code == 200
    assert repo.get_course("01_math_analysis").exploration_stage == "已完成"


# ---------------- 知识正本合规（docs/knowledge/ = 契约守护） ----------------


def test_knowledge_docs_domain_conforms_to_contract() -> None:
    source = ROOT / "docs" / "knowledge" / "math-advanced.json"
    validate_domain(json.loads(source.read_text(encoding="utf-8")))


def test_knowledge_docs_computer_science_conforms_to_contract() -> None:
    """QED-050：计算机领域范本（3 条主干方向 + 5 门基础/主干课）契约合规。"""
    source = ROOT / "docs" / "knowledge" / "computer-science.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    validate_domain(data)
    assert len(data["classic_tracks"]) == 3
    assert all(t["kind"] == "main" for t in data["classic_tracks"])
    assert 3 <= len(data["courses"]) <= 5
    assert all(c["stage"] in ("基础", "主干") for c in data["courses"])


def test_knowledge_docs_courses_conform_to_contract() -> None:
    for course_file in sorted((ROOT / "docs" / "knowledge" / "math-advanced").glob("*.json")):
        validate_course(json.loads(course_file.read_text(encoding="utf-8")))
