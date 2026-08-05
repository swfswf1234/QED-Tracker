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
