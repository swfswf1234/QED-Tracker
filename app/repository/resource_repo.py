"""资源仓储"""

from sqlalchemy.orm import Session
from app.repository import BaseRepository
from app.models.resource import Resource


class ResourceRepo(BaseRepository[Resource]):
    def __init__(self, db: Session):
        super().__init__(db, Resource)

    def get_by_type(self, rtype: str) -> list[Resource]:
        return self.db.query(Resource).filter(Resource.resource_type == rtype).all()
