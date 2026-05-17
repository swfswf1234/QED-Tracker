from sqlalchemy import Column, String, Text, DateTime, func
from app.core.database import Base
from app.core.utils import uuid_str


class Textbook(Base):
    __tablename__ = "textbooks"

    id = Column(String, primary_key=True, default=uuid_str)
    course = Column(String(50), nullable=False, index=True)
    title = Column(Text, nullable=False)
    author = Column(String(200))
    language = Column(String(10), default="zh")
    source = Column(String(100))
    source_url = Column(Text)
    local_pdf_path = Column(Text)
    local_solution_path = Column(Text)
    stage = Column(String(20))
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
