"""Tests for ResourceRepo query helpers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.resource import Resource
from app.repository.resource_repo import ResourceRepo


def make_resource(**overrides):
    data = {
        "resource_type": "article",
        "title": "Random Geometry",
        "url": "https://example.com/random-geometry",
        "description": "Probability and geometry article",
        "author": "Quanta Magazine",
        "platform": "Quanta",
        "course_tags": ["probability"],
    }
    data.update(overrides)
    return Resource(**data)


class TestResourceRepo:
    def test_get_by_url_and_exists_by_url(self, db_session):
        repo = ResourceRepo(db_session)
        created = repo.create(make_resource())

        fetched = repo.get_by_url("https://example.com/random-geometry")

        assert fetched is not None
        assert fetched.id == created.id
        assert repo.exists_by_url("https://example.com/random-geometry") is True
        assert repo.exists_by_url("https://example.com/missing") is False

    def test_search_matches_title_description_author_platform_and_url(self, db_session):
        repo = ResourceRepo(db_session)
        repo.create(make_resource(title="Discrete random matrices", author="Terence Tao", platform="Tao Blog"))
        repo.create(make_resource(
            title="PyTorch",
            url="https://github.com/pytorch/pytorch",
            description="Tensor library",
            author="PyTorch Team",
            platform="GitHub",
            resource_type="repo",
        ))

        assert [r.title for r in repo.search("random")] == ["Discrete random matrices"]
        assert [r.title for r in repo.search("tensor")] == ["PyTorch"]
        assert [r.title for r in repo.search("tao")] == ["Discrete random matrices"]
        assert [r.title for r in repo.search("github")] == ["PyTorch"]
        assert [r.title for r in repo.search("pytorch", resource_type="repo")] == ["PyTorch"]
        assert repo.search("pytorch", resource_type="article") == []

    def test_list_favorites_and_set_favorite(self, db_session):
        repo = ResourceRepo(db_session)
        article = repo.create(make_resource(title="Favorite Article"))
        repo.create(make_resource(title="Plain Article", url="https://example.com/plain"))

        updated = repo.set_favorite(article.id)

        assert updated is not None
        assert updated.is_favorite is True
        assert [r.title for r in repo.list_favorites()] == ["Favorite Article"]

    def test_set_favorite_returns_none_for_unknown_id(self, db_session):
        repo = ResourceRepo(db_session)

        assert repo.set_favorite("missing-id") is None
