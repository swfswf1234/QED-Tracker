"""外部资源来源适配器。"""

from qed_tracker.providers.arxiv import ArxivProvider
from qed_tracker.providers.books import create_book_providers

__all__ = ["ArxivProvider", "create_book_providers"]
