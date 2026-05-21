"""论文仓储"""

from sqlalchemy.orm import Session
from app.repository import BaseRepository
from app.models.paper import Paper


class PaperRepo(BaseRepository[Paper]):
    def __init__(self, db: Session):
        super().__init__(db, Paper)

    def get_by_arxiv_id(self, arxiv_id: str) -> Paper | None:
        return self.db.query(Paper).filter(Paper.arxiv_id == arxiv_id).first()

    def exists_by_arxiv_id(self, arxiv_id: str) -> bool:
        return self.db.query(Paper).filter(Paper.arxiv_id == arxiv_id).first() is not None
