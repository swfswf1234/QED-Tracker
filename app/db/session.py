from app.core.config import settings
from app.db.base import DatabaseEngine


def create_engine_from_config(cfg: dict | None = None) -> DatabaseEngine:
    if cfg is None:
        cfg = {}
    engine_type = cfg.get("engine", "") or settings.db_engine
    if engine_type == "mysql":
        from app.db.mysql import MySQLEngine
        return MySQLEngine(cfg)
    elif engine_type == "postgresql":
        from app.db.postgresql import PostgreSQLEngine
        return PostgreSQLEngine(cfg)
    else:
        raise ValueError(f"Unsupported database engine: {engine_type}")
