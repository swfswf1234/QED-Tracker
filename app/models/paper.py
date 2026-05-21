from sqlalchemy import Column, String, Text, Date, DateTime, JSON, func
from app.core.database import Base
from app.core.utils import uuid_str


class Paper(Base):
    __tablename__ = "papers"

    id = Column(String, primary_key=True, default=uuid_str)
    arxiv_id = Column(String(50), unique=True, nullable=False)
    title = Column(Text, nullable=False)
    title_cn = Column(Text)
    authors = Column(JSON, default=list)
    categories = Column(JSON, default=list)
    published_date = Column(Date)
    source_url = Column(Text)
    local_path = Column(Text)
    course_tags = Column(JSON, default=list)
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
