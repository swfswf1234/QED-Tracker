"""测试：ORM 模型创建和字段"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.textbook import Textbook
from app.models.paper import Paper
from app.models.official_doc import OfficialDoc
from app.models.resource import Resource


class TestTextbook:
    def test_create(self):
        t = Textbook(course="01_math_analysis", title="Test Book", author="Author")
        assert t.course == "01_math_analysis"
        assert t.title == "Test Book"

    def test_author_optional(self):
        t = Textbook(course="x", title="y")
        assert t.author is None

    def test_stage_default_none(self):
        t = Textbook(course="x", title="y")
        assert t.stage is None

    def test_has_id_field(self):
        t = Textbook(course="x", title="y")
        assert hasattr(t, "id")


class TestPaper:
    def test_create(self):
        p = Paper(
            arxiv_id="2601.12345",
            title="A Test Paper",
            authors=["Alice", "Bob"],
            categories=["math.CA"],
        )
        assert p.arxiv_id == "2601.12345"
        assert p.title == "A Test Paper"

    def test_optional_fields(self):
        p = Paper(arxiv_id="2601.99999", title="Minimal")
        assert p.authors is None or p.authors == []
        assert p.categories is None or p.categories == []
        assert p.course_tags is None or p.course_tags == []

    def test_has_id_field(self):
        p = Paper(arxiv_id="2601.x", title="x")
        assert hasattr(p, "id")


class TestOfficialDoc:
    def test_create(self):
        d = OfficialDoc(name="pytorch", source_url="https://pytorch.org/")
        assert d.name == "pytorch"

    def test_version_default_none(self):
        d = OfficialDoc(name="sklearn", source_url="https://scikit-learn.org/")
        assert d.version is None


class TestResource:
    def test_create_blog(self):
        r = Resource(
            resource_type="blog",
            title="Great Math Blog",
            url="https://example.com/blog",
        )
        assert r.resource_type == "blog"
        assert not r.is_favorite

    def test_default_fields(self):
        r = Resource(resource_type="video", title="Tutorial", url="https://youtu.be/test")
        assert r.course_tags is None or r.course_tags == []
        # is_favorite 默认值为 False，由服务端设置；刷新数据库前为 None
        assert r.is_favorite is None or r.is_favorite is False
