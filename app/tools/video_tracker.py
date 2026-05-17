"""
视频/博客跟踪工具 — 占位符

用途:
    - 跟踪 3Blue1Brown 等数学视频频道更新
    - 跟踪知乎/B站等平台数学文章
    - 后续扩展为 RSS/API 轮询 + 元数据入库

设计预留接口:
"""

from typing import Optional


class VideoTracker:
    """视频/文章跟踪器（占位）"""

    def __init__(self):
        pass

    def check_updates(self) -> list[dict]:
        """检查是否有新内容发布"""
        raise NotImplementedError("待实现")

    def download_metadata(self, url: str) -> Optional[dict]:
        """下载视频/文章元数据"""
        raise NotImplementedError("待实现")
