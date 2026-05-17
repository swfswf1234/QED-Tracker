"""测试：仓库 CRUD 操作（需要 PostgreSQL）"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import check_db
from app.core.config import settings

require_pg = pytest.mark.skipif(not check_db(), reason="PostgreSQL not available")


@require_pg
class TestTextbookRepo:
    def test_create_and_get(self, db_session):
        from app.models.textbook import Textbook
        from app.repository.textbook_repo import TextbookRepo
        repo = TextbookRepo(db_session)
        t = Textbook(course="01_test", title="Test Book", author="Tester")
        created = repo.create(t)
        assert created.id is not None
        assert created.title == "Test Book"
        fetched = repo.get(created.id)
        assert fetched is not None
        assert fetched.course == "01_test"

    def test_get_by_course(self, db_session):
        from app.models.textbook import Textbook
        from app.repository.textbook_repo import TextbookRepo
        repo = TextbookRepo(db_session)
        repo.create(Textbook(course="ca", title="A"))
        repo.create(Textbook(course="ca", title="B"))
        repo.create(Textbook(course="cb", title="C"))
        assert len(repo.get_by_course("ca")) == 2

    def test_exists_by_path(self, db_session):
        from app.models.textbook import Textbook
        from app.repository.textbook_repo import TextbookRepo
        repo = TextbookRepo(db_session)
        repo.create(Textbook(course="x", title="x", local_pdf_path="path/to/book.pdf"))
        assert repo.exists_by_path("path/to/book.pdf") is True
        assert repo.exists_by_path("other.pdf") is False


@require_pg
class TestPaperRepo:
    def test_create_and_get_by_arxiv(self, db_session):
        from app.models.paper import Paper
        from app.repository.paper_repo import PaperRepo
        repo = PaperRepo(db_session)
        p = Paper(arxiv_id="2601.99999", title="Test Paper")
        created = repo.create(p)
        assert created.id is not None
        fetched = repo.get_by_arxiv_id("2601.99999")
        assert fetched is not None
        assert fetched.title == "Test Paper"

    def test_exists_by_arxiv_id(self, db_session):
        from app.models.paper import Paper
        from app.repository.paper_repo import PaperRepo
        repo = PaperRepo(db_session)
        repo.create(Paper(arxiv_id="2601.11111", title="P1"))
        assert repo.exists_by_arxiv_id("2601.11111") is True
        assert repo.exists_by_arxiv_id("2601.22222") is False
