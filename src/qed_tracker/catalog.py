"""加载冻结的内置下载目录。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files

from qed_tracker.models import BookRole, CatalogTarget, ResourceKind, default_roles


@dataclass(frozen=True, slots=True)
class Catalog:
    id: str
    name: str
    description: str
    status: str
    targets: tuple[CatalogTarget, ...]


def list_catalogs() -> tuple[str, ...]:
    return tuple(sorted(path.name.removesuffix(".json") for path in files("qed_tracker.catalogs").iterdir() if path.name.endswith(".json")))


def load_catalog(catalog_id: str) -> Catalog:
    resource = files("qed_tracker.catalogs").joinpath(f"{catalog_id}.json")
    if not resource.is_file():
        raise ValueError(f"未知目录：{catalog_id}")
    value = json.loads(resource.read_text(encoding="utf-8"))
    targets = tuple(CatalogTarget(
        id=item["id"], course_id=item["course_id"], course_name=item["course_name"],
        kind=ResourceKind(item["kind"]), title=item["title"], authors=tuple(item.get("authors", [])),
        language=item.get("language", ""), edition=item.get("edition", ""), query=item.get("query", ""),
        required=item.get("required", True), file_hint=item.get("file_hint", ""),
        roles=tuple(BookRole(role) for role in item.get("roles", [])) or default_roles(ResourceKind(item["kind"])),
    ) for item in value["targets"])
    return Catalog(value["id"], value["name"], value.get("description", ""), value["status"], targets)
