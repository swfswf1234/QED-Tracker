"""领域知识 JSON 文件读写工具。

领域导入/探索结果落盘到 QED_DATA_ROOT/raw/{domain_id}/domains.json，
用户查看后确认再覆盖数据库。
课程探索结果落盘到 QED_DATA_ROOT/raw/{domain_id}/{course_id}/tutorials.json。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _domain_file_path(data_root: Path, domain_id: str) -> Path:
    return data_root / "raw" / domain_id / "domains.json"


def _course_file_path(data_root: Path, domain_id: str, course_id: str) -> Path:
    return data_root / "raw" / domain_id / course_id / "tutorials.json"


def write_domain_file(data_root: Path, domain_id: str, data: dict[str, Any]) -> Path:
    """将领域知识 JSON 写入 QED_DATA_ROOT/raw/{domain_id}/domains.json。

    幂等：已有文件直接覆盖。目录不存在时自动创建。
    返回写入的文件路径。
    """
    path = _domain_file_path(data_root, domain_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def read_domain_file(data_root: Path, domain_id: str) -> dict[str, Any]:
    """读取 QED_DATA_ROOT/raw/{domain_id}/domains.json。

    文件不存在时抛出 FileNotFoundError。
    """
    path = _domain_file_path(data_root, domain_id)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def domain_file_exists(data_root: Path, domain_id: str) -> bool:
    return _domain_file_path(data_root, domain_id).exists()


def write_domain_courses_file(data_root: Path, domain_id: str, data: dict[str, Any]) -> Path:
    """将领域课程探索结果 JSON 写入 QED_DATA_ROOT/raw/{domain_id}/courses.json。

    幂等：已有文件直接覆盖。目录不存在时自动创建。
    返回写入的文件路径。
    """
    path = data_root / "raw" / domain_id / "courses.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def read_domain_courses_file(data_root: Path, domain_id: str) -> dict[str, Any]:
    """读取 QED_DATA_ROOT/raw/{domain_id}/courses.json。

    文件不存在时抛出 FileNotFoundError。
    """
    path = data_root / "raw" / domain_id / "courses.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_course_tutorials_file(
    data_root: Path, domain_id: str, course_id: str, data: dict[str, Any]
) -> Path:
    """将课程探索结果 JSON 写入 QED_DATA_ROOT/raw/{domain_id}/{course_id}/tutorials.json。

    幂等：已有文件直接覆盖。目录不存在时自动创建。
    返回写入的文件路径。
    """
    path = _course_file_path(data_root, domain_id, course_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def read_course_tutorials_file(data_root: Path, domain_id: str, course_id: str) -> dict[str, Any]:
    """读取 QED_DATA_ROOT/raw/{domain_id}/{course_id}/tutorials.json。

    文件不存在时抛出 FileNotFoundError。
    """
    path = _course_file_path(data_root, domain_id, course_id)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def course_tutorials_file_exists(data_root: Path, domain_id: str, course_id: str) -> bool:
    return _course_file_path(data_root, domain_id, course_id).exists()


def finalize_domain_file(
    data_root: Path, domain_id: str, selected_courses: list[str] | None = None
) -> Path | None:
    """已完成收口（QED-061）：最终课程反写 `domains.json`，删除中间态 `courses.json`。

    - `selected_courses` 非空时按 course_id 过滤（apply-results 的最终保留集合）；
    - 反写后的 `domains.json` 通过 `validate_domain`（courses 非空），可重新导入；
    - `courses.json` 为中间态，收口后删除；文件缺失时返回 None（不阻塞主流程）。
    """
    try:
        domain_data = read_domain_file(data_root, domain_id)
    except FileNotFoundError:
        return None
    try:
        courses_data = read_domain_courses_file(data_root, domain_id)
    except FileNotFoundError:
        courses_data = {}
    courses = courses_data.get("courses") or domain_data.get("courses") or []
    if selected_courses:
        keep = set(selected_courses)
        courses = [course for course in courses if str(course.get("course_id")) in keep]
    domain_data["courses"] = courses
    if courses_data.get("path"):
        domain_data["path"] = courses_data["path"]
    path = write_domain_file(data_root, domain_id, domain_data)
    (data_root / "raw" / domain_id / "courses.json").unlink(missing_ok=True)
    return path


def finalize_course_tutorials_file(
    data_root: Path,
    domain_id: str,
    course_id: str,
    *,
    course_name: str,
    tutorials: list[dict[str, Any]],
) -> Path:
    """已完成/采纳收口（QED-061）：写课程定稿知识 JSON（含 knowledge_id/book_id）。"""
    data = {
        "domain_id": domain_id,
        "course_id": course_id,
        "course_name": course_name,
        "tutorials": tutorials,
    }
    return write_course_tutorials_file(data_root, domain_id, course_id, data)
