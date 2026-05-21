from app.core.database import Base
from app.models.textbook import Textbook
from app.models.paper import Paper
from app.models.official_doc import OfficialDoc
from app.models.resource import Resource

__all__ = ["Base", "Textbook", "Paper", "OfficialDoc", "Resource"]
