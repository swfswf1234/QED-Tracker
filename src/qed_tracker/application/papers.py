"""arXiv 检索、智能推荐、选择报告和显式下载用例。"""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import ExitStack
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Protocol

from qed_tracker.application.resources import ResourceService
from qed_tracker.inventory import raw_general_dir
from qed_tracker.models import Candidate, PaperAssessment, PaperProfile, PaperSearch, ResourceKind, ResourceRecord
from qed_tracker.profiles import CATEGORY_PATTERN
from qed_tracker.selection_store import SelectionStore

MAX_SEARCHES = 4
MAX_CANDIDATES = 40
RECOMMENDATION_THRESHOLD = 70


class ArxivSource(Protocol):
    def search(self, query: str = "", *, category: str = "", author: str = "", limit: int = 10) -> list[Candidate]: ...

    def search_terms(self, terms: tuple[str, ...], *, category: str, limit: int = 10) -> list[Candidate]: ...

    def get(self, identifier: str) -> Candidate: ...

    def close(self) -> None: ...


class PaperAdvisor(Protocol):
    def plan(self, profile: PaperProfile, goal: str, allowed_categories: tuple[str, ...]) -> list[PaperSearch]: ...

    def assess(self, profile: PaperProfile, goal: str, candidates: list[Candidate]) -> list[PaperAssessment]: ...

    def metadata(self) -> dict[str, Any]: ...

    def close(self) -> None: ...


class PaperSelectionError(RuntimeError):
    def __init__(self, message: str, selection_id: str):
        super().__init__(message)
        self.selection_id = selection_id


