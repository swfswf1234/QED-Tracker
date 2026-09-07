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
