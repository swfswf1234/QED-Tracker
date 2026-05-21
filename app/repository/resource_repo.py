"""资源仓储"""

from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.repository import BaseRepository
from app.models.resource import Resource


class ResourceRepo(BaseRepository[Resource]):
    def __init__(self, db: Session):
        super().__init__(db, Resource)

    def get_by_type(self, rtype: str) -> list[Resource]:
        return self.db.query(Resource).filter(Resource.resource_type == rtype).all()

    def get_by_url(self, url: str) -> Resource | None:
        return self.db.query(Resource).filter(Resource.url == url).first()

    def exists_by_url(self, url: str) -> bool:
        return self.get_by_url(url) is not None

    def search(self, keyword: str, resource_type: str | None = None) -> list[Resource]:
        pattern = f"%{keyword.strip()}%"
        query = self.db.query(Resource).filter(
            or_(
                Resource.title.ilike(pattern),
                Resource.description.ilike(pattern),
                Resource.author.ilike(pattern),
                Resource.platform.ilike(pattern),
                Resource.url.ilike(pattern),
            )
        )
        if resource_type:
            query = query.filter(Resource.resource_type == resource_type)
        return query.order_by(Resource.title.asc()).all()

    def list_favorites(self) -> list[Resource]:
        return (
            self.db.query(Resource)
            .filter(Resource.is_favorite.is_(True))
            .order_by(Resource.title.asc())
            .all()
        )

    def set_favorite(self, resource_id: str, value: bool = True) -> Resource | None:
        resource = self.get(resource_id)
        if resource is None:
            return None
        resource.is_favorite = value
        self.db.commit()
        self.db.refresh(resource)
        return resource