class PaperService:
    def __init__(
        self,
        provider: ArxivSource,
        resources: ResourceService,
        *,
        advisor: PaperAdvisor | None = None,
        selections: SelectionStore | None = None,
        session_factory=None,
    ):
        self.provider = provider
        self.resources = resources
        self.advisor = advisor
        if selections is not None:
            self.selections = selections
        elif session_factory is not None:
            self.selections = SelectionStore(session_factory)
        else:
            # 无 MySQL 时创建 SQLite in-memory fallback（兼容测试场景）
            from sqlalchemy import create_engine as _ce
            from sqlalchemy.orm import sessionmaker as _sm
            from sqlalchemy.pool import StaticPool
            from qed_tracker.db.models import Base as _Base
            _engine = _ce(
                "sqlite://", future=True,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
            _Base.metadata.create_all(_engine)
            _factory = _sm(bind=_engine, expire_on_commit=False)
            self.selections = SelectionStore(lambda: _factory())

    def close(self) -> None:
        # ExitStack still closes the remaining clients if an earlier close fails.
        with ExitStack() as stack:
            if self.advisor:
                stack.callback(self.advisor.close)
            stack.callback(self.resources.close)
            stack.callback(self.provider.close)

    def search(self, query: str = "", *, category: str = "", author: str = "", limit: int = 10) -> list[Candidate]:
        return self.provider.search(query, category=category, author=author, limit=limit)

    def get(self, identifiers: Iterable[str]) -> list[Candidate]:
        return [self.provider.get(identifier) for identifier in identifiers]

    def download(self, candidate: Candidate) -> ResourceRecord:
        # ARCH-019 共享布局：论文落领域通用桶 papers/<year>/（raw/math/_general/papers/）。
        destination = (
            raw_general_dir(self.resources.inventory.data_root) / "papers" / (candidate.year or "unknown")
        )
        return self.resources.download_candidate(candidate, kind=ResourceKind.PAPER, destination_dir=destination)

    def recommend(
        self,
        profile: PaperProfile,
        *,
        goal: str = "",
        categories: Iterable[str] = (),
        limit: int = 10,
        top: int = 10,
    ) -> dict[str, Any]:
        if self.advisor is None:
            raise ValueError("论文推荐需要配置百炼顾问")
        if not 1 <= limit <= 25:
            raise ValueError("每组 arXiv 结果数必须在 1 到 25 之间")
        if not 1 <= top <= 20:
            raise ValueError("推荐数量必须在 1 到 20 之间")
        extras = tuple(dict.fromkeys(item.strip() for item in categories if item.strip()))
        invalid = [item for item in extras if not CATEGORY_PATTERN.fullmatch(item)]
        if invalid:
            raise ValueError(f"非法 arXiv 分类：{', '.join(invalid)}")
        allowed = tuple(dict.fromkeys((*profile.allowed_categories, *extras)))
        selection_id = self.selections.new_id()
        report: dict[str, Any] = {
            "selection_id": selection_id,
            "schema_version": 1,
            "status": "planning",
            "created_at": datetime.now(UTC).isoformat(),
            "profile": asdict(profile),
            "temporary_goal": goal,
            "allowed_categories": list(allowed),
            "search_plan": [],
            "search_failures": [],
            "excluded_existing": [],
            "candidates": [],
            "assessments": [],
            "recommendations": [],
            "model": {},
            "downloads": [],
        }
        try:
            searches = self.advisor.plan(profile, goal, allowed)
            self._validate_searches(searches, allowed)
            report["search_plan"] = [asdict(item) for item in searches]
            candidates = self._search_candidates(searches, limit, report)
            existing_ids = self._existing_arxiv_ids()
            report["excluded_existing"] = sorted(item.identifiers.get("arxiv", "") for item in candidates if item.identifiers.get("arxiv", "") in existing_ids)
            candidates = [item for item in candidates if item.identifiers.get("arxiv", "") not in existing_ids][:MAX_CANDIDATES]
            report["candidates"] = [asdict(item) for item in candidates]
            if not candidates:
                report["status"] = "no_candidates"
                report["model"] = self.advisor.metadata()
                self.selections.save(report)
                return report
            assessments = self.advisor.assess(profile, goal, candidates)
            self._validate_assessments(assessments, candidates)
            by_id = {item.arxiv_id: item for item in assessments}
            ranked = sorted(
                candidates,
                key=lambda item: (
                    -by_id[item.identifiers["arxiv"]].score,
                    -_published_timestamp(item.published_at),
                    item.identifiers["arxiv"],
                ),
            )
            entries = []
            recommended_ranks = []
            for rank, candidate in enumerate(ranked, 1):
                assessment = by_id[candidate.identifiers["arxiv"]]
                recommended = assessment.score >= RECOMMENDATION_THRESHOLD and len(recommended_ranks) < top
                entry = {
                    "rank": rank,
                    "candidate": asdict(candidate),
                    "assessment": asdict(assessment),
                    "score": assessment.score,
                    "recommended": recommended,
                }
                entries.append(entry)
                if recommended:
                    recommended_ranks.append(rank)
            report["assessments"] = entries
            report["recommendations"] = recommended_ranks
            report["model"] = self.advisor.metadata()
            report["status"] = "ranked" if recommended_ranks else "no_recommendations"
            self.selections.save(report)
            return report
        except Exception as exc:
            report["status"] = "failed"
            report["error"] = str(exc)[:500]
            report["model"] = self.advisor.metadata()
            self.selections.save(report)
            raise PaperSelectionError(f"论文推荐失败；报告 {selection_id}：{exc}", selection_id) from exc

    def list_selections(self) -> list[dict[str, Any]]:
        return self.selections.list()

    def get_selection(self, selection_id: str) -> dict[str, Any]:
        return self.selections.load(selection_id)

    def download_selection(self, selection_id: str, picks: Iterable[int]) -> tuple[dict[str, Any], int]:
        report = self.selections.load(selection_id)
        selected = tuple(dict.fromkeys(picks))
        if not selected:
            raise ValueError("至少需要一个 --pick")
        allowed = set(report.get("recommendations", []))
        invalid = [item for item in selected if item not in allowed]
        if invalid:
            raise ValueError(f"只能下载报告中的推荐序号：{', '.join(map(str, invalid))}")
        entries = {int(item["rank"]): item for item in report.get("assessments", [])}
        failures = 0
        for rank in selected:
            entry = entries[rank]
            candidate = _candidate_from_dict(entry["candidate"])
            attempt = {
                "attempted_at": datetime.now(UTC).isoformat(),
                "rank": rank,
                "arxiv_id": candidate.identifiers.get("arxiv", ""),
            }
            try:
                record = self.download(candidate)
                attempt.update({"status": "downloaded", "resource_id": record.resource_id})
            except Exception as exc:
                failures += 1
                attempt.update({"status": "failed", "error": str(exc)[:500]})
            report.setdefault("downloads", []).append(attempt)
        if failures == len(selected):
            report["status"] = "download_failed"
        elif failures:
            report["status"] = "partially_downloaded"
        else:
            report["status"] = "downloaded"
        self.selections.save(report)
        return report, failures

    def _search_candidates(self, searches: list[PaperSearch], limit: int, report: dict[str, Any]) -> list[Candidate]:
        candidates: list[Candidate] = []
        seen: set[str] = set()
        for search in searches:
            try:
                results = self.provider.search_terms(search.terms, category=search.category, limit=limit)
            except Exception as exc:
                report["search_failures"].append({"category": search.category, "terms": list(search.terms), "error": str(exc)[:500]})
                continue
            for candidate in results:
                arxiv_id = candidate.identifiers.get("arxiv", "")
                if not arxiv_id or arxiv_id in seen:
                    continue
                seen.add(arxiv_id)
                candidates.append(candidate)
        if not candidates and report["search_failures"]:
            raise RuntimeError("全部 arXiv 检索均失败")
        return candidates

    def _existing_arxiv_ids(self) -> set[str]:
        return {
            record.identifiers["arxiv"]
            for record in self.resources.inventory.list(ResourceKind.PAPER.value)
            if record.identifiers.get("arxiv")
        }

    @staticmethod
    def _validate_searches(searches: list[PaperSearch], allowed: tuple[str, ...]) -> None:
        if not 1 <= len(searches) <= MAX_SEARCHES:
            raise ValueError("论文检索计划必须包含 1 到 4 项")
        for search in searches:
            if search.category not in allowed or not 1 <= len(search.terms) <= 4:
                raise ValueError("论文检索计划超出允许范围")

    @staticmethod
    def _validate_assessments(assessments: list[PaperAssessment], candidates: list[Candidate]) -> None:
        expected = {item.identifiers["arxiv"] for item in candidates}
        received = [item.arxiv_id for item in assessments]
        if len(received) != len(set(received)) or set(received) != expected:
            raise ValueError("论文评估没有完整覆盖候选")
        for item in assessments:
            if not all(0 <= value <= 5 for value in (item.goal_fit, item.foundational_value, item.readability)):
                raise ValueError("论文评分超出 0 到 5 范围")


def _candidate_from_dict(value: dict[str, Any]) -> Candidate:
    converted = dict(value)
    for name in ("authors", "subjects"):
        converted[name] = tuple(converted.get(name, ()))
    return Candidate(**converted)


def _published_timestamp(value: str) -> float:
    if not value:
        return float("-inf")
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return moment.timestamp()
    except ValueError:
        return float("-inf")
