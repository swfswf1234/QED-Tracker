"""加载学科课程体系（共享表 qed_domain / qed_course；courses/*.json 已退役，QED-031）。

读取依赖 KnowledgeRepository（DB 配置后由 CLI 注入）；无 DB 时 raise ValueError。
dataclass（Course/Curriculum）保留，供 CLI/测试消费。
"""

from __future__ import annotations

from dataclasses import dataclass

from qed_tracker.db.knowledge_repository import KnowledgeRepository

_repository: KnowledgeRepository | None = None


def set_repository(repo: KnowledgeRepository | None) -> None:
    """注入仓库（CLI 启动时设置；测试用 SQLite mock）。"""
    global _repository
    _repository = repo


def _repo() -> KnowledgeRepository:
    if _repository is None:
        raise ValueError("数据库未配置：课程体系读取需 qed_course 表（运行 `qed-tracker migrate` 种子或设置数据库）")
    return _repository


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
    return tuple(domain.domain_id for domain in _repo().list_domains())


def _course_to_dataclass(row) -> Course:
    return Course(
        course_id=row.course_id,
        name=row.name,
        aliases=tuple(row.aliases or []),
        stage=row.stage,
        prerequisites=tuple(row.prerequisites or []),
        related_targets=tuple(row.related_targets or []),
        note=row.description,
    )


def load_course(subject: str) -> Curriculum:
    repo = _repo()
    domain = next((d for d in repo.list_domains() if d.domain_id == subject), None)
    if domain is None:
        raise ValueError(f"未知学科课程体系：{subject}")
    courses = tuple(_course_to_dataclass(row) for row in repo.list_courses(subject))
    return Curriculum(
        subject=domain.domain_id,
        name=domain.name,
        description=domain.description,
        stages=tuple(domain.stages or []),
        courses=courses,
    )
