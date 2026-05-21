"""教科书仓储"""

from sqlalchemy.orm import Session
from app.repository import BaseRepository
from app.models.textbook import Textbook


class TextbookRepo(BaseRepository[Textbook]):
    def __init__(self, db: Session):
        super().__init__(db, Textbook)

    def get_by_course(self, course: str) -> list[Textbook]:
        return self.db.query(Textbook).filter(Textbook.course == course).all()

    def exists_by_path(self, path: str) -> bool:
        return self.db.query(Textbook).filter(Textbook.local_pdf_path == path).first() is not None
