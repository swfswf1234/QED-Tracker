from sqlalchemy import Column, String, Text, Boolean, DateTime, JSON, func
from app.core.database import Base
from app.core.utils import uuid_str


class Resource(Base):
    __tablename__ = "resources"

    id = Column(String, primary_key=True, default=uuid_str)
    resource_type = Column(String(20), nullable=False, index=True)
    title = Column(Text, nullable=False)
    url = Column(Text, nullable=False)
    description = Column(Text)
    course_tags = Column(JSON, default=list)
    author = Column(String(200))
    platform = Column(String(100))
    is_favorite = Column(Boolean, default=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=func.now())
