"""加载学科课程体系（包内静态 JSON，与 catalogs/ 同模式）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files


@dataclass(frozen=True, slots=True)
class Course:
    course_id: str
    name: str
    aliases: tuple[str, ...]
    stage: str
    prerequisites: tuple[str, ...]
    related_targets: tuple[str, ...]
    note: str


@dataclass(frozen=True, slots=True)
class Curriculum:
    subject: str
    name: str
    description: str
    stages: tuple[str, ...]
    courses: tuple[Course, ...]


def list_courses() -> tuple[str, ...]:
    return tuple(
        sorted(path.name.removesuffix(".json") for path in files("qed_tracker").joinpath("courses").iterdir() if path.name.endswith(".json"))
    )


def load_course(subject: str) -> Curriculum:
    resource = files("qed_tracker").joinpath("courses", f"{subject}.json")
    if not resource.is_file():
        raise ValueError(f"未知学科课程体系：{subject}")
    value = json.loads(resource.read_text(encoding="utf-8"))
    courses = tuple(
        Course(
            course_id=item["course_id"],
            name=item["name"],
            aliases=tuple(item.get("aliases", [])),
            stage=item["stage"],
            prerequisites=tuple(item.get("prerequisites", [])),
            related_targets=tuple(item.get("related_targets", [])),
            note=item.get("note", ""),
        )
        for item in value["courses"]
    )
    return Curriculum(
        subject=value["subject"],
        name=value["name"],
        description=value.get("description", ""),
        stages=tuple(value["stages"]),
        courses=courses,
    )
