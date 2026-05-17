from abc import ABC, abstractmethod
from typing import Any


class DatabaseEngine(ABC):
    @abstractmethod
    def connect(self) -> None:
        ...

    @abstractmethod
    def disconnect(self) -> None:
        ...

    @abstractmethod
    def get_session(self) -> Any:
        ...

    @abstractmethod
    def init_tables(self) -> int:
        ...

    @abstractmethod
    def check_connection(self) -> bool:
        ...
