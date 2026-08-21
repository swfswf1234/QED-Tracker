"""下载候选、目录目标和本地资源的稳定数据模型。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class ResourceKind(StrEnum):
    BOOK = "book"
    EXERCISE = "exercise"
    PAPER = "paper"


class Availability(StrEnum):
    DOWNLOADABLE = "downloadable"
    METADATA_ONLY = "metadata_only"


class BookRole(StrEnum):
    """书籍角色（多值，方案 A 2026-08-12；QED-034 退休 solutions≈exercises 冗余）。

    取值：textbook（教材）/ exercises（习题集，含题解与答案册）/ reference（参考）。
    kind 保留单值主分类（存储/统计），roles 表达真实使用角色（评审/成套判定）。
    """

    TEXTBOOK = "textbook"
    EXERCISES = "exercises"
    REFERENCE = "reference"


def default_roles(kind: ResourceKind) -> tuple[BookRole, ...]:
    """按 kind 推导默认角色（未显式指定时）：book→[textbook]、exercise→[exercises]、paper→[]。"""
    mapping: dict[ResourceKind, tuple[BookRole, ...]] = {
        ResourceKind.BOOK: (BookRole.TEXTBOOK,),
        ResourceKind.EXERCISE: (BookRole.EXERCISES,),
        ResourceKind.PAPER: (),
    }
    return mapping.get(kind, ())


@dataclass(frozen=True, slots=True)
class DownloadLink:
    """人工下载方案（metadata_only 来源无直链时给用户的指引，如 torrent/IPFS/ed2k）。"""

    label: str
    url: str
    kind: str = "http"  # torrent | ipfs | ed2k | http


@dataclass(frozen=True, slots=True)
class Candidate:
    provider: str
    provider_id: str
    title: str
    authors: tuple[str, ...] = ()
    language: str = ""
    year: str = ""
    edition: str = ""
    format: str = "pdf"
    size_bytes: int | None = None
    page_url: str = ""
    download_url: str = ""
    availability: Availability = Availability.DOWNLOADABLE
    identifiers: dict[str, str] = field(default_factory=dict)
    abstract: str = ""
    subjects: tuple[str, ...] = ()
    published_at: str = ""
    updated_at: str = ""
    file_keywords: tuple[str, ...] = ()
    """下载时优先匹配的文件名关键词（如「习题答案」；无匹配回退最大 PDF，见 providers/books.py resolve）。"""
    links: tuple[DownloadLink, ...] = ()
    """人工下载方案清单（libgen_li 等发现专用来源：torrent/IPFS/ed2k 指引）。"""


@dataclass(frozen=True, slots=True)
class PaperProfile:
    id: str
    name: str
    description: str
    audience: str
    goals: tuple[str, ...]
    topics: tuple[str, ...]
    allowed_categories: tuple[str, ...]
    exclude: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PaperSearch:
    terms: tuple[str, ...]
    category: str
    reason: str


@dataclass(frozen=True, slots=True)
class PaperAssessment:
    arxiv_id: str
    goal_fit: int
    foundational_value: int
    readability: int
    reason: str
    risks: tuple[str, ...] = ()

    @property
    def score(self) -> int:
        return self.goal_fit * 10 + self.foundational_value * 6 + self.readability * 4


@dataclass(frozen=True, slots=True)
class BookAssessment:
    """教材候选评估（QED-013）：LLM 只生成可审阅评分，不写资源事实。"""

    provider_id: str
    score: int  # 0-100
    verdict: str  # recommend | uncertain
    summary: str = ""


@dataclass(frozen=True, slots=True)
class CatalogTarget:
    id: str
    course_id: str
    course_name: str
    kind: ResourceKind
    title: str
    authors: tuple[str, ...] = ()
    language: str = ""
    edition: str = ""
    query: str = ""
    required: bool = True
    file_hint: str = ""
    """下载时优先匹配的文件名关键词（archive 同条目多 PDF 时按此选文件，如「习题答案」）。"""
    note: str = ""
    """人工备注（如「套1」归组线索），不影响匹配。"""
    roles: tuple[BookRole, ...] = ()
    """书籍角色（多值，方案 A）：空时按 kind 推导（default_roles）。一套书可同时是教材与习题集。"""
    set_no: str = ""
    """套标记（QED-024）：1~4=中文套 / en=英文对照套 / 空=无配套。同一课程内 set_no 相同属同一套。"""


@dataclass(frozen=True, slots=True)
class MatchResult:
    score: float
    strict: bool
    reasons: tuple[str, ...]


@dataclass(slots=True)
class ResourceRecord:
    resource_id: str
    kind: str
    title: str
    authors: list[str]
    language: str
    year: str
    identifiers: dict[str, str]
    source: dict[str, Any]
    file: dict[str, Any]
    catalog_ref: dict[str, str] | None = None
    roles: list[str] | None = None
    """书籍角色（方案 A，多值）：从 catalog target 继承；空时按 kind 推导。资源 JSON schema 保持 v1（可选字段向后兼容）。"""
    schema_version: int = 1
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ResourceRecord:
        return cls(**value)

    @property
    def sha256(self) -> str:
        return self.file["sha256"]

    def absolute_path(self, data_root: Path) -> Path:
        return data_root / Path(self.file["relative_path"])
