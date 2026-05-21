"""仓储基类 — 通用 CRUD"""

from __future__ import annotations

from typing import Generic, TypeVar, Optional, List
from sqlalchemy.orm import Session

from app.core.database import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    def __init__(self, db: Session, model_class: type[T]):
        self.db = db
        self.model = model_class

    def get(self, id: str) -> Optional[T]:
        return self.db.query(self.model).filter(self.model.id == id).first()

    def list(self, limit: int = 100, offset: int = 0) -> List[T]:
        return self.db.query(self.model).offset(offset).limit(limit).all()

    def create(self, obj: T) -> T:
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update(self, obj: T) -> T:
        self.db.merge(obj)
        self.db.commit()
        return obj

    def delete(self, obj: T) -> bool:
        self.db.delete(obj)
        self.db.commit()
        return True

    def count(self) -> int:
        return self.db.query(self.model).count()

    def exists(self, **filters) -> bool:
        q = self.db.query(self.model)
        for k, v in filters.items():
            q = q.filter(getattr(self.model, k) == v)
        return q.first() is not None
