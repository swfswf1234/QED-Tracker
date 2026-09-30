"""Bounded, deterministic evidence bundles for local-model synthesis."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True)
class EvidenceSource:
    source_id: str
    family: str
    institution: str | None
    title: str
    canonical_url: str
    retrieved_at: str
    excerpt: str
    locator: str
    claims: tuple[str, ...]
    priority: int


@dataclass(frozen=True)
class PackedEvidence:
    bundle: dict
    estimated_tokens: int


_TEXT_LIMIT_FLOOR = 1
_IDENT_LIMIT = 64
"""标识/枚举字段硬上限（source_id、family、institution、retrieved_at、phase、coverage 家族名）。
压缩纪律按计划只收缩摘录类自由文本：把 `Stanford` 截成 `Stanfor` 会破坏引用与枚举语义。"""


def _estimate_tokens(value: object) -> int:
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return ceil(len(serialized) / 4)


def _truncate(text: str, character_limit: int) -> tuple[str, bool]:
    if len(text) <= character_limit:
        return text, False
    shortened = text[:character_limit].rsplit("。", 1)[0].strip()
    return (shortened or text[:character_limit]).strip(), True


class EvidencePacker:
    """Pack source evidence without allowing any caller-controlled field to exceed the context budget."""

    def __init__(self, *, max_tokens: int = 4300) -> None:
        if max_tokens < 1:
            raise ValueError("max_tokens 必须大于零")
        self.max_tokens = max_tokens

    def pack(
        self,
        *,
        domain_name: str,
        scope_hint: str,
        language: str,
        phase: str,
        sources: Iterable[EvidenceSource],
        requested_families: tuple[str, ...],
    ) -> PackedEvidence:
        ordered = sorted(sources, key=lambda source: (source.priority, source.source_id))
        requested = list(requested_families[: max(1, self.max_tokens // 32)])
        source_slots = min(len(ordered), max(1, min(4, self.max_tokens // 64)))
        selected = ordered[:source_slots]
        omitted = {source.institution or source.family: "omitted_for_budget" for source in ordered[source_slots:]}

        while True:
            bundle = self._build_bundle(
                domain_name=domain_name,
                scope_hint=scope_hint,
                language=language,
                phase=phase,
                selected=selected,
                requested=requested,
                omitted=omitted,
            )
            estimated_tokens = _estimate_tokens(bundle)
            if estimated_tokens <= self.max_tokens or not selected:
                return PackedEvidence(bundle=bundle, estimated_tokens=estimated_tokens)
            removed = selected.pop()
            omitted[removed.institution or removed.family] = "omitted_for_budget"

    def _build_bundle(
        self,
        *,
        domain_name: str,
        scope_hint: str,
        language: str,
        phase: str,
        selected: list[EvidenceSource],
        requested: list[str],
        omitted: dict[str, str],
    ) -> dict:
        field_count = 16 + len(selected) * 14 + len(requested) * 4
        character_limit = max(_TEXT_LIMIT_FLOOR, (self.max_tokens * 2) // field_count)

        def clip(value: str) -> tuple[str, bool]:
            return _truncate(value, character_limit)

        def ident(value: str) -> tuple[str, bool]:
            return _truncate(value, _IDENT_LIMIT)

        packed_sources: list[dict] = []
        collected: set[str] = set()
        for source in selected:
            source_id, id_truncated = ident(source.source_id)
            family, family_truncated = ident(source.family)
            institution, institution_truncated = ident(source.institution or "")
            title, title_truncated = clip(source.title)
            canonical_url, url_truncated = clip(source.canonical_url)
            retrieved_at, time_truncated = ident(source.retrieved_at)
            excerpt, excerpt_truncated = clip(source.excerpt)
            locator, locator_truncated = clip(source.locator)
            claims = [clip(claim)[0] for claim in source.claims[:2]]
            packed_sources.append(
                {
                    "source_id": source_id,
                    "family": family,
                    "institution": institution or None,
                    "title": title,
                    "canonical_url": canonical_url,
                    "retrieved_at": retrieved_at,
                    "excerpt": excerpt,
                    "locator": locator,
                    "claims": claims,
                    "truncated": any(
                        (
                            id_truncated,
                            family_truncated,
                            institution_truncated,
                            title_truncated,
                            url_truncated,
                            time_truncated,
                            excerpt_truncated,
                            locator_truncated,
                        )
                    ),
                }
            )
            collected.update({source.family, source.institution or source.family})

        safe_domain_name, _ = clip(domain_name)
        safe_scope_hint, _ = clip(scope_hint)
        safe_language, _ = ident(language)
        safe_phase, _ = ident(phase)
        missing = [
            {"family": ident(name)[0], "reason": omitted.get(name, "not_collected")}
            for name in requested
            if name not in collected
        ]
        return {
            "schema_version": "evidence-bundle-v1",
            "phase": safe_phase,
            "query": {
                "domain_name": safe_domain_name,
                "canonical_name": safe_domain_name,
                "scope_hint": safe_scope_hint,
                "language": safe_language,
            },
            "sources": packed_sources,
            "coverage": {
                "requested_families": [ident(name)[0] for name in requested],
                "collected_families": [ident(name)[0] for name in requested if name in collected],
                "missing": missing,
            },
        }
