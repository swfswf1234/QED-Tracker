"""兼容层 — 保持 v0.1 API 不变，底层委托 app/db/

旧代码 (scripts, repository) 仍通过 from app.core.database import get_conn 等引用。
新代码应直接使用 app.db.session.create_engine_from_config()。
"""

from app.core.config import settings
from app.db.session import create_engine_from_config

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine_from_config()
        _engine.connect()
    return _engine


def get_db():
    """FastAPI Depends 兼容"""
    engine = _get_engine()
    db = engine.get_session()
    try:
        yield db
    finally:
        db.close()


def get_conn():
    """脚本用连接"""
    engine = _get_engine()
    return engine.get_session()


def init_tables():
    engine = _get_engine()
    return engine.init_tables()


def check_db():
    engine = _get_engine()
    return engine.check_connection()


from sqlalchemy.orm import declarative_base
Base = declarative_base()
