"""目录目标与来源候选的保守匹配规则。"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from qed_tracker.models import Candidate, CatalogTarget, MatchResult


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(part for part in re.split(r"[^\w\u4e00-\u9fff]+", value) if part)


def _tokens(value: str) -> set[str]:
    normalized = _normalize(value)
    parts = {part for part in normalized.split() if len(part) > 1}
    if not parts and any("\u4e00" <= char <= "\u9fff" for char in normalized):
        parts = {char for char in normalized if "\u4e00" <= char <= "\u9fff"}
    return parts


def _similarity(actual: str, expected: str) -> float:
    actual_n, expected_n = _normalize(actual), _normalize(expected)
    if not actual_n or not expected_n:
        return 0.0
    if actual_n in expected_n or expected_n in actual_n:
        return 1.0
    expected_tokens = _tokens(expected)
    coverage = len(expected_tokens & _tokens(actual)) / len(expected_tokens) if expected_tokens else 0.0
    return max(coverage, SequenceMatcher(None, actual_n, expected_n).ratio())


def _language(value: str) -> str:
    normalized = _normalize(value)
    if normalized in {"zh", "cn", "chi", "chinese", "中文"}:
        return "zh"
    if normalized in {"en", "eng", "english"}:
        return "en"
    return normalized


def match_candidate(candidate: Candidate, target: CatalogTarget) -> MatchResult:
    reasons: list[str] = []
    title_score = _similarity(candidate.title, target.title)
    if title_score < 0.82:
        reasons.append("题名不匹配")

    author_score = 1.0
    if target.authors:
        actual_authors = " ".join(candidate.authors)
        author_score = max((_similarity(actual_authors, author) for author in target.authors), default=0.0)
        if not actual_authors or author_score < 0.72:
            reasons.append("作者不匹配或缺失")

    language_score = 1.0
    if target.language:
        language_score = 1.0 if _language(candidate.language) == _language(target.language) else 0.0
        if language_score == 0:
            reasons.append("语言不匹配或缺失")

    edition_score = 1.0
    if target.edition:
        haystack = f"{candidate.title} {candidate.edition} {candidate.year}"
        edition_score = _similarity(haystack, target.edition)
        if edition_score < 0.7:
            reasons.append("版次不匹配或缺失")

    score = 0.55 * title_score + 0.25 * author_score + 0.1 * language_score + 0.1 * edition_score
    return MatchResult(round(score, 4), not reasons and candidate.availability == "downloadable", tuple(reasons))
