"""Base collector: provides source identifier, does not enforce unified method signature

Each collector uses different entry methods due to business differences (textbooks/papers/docs),
but all identify data source type through the source attribute.
"""


class BaseCollector:
    """Base collector class"""
    source: str = "base"
