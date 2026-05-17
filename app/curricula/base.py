from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class Confidence(str, Enum):
    A = "A"
    B = "B"
    C = "C"


@dataclass
class TextbookTarget:
    title: str = ""
    author: str = ""
    lang: str = "zh"
    confidence: Confidence = Confidence.C
    query: str = ""


@dataclass
class VideoTarget:
    title: str = ""
    platform: str = ""
    url: str = ""
    channel: str = ""


@dataclass
class ArticleTarget:
    title: str = ""
    platform: str = ""
    keywords: list[str] = field(default_factory=list)


@dataclass
class Course:
    id: str
    name: str
    stage: str = ""
    textbooks: list[TextbookTarget] = field(default_factory=list)
    exercises: list[TextbookTarget] = field(default_factory=list)
    videos: list[VideoTarget] = field(default_factory=list)
    articles: list[ArticleTarget] = field(default_factory=list)


@dataclass
class Curriculum:
    name: str
    description: str = ""
    courses: list[Course] = field(default_factory=list)

    def get_course(self, course_id: str) -> Optional[Course]:
        for c in self.courses:
            if c.id == course_id:
                return c
        return None

    def list_course_ids(self) -> list[str]:
        return [c.id for c in self.courses]
