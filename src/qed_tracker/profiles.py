"""论文目标档案加载与校验。"""

from __future__ import annotations

import json
import re
from dataclasses import fields
from importlib.resources import files
from pathlib import Path

from qed_tracker.models import PaperProfile

PROFILE_FIELDS = {item.name for item in fields(PaperProfile)}
CATEGORY_PATTERN = re.compile(r"^[a-z][a-z.-]*\.[A-Za-z-]+$")


def list_paper_profiles() -> tuple[str, ...]:
    root = files("qed_tracker.paper_profiles")
    return tuple(sorted(item.name.removesuffix(".json") for item in root.iterdir() if item.name.endswith(".json")))


def load_paper_profile(value: str | Path) -> PaperProfile:
    path = Path(value)
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
    else:
        name = str(value).removesuffix(".json")
        resource = files("qed_tracker.paper_profiles").joinpath(f"{name}.json")
        if not resource.is_file():
            raise ValueError(f"未知论文目标档案：{value}")
        raw = json.loads(resource.read_text(encoding="utf-8"))
    return _validate_profile(raw)


def _validate_profile(raw: object) -> PaperProfile:
    if not isinstance(raw, dict):
        raise ValueError("论文目标档案必须是 JSON 对象")
    unknown = set(raw) - PROFILE_FIELDS
    if unknown:
        raise ValueError(f"论文目标档案包含未知字段：{', '.join(sorted(unknown))}")
    required = PROFILE_FIELDS - {"exclude"}
    missing = [name for name in sorted(required) if not raw.get(name)]
    if missing:
        raise ValueError(f"论文目标档案缺少字段：{', '.join(missing)}")
    for name in ("goals", "topics", "allowed_categories", "exclude"):
        value = raw.get(name, [])
        if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
            raise ValueError(f"论文目标档案字段 {name} 必须是非空字符串数组")
    categories = tuple(dict.fromkeys(raw["allowed_categories"]))
    invalid = [item for item in categories if not CATEGORY_PATTERN.fullmatch(item)]
    if invalid:
        raise ValueError(f"非法 arXiv 分类：{', '.join(invalid)}")
    return PaperProfile(
        id=str(raw["id"]),
        name=str(raw["name"]),
        description=str(raw["description"]),
        audience=str(raw["audience"]),
        goals=tuple(raw["goals"]),
        topics=tuple(raw["topics"]),
        allowed_categories=categories,
        exclude=tuple(raw.get("exclude", [])),
    )
