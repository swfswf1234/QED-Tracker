"""手动知识导入链路（QED-050/QED-061）：领域 JSON 校验器 + POST /domains/import 契约 + 书籍导入。

守护面：
- validate_domain manual@v1 与 validate_course 数据文件版契约；
- /domains/import：内联与 file_path 两模式、只落盘不落库、错误码；
- /books/{id}/import：人工导入落盘（数据根相对路径 + domain_id）；
- 知识正本合规：docs/knowledge/ 通过对应校验器。
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
            {"course_id": "test_analysis", "name": "数学分析", "track": "分析学", "stage": "基础",
             "aliases": ["微积分"], "summary": "测试课程简介。", "prerequisites": []},
            {"course_id": "test_advanced", "name": "高等数学", "track": "", "stage": "主干",
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
        ({"courses": [{"course_id": "course_x", "name": "n", "track": "", "stage": "主", "summary": "简介",
                       "prerequisites": []}]}, "stage 必须是 stages"),
        ({"courses": [{"course_id": "course_y", "name": "n", "track": "不存在的方向", "stage": "基础",
                       "summary": "简介", "prerequisites": []}]}, "track 必须逐字取自 classic_tracks"),
        ({"courses": [{"course_id": "a1", "name": "n", "track": "", "stage": "基础", "summary": "s",
                       "prerequisites": ["ghost"]},
                      {"course_id": "a2", "name": "n2", "track": "", "stage": "基础", "summary": "s",
                       "prerequisites": []}]}, "引用不在本批课程"),
        ({"courses": [{"course_id": "a1", "name": "n", "track": "", "stage": "基础", "summary": "s",
                       "prerequisites": ["a2"]},
                      {"course_id": "a2", "name": "n2", "track": "", "stage": "基础", "summary": "s",
                       "prerequisites": ["a1"]}]}, "存在循环"),
    ],
)
def test_validate_domain_rejects(overrides, needle: str) -> None:
    with pytest.raises(KnowledgeImportError, match=needle):
        validate_domain(_domain_ok(**overrides))


# ---------------- 校验器（validate_course，数据文件版） ----------------


def _ref(title: str = "教材", roles: list[str] | None = None) -> dict:
    return {
        "title": title, "part": "",
        "authors": [{"name": "作者", "role": "author"}],
        "publisher": "", "edition": "", "year": None, "language": "zh",
        "roles": roles or ["textbook"],
    }


def _course_ok(**overrides) -> dict:
    value = {
        "domain_id": "math-advanced",
        "course_id": "math_analysis",
        "course_name": "数学分析",
        "tutorials": [{
            "knowledge_id": "kt-mathanalysis-1",
            "kind": "tutorial",
            "set_no": "1",
            "name": "教程1：测试教程",
            "position": "beginner",
            "intro": "教材简介。" * 40,
            "textbook_ref": [_ref()],
            "exercise_ref": None,
            "parallel_ref": None,
        }],
    }
    value.update(overrides)
    return value


def test_validate_course_happy_path() -> None:
    value = _course_ok()
    assert validate_course(value) is value


@pytest.mark.parametrize(
    "overrides, needle",
    [
        ({"tutorials": []}, "tutorials 必须为 1~6 套"),
        ({"domain_id": "Bad"}, "domain_id"),
        ({"course_id": "Bad"}, "course_id"),
        ({"tutorials": [{"set_no": "", "name": "n", "position": "beginner", "intro": "x" * 130,
                         "textbook_ref": [_ref()]}]}, "set_no"),
        ({"tutorials": [{"set_no": "1", "name": "n", "position": "bad", "intro": "x" * 130,
                         "textbook_ref": [_ref()]}]}, "position"),
        ({"tutorials": [{"set_no": "1", "name": "n", "position": "beginner", "intro": "短",
                         "textbook_ref": [_ref()]}]}, "至少 120 字"),
        ({"tutorials": [{"set_no": "1", "name": "n", "position": "beginner", "intro": "x" * 130,
                         "textbook_ref": []}]}, "textbook_ref"),
        ({"tutorials": [{"set_no": "1", "name": "n", "position": "beginner", "intro": "x" * 130,
                         "textbook_ref": [{"title": "t", "authors": [], "roles": ["textbook"]}]}]}, "authors"),
        ({"tutorials": [{"set_no": "1", "name": "n", "position": "beginner", "intro": "x" * 130,
                         "textbook_ref": [_ref(roles=["notes"])]}]}, "roles"),
    ],
)
def test_validate_course_rejects(overrides, needle: str) -> None:
    with pytest.raises(KnowledgeImportError, match=needle):
        validate_course(_course_ok(**overrides))


# ---------------- API：POST /domains/import（只落盘 + 已生成） ----------------


@pytest.fixture
def repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'kn.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    from qed_tracker.db.engine import utc_now

    now = utc_now()
    session.add(QedDomain(domain_id="test-math", name="测试数学", description="d", stages=["基础"],
                          created_at=now, updated_at=now))
    session.add(QedDomain(domain_id="math", name="数学", description="d", stages=["基础"],
                          created_at=now, updated_at=now))
    session.add(QedCourse(course_id="math_analysis", domain_id="math", sort_order=1, name="数学分析",
                          aliases=[], stage="基础", prerequisites=[], related_targets=[],
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


def test_domain_import_writes_file_and_sets_generated(client, repo, tmp_path) -> None:
    response = client.post("/api/v1/domains/import", json={"domain": _domain_ok()})
    assert response.status_code == 200
    body = response.json()
    assert body["domain_id"] == "test-math"
    assert body["exploration_stage"] == "已生成"
    assert (tmp_path / "raw" / "test-math" / "domains.json").exists()
    assert repo.get_domain("test-math").exploration_stage == "已生成"


def test_domain_import_is_idempotent_overwrite(client, tmp_path) -> None:
    payload = _domain_ok()
    assert client.post("/api/v1/domains/import", json={"domain": payload}).status_code == 200
    payload["description"] = "更新后的描述。"
    response = client.post("/api/v1/domains/import", json={"domain": payload})
    assert response.status_code == 200
    data = json.loads((tmp_path / "raw" / "test-math" / "domains.json").read_text(encoding="utf-8"))
    assert data["description"] == "更新后的描述。"


def test_domain_import_accepts_file_path_mode(client, tmp_path) -> None:
    file_path = tmp_path / "domain.json"
    file_path.write_text(json.dumps(_domain_ok(), ensure_ascii=False), encoding="utf-8")
    response = client.post("/api/v1/domains/import", json={"file_path": str(file_path)})
    assert response.status_code == 200
    assert response.json()["domain_id"] == "test-math"


def test_domain_import_rejects_invalid_payload(client) -> None:
    payload = _domain_ok(courses=[{"course_id": "x", "name": "n", "track": "", "stage": "坏档",
                                   "summary": "s", "prerequisites": []}])
    response = client.post("/api/v1/domains/import", json={"domain": payload})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_PARAMS"


def test_domain_import_requires_domain_or_file_path(client) -> None:
    assert client.post("/api/v1/domains/import", json={}).status_code == 422


def test_domain_import_unreadable_file_400(client) -> None:
    assert client.post("/api/v1/domains/import", json={"file_path": "N:/not/exist.json"}).status_code == 400


def test_domain_import_unknown_domain_404(client) -> None:
    payload = _domain_ok(domain="ghost-domain")
    response = client.post("/api/v1/domains/import", json={"domain": payload})
    assert response.status_code == 404


def test_domain_import_no_db_409(tmp_path) -> None:
    from dataclasses import replace

    settings = replace(load_settings(data_root=tmp_path), db_password="")
    app = create_app(settings)
    with TestClient(app) as test_client:
        response = test_client.post("/api/v1/domains/import", json={"domain": _domain_ok()})
        assert response.status_code == 409


# ---------------- API：POST /books/{id}/import ----------------


def _make_pdf(path: Path) -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(612, 792)
    with path.open("wb") as stream:
        writer.write(stream)


def _seed_book(repo: KnowledgeRepository, *, domain_id: str = "math-advanced") -> str:
    knowledge = repo.create_knowledge(course_id="math_analysis", set_no="9", name="教程9：导入测试")
    book = repo.create_book("mathanalysis-b09", title="导入测试教材",
                            authors=[{"name": "Tester", "role": "author"}], language="zh", domain_id=domain_id)
    knowledge.textbook_ref = [{"book_id": book.book_id, "title": book.title}]
    session = repo.session_factory()
    session.merge(knowledge)
    session.commit()
    session.close()
    return book.book_id


def test_book_import_local_pdf_to_data_root(client, repo, tmp_path_factory) -> None:
    external = tmp_path_factory.mktemp("src")
    pdf = external / "manual.pdf"
    _make_pdf(pdf)
    book_id = _seed_book(repo)
    response = client.post(f"/api/v1/books/{book_id}/import", json={"file_path": str(pdf)})
    assert response.status_code == 200
    body = response.json()
    assert body["holding"] == "owned"
    assert body["file_path"].startswith("raw/math-advanced/math_analysis/")
    assert body["file_path"].endswith(".pdf")
    local = client.get("/api/v1/books/" + book_id + "/sources").json()
    assert any(s["channel"] == "local_import" and s["ok"] for s in local)


def test_book_import_target_path_override(client, repo, tmp_path_factory) -> None:
    external = tmp_path_factory.mktemp("src2")
    pdf = external / "custom.pdf"
    _make_pdf(pdf)
    book_id = _seed_book(repo)
    response = client.post(
        f"/api/v1/books/{book_id}/import",
        json={"file_path": str(pdf), "target_path": "raw/math-advanced/math_analysis/自定义.pdf"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["file_path"].startswith("raw/math-advanced/math_analysis/自定义_")
    assert body["file_path"].endswith(".pdf")


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
    assert client.post(f"/api/v1/books/{book_id}/import", json={"file_path": "N:/no.pdf"}).status_code == 404


def test_book_import_non_pdf_400(client, repo, tmp_path_factory) -> None:
    external = tmp_path_factory.mktemp("src4")
    txt = external / "not.pdf"
    txt.write_text("hello", encoding="utf-8")
    book_id = _seed_book(repo)
    assert client.post(f"/api/v1/books/{book_id}/import", json={"file_path": str(txt)}).status_code == 400


def test_book_import_requires_file_path(client, repo) -> None:
    book_id = _seed_book(repo)
    assert client.post(f"/api/v1/books/{book_id}/import", json={}).status_code == 422


def test_book_import_uses_book_domain_id(client, repo, tmp_path_factory) -> None:
    """QED-059 回归：book_import 使用书籍实际 domain_id 而非默认 math。"""
    external = tmp_path_factory.mktemp("cs_import")
    pdf = external / "algorithms.pdf"
    _make_pdf(pdf)
    book_id = _seed_book(repo, domain_id="computer-science")
    response = client.post(f"/api/v1/books/{book_id}/import", json={"file_path": str(pdf)})
    assert response.status_code == 200
    body = response.json()
    assert body["holding"] == "owned"
    assert body["file_path"].startswith("raw/computer-science/math_analysis/")
    assert body["file_path"].endswith(".pdf")


# ---------------- 知识正本合规（docs/knowledge/ = 契约守护） ----------------


def test_knowledge_docs_domain_conforms_to_contract() -> None:
    source = ROOT / "docs" / "knowledge" / "math-advanced.json"
    validate_domain(json.loads(source.read_text(encoding="utf-8")))


def test_knowledge_docs_computer_science_conforms_to_contract() -> None:
    source = ROOT / "docs" / "knowledge" / "computer-science.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    validate_domain(data)
    assert len(data["classic_tracks"]) == 3
    assert all(t["kind"] == "main" for t in data["classic_tracks"])


def test_knowledge_docs_courses_conform_to_contract() -> None:
    for course_file in sorted((ROOT / "docs" / "knowledge" / "math-advanced").glob("*.json")):
        if course_file.name == "template.json":
            continue  # 契约范本含占位符，不参与 validate_course
        validate_course(json.loads(course_file.read_text(encoding="utf-8")))
