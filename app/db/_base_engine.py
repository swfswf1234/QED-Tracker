"""SQL 引擎公共基类 — 消除 mysql.py / postgresql.py 重复"""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.config import settings
from app.db.base import DatabaseEngine
from app.models import Base as ModelsBase


class BaseSQLEngine(DatabaseEngine):
    """SQL 数据库引擎公共实现"""

    DRIVER = ""

    def __init__(self, cfg: dict | None = None):
        self._cfg = cfg or {}
        self._engine = None
        self._session_factory = None

    @property
    def url(self) -> str:
        raise NotImplementedError

    def connect(self) -> None:
        self._engine = create_engine(
            self.url,
            echo=False,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        self._session_factory = sessionmaker(
            autocommit=False, autoflush=False, bind=self._engine
        )

    def disconnect(self) -> None:
        if self._engine:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None

    def get_session(self):
        if self._session_factory is None:
            self.connect()
        session = self._session_factory()
        try:
            return session
        except Exception:
            session.close()
            raise

    def init_tables(self) -> int:
        if self._engine is None:
            self.connect()
        inspector = inspect(self._engine)
        existing = set(inspector.get_table_names())
        tables = [
            t for t in ModelsBase.metadata.tables.values() if t.name not in existing
        ]
        if tables:
            ModelsBase.metadata.create_all(bind=self._engine, tables=tables)
            return len(tables)
        return 0

    def check_connection(self) -> bool:
        try:
            if self._engine is None:
                self.connect()
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
