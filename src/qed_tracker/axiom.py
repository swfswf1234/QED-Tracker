"""通过 Axiom-Flow HTTP API 显式交付 PDF。"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from qed_tracker.inventory import Inventory
from qed_tracker.models import ResourceRecord


class AxiomError(RuntimeError):
    pass


class AxiomClient:
    def __init__(self, base_url: str, *, timeout: float = 120.0, proxy: str = "", tls_verify: bool = True):
        kwargs: dict = {"base_url": base_url.rstrip("/"), "timeout": timeout, "verify": tls_verify}
        if proxy:
            kwargs["proxy"] = proxy
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(**kwargs)

    def close(self) -> None:
        self.client.close()

    def health(self) -> dict:
        response = self.client.get("/api/v1/health")
        self._raise(response, "Axiom-Flow 健康检查失败")
        return response.json()

    def push(
        self,
        resource: ResourceRecord,
        inventory: Inventory,
        *,
        parse: bool = False,
        page_start: int | None = None,
        page_end: int | None = None,
    ) -> dict:
        self.health()
        path = resource.absolute_path(inventory.data_root)
        if not path.exists():
            raise AxiomError(f"资源文件不存在：{path}")
        with path.open("rb") as stream:
            response = self.client.post(
                "/api/v1/documents",
                files={"file": (path.name, stream, "application/pdf")},
            )
        self._raise(response, "Axiom-Flow PDF 上传失败")
        document = response.json()
        result = {
            "schema_version": 1,
            "resource_id": resource.resource_id,
            "axiom_url": self.base_url,
            "document_id": document["id"],
            "pushed_at": datetime.now(UTC).isoformat(),
            "document": document,
        }
        if parse:
            payload = {}
            if page_start is not None:
                payload["page_start"] = page_start
            if page_end is not None:
                payload["page_end"] = page_end
            command = self.client.post(f"/api/v1/documents/{document['id']}/parse-jobs", json=payload)
            try:
                self._raise(command, "Axiom-Flow 解析任务创建失败")
            except AxiomError as exc:
                result["parse_error"] = str(exc)
                inventory.record_axiom_transfer(resource, result)
                raise
            result["parse_command"] = command.json()
        inventory.record_axiom_transfer(resource, result)
        return result

    @staticmethod
    def _raise(response: httpx.Response, prefix: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text[:500]
            raise AxiomError(f"{prefix}（HTTP {response.status_code}）：{detail}") from exc
