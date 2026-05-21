"""官方文档仓储"""

from sqlalchemy.orm import Session
from app.repository import BaseRepository
from app.models.official_doc import OfficialDoc


class OfficialDocRepo(BaseRepository[OfficialDoc]):
    def __init__(self, db: Session):
        super().__init__(db, OfficialDoc)

    def get_by_name(self, name: str) -> OfficialDoc | None:
        return self.db.query(OfficialDoc).filter(OfficialDoc.name == name).first()
