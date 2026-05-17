from app.core.config import settings
from app.db._base_engine import BaseSQLEngine


class PostgreSQLEngine(BaseSQLEngine):
    DRIVER = "postgresql"

    @property
    def url(self) -> str:
        return (
            f"{self.DRIVER}://{self._cfg.get('user', settings.db_user)}"
            f":{self._cfg.get('password', settings.db_password)}"
            f"@{self._cfg.get('host', settings.db_host)}"
            f":{self._cfg.get('port', settings.db_port)}"
            f"/{self._cfg.get('database', settings.db_name)}"
        )
