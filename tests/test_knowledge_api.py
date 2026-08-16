"""五层模型 API 端点定向测试（QED-031）：knowledge/books/sources 契约 + 彻底隐藏。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.api.main import create_app
from qed_tracker.config import load_settings
from qed_tracker.db.knowledge_repository import KnowledgeRepository
from qed_tracker.db.models import Base, BookStatus, KnowledgeStatus, QedCourse, QedDomain


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
    repo = KnowledgeRepository(lambda: factory())
    yield repo
    engine.dispose()


@pytest.fixture
def client(tmp_path, repo):
    settings = load_settings(data_root=tmp_path)
    app = create_app(settings, knowledge_repository=repo)
    with TestClient(app) as test_client:
        yield test_client


def _seed_knowledge(repo: KnowledgeRepository, *, name: str = "数学分析 套一", status: str = "draft"):
    knowledge = repo.create_knowledge(
        domain_id="math", course_id="01_math_analysis", kind="tutorial", set_no="1", name=name,
    )
    if status == "confirmed":
        repo.confirm_knowledge(knowledge.knowledge_id, textbook_ref={"title": "微积分学教程"},
                               exercise_ref={"title": "习题集"})
    elif status == "rejected":
        repo.reject_knowledge(knowledge.knowledge_id, reason="版本旧", by="web")
    return knowledge


def test_knowledge_list_filters_hidden(client, repo):
    _seed_knowledge(repo)
    _seed_knowledge(repo, name="坏书", status="rejected")
    response = client.get("/api/v1/knowledge")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_knowledge_detail_with_books(client, repo):
    knowledge = _seed_knowledge(repo)
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="微积分学教程",
                            authors=["菲赫金哥尔茨"])
    response = client.get(f"/api/v1/knowledge/{knowledge.knowledge_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["knowledge_id"] == knowledge.knowledge_id
    assert len(body["books"]) == 1
    assert body["books"][0]["book_id"] == book.book_id


def test_knowledge_confirm(client, repo):
    knowledge = _seed_knowledge(repo)
    response = client.post(f"/api/v1/knowledge/{knowledge.knowledge_id}/confirm", json={
        "textbook_ref": {"title": "微积分学教程", "version": "第8版"},
        "textbook_intro": "经典三卷本。",
    })
    assert response.status_code == 200
    assert response.json()["status"] == KnowledgeStatus.CONFIRMED.value


def test_knowledge_reject_requires_reason(client, repo):
    knowledge = _seed_knowledge(repo)
    response = client.post(f"/api/v1/knowledge/{knowledge.knowledge_id}/reject", json={})
    assert response.status_code == 422
    response = client.post(f"/api/v1/knowledge/{knowledge.knowledge_id}/reject",
                           json={"reason": "版本旧"})
    assert response.status_code == 200


def test_knowledge_invalid_transition_409(client, repo):
    knowledge = _seed_knowledge(repo, status="confirmed")
    response = client.post(f"/api/v1/knowledge/{knowledge.knowledge_id}/complete")
    assert response.status_code == 409  # 无书行，不能 completed


def test_book_create_and_transitions(client, repo):
    knowledge = _seed_knowledge(repo)
    response = client.post("/api/v1/books", json={
        "knowledge_id": knowledge.knowledge_id, "kind": "textbook", "title": "微积分学教程",
        "part": "第一册", "authors": ["菲赫金哥尔茨"],
    })
    assert response.status_code == 200
    book_id = response.json()["book_id"]
    assert client.post(f"/api/v1/books/{book_id}/decide").status_code == 200
    assert client.post(f"/api/v1/books/{book_id}/start").status_code == 200
    r = client.post(f"/api/v1/books/{book_id}/complete", json={
        "sha256": "c" * 64, "relative_path": "raw/books/x.pdf", "page_count": 100,
    })
    assert r.status_code == 200
    assert r.json()["status"] == BookStatus.DOWNLOADED.value
    assert client.post(f"/api/v1/books/{book_id}/verify").status_code == 200


def test_book_register_manual_direct(client, repo, tmp_path, pdf_bytes):
    knowledge = _seed_knowledge(repo)
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="微积分学教程",
                            authors=["菲赫金哥尔茨"])
    rel = "raw/books/manual.pdf"
    target = tmp_path / rel
    target.parent.mkdir(parents=True)
    target.write_bytes(pdf_bytes)
    response = client.post(f"/api/v1/books/{book.book_id}/register", json={"relative_path": rel})
    assert response.status_code == 200
    assert response.json()["status"] == BookStatus.DOWNLOADED.value


def test_book_reject_hidden(client, repo):
    knowledge = _seed_knowledge(repo)
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="坏书")
    response = client.post(f"/api/v1/books/{book.book_id}/reject", json={"reason": "不适用"})
    assert response.status_code == 200
    assert client.get(f"/api/v1/knowledge/{knowledge.knowledge_id}").json()["books"] == []


def test_sources_endpoint(client, repo):
    knowledge = _seed_knowledge(repo)
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="微积分学教程")
    response = client.post(f"/api/v1/books/{book.book_id}/sources", json={
        "channel": "manual", "ok": True, "download_url": "http://x",
    })
    assert response.status_code == 200
    rows = client.get(f"/api/v1/books/{book.book_id}/sources").json()
    assert len(rows) == 1
    assert rows[0]["channel"] == "manual"


def test_knowledge_detail_unknown_404(client):
    assert client.get("/api/v1/knowledge/kn_nope").status_code == 404


def test_book_transition_unknown_404(client):
    assert client.post("/api/v1/books/bk_nope/decide").status_code == 404


def test_book_register_rejects_non_pdf(client, repo, tmp_path):
    knowledge = _seed_knowledge(repo)
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="微积分学教程")
    rel = "raw/books/not_pdf.txt"
    target = tmp_path / rel
    target.parent.mkdir(parents=True)
    target.write_text("not a pdf", encoding="utf-8")
    response = client.post(f"/api/v1/books/{book.book_id}/register", json={"relative_path": rel})
    assert response.status_code == 400
    assert repo.get_book(book.book_id).status == BookStatus.CANDIDATE.value  # 状态不变


def test_book_register_rejects_path_traversal(client, repo):
    knowledge = _seed_knowledge(repo)
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="微积分学教程")
    response = client.post(f"/api/v1/books/{book.book_id}/register", json={"relative_path": "../escape.pdf"})
    assert response.status_code == 400


def test_complete_validates_sha256_format(client, repo):
    knowledge = _seed_knowledge(repo)
    book = repo.create_book(knowledge.knowledge_id, kind="textbook", title="微积分学教程")
    response = client.post(f"/api/v1/books/{book.book_id}/complete",
                           json={"sha256": "not-hex", "relative_path": "raw/books/x.pdf"})
    assert response.status_code == 422


def test_knowledge_rejected_hidden_in_list(client, repo):
    _seed_knowledge(repo)
    _seed_knowledge(repo, name="坏书", status="rejected")
    response = client.get("/api/v1/knowledge?status=rejected")
    assert response.status_code == 200
    assert response.json() == []
