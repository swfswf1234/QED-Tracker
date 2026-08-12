"""资源登记双写服务：JSON 事实源（Inventory）之后同步 qt_resources 查询索引。

登记顺序（契约）：PDF 落盘 → 写 `meta/resources/<sha256>.json`（Inventory）→ 写 MySQL；
任一步失败任务失败并保留可重放现场（同 sha256 幂等复用既有记录）。
`repository` 为 None（无 QED_DB_PASSWORD）时 DB 侧降级 no-op，不阻塞下载主链路。
"""

from __future__ import annotations

from typing import Any

from qed_tracker.db.repository import ResourceRepository


class ResourceRegistry:
    def __init__(self, repository: ResourceRepository | None):
        self.repository = repository

    def register_downloaded(self, record: Any) -> None:
        """下载登记双写：调用方须先完成文件落盘与 JSON 登记（Inventory）。"""
        if self.repository is None:
            return
        value = record.to_dict() if hasattr(record, "to_dict") else record
        self.repository.upsert_downloaded(
            resource_id=value["resource_id"],
            sha256=value["file"]["sha256"],
            relative_path=value["file"]["relative_path"],
            page_count=value["file"].get("page_count", 0),
            kind=value["kind"],
            title=value["title"],
            authors=value.get("authors", []),
            language=value.get("language", ""),
            year=value.get("year", ""),
            edition=value.get("edition", ""),
            source=value.get("source", {}),
            catalog_ref=value.get("catalog_ref"),
        )

    def reject(self, resource_id: str, *, reason: str, by: str) -> None:
        """拒绝留痕（候选级或下载后验收级；DB 记录保留永不删除）。"""
        if self.repository is None:
            return
        self.repository.reject(resource_id, reason=reason, by=by)
