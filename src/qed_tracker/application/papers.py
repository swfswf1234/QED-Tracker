"""arXiv 检索、智能推荐、选择报告和显式下载用例。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import ExitStack
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from qed_tracker.application.resources import ResourceService
from qed_tracker.db.engine import dispose as _dispose_engine
from qed_tracker.db.selection_repository import SelectionStore
from qed_tracker.inventory import raw_general_dir
from qed_tracker.models import Candidate, PaperAssessment, PaperProfile, PaperSearch, ResourceKind, ResourceRecord
from qed_tracker.profiles import CATEGORY_PATTERN
from qed_tracker.providers.bailian import BailianError

MAX_SEARCHES = 4
MAX_CANDIDATES = 40
RECOMMENDATION_THRESHOLD = 70
DEFAULT_YEARS_LIMIT = 3
DAYS_PER_YEAR = 365


class ArxivSource(Protocol):
    def search(self, query: str = "", *, category: str = "", author: str = "", limit: int = 10, sort_by: str = "date") -> list[Candidate]: ...

    def search_terms(
        self, terms: tuple[str, ...], *, category: str, limit: int = 10, sort_by: str = "date", overfetch: bool = False
    ) -> list[Candidate]: ...

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


def _paper_duplicate_entry(arxiv_id: str, title: str, row) -> dict:
    """双报条目：命中行摘要 + 候选 arXiv ID（历史直写留痕无书行时命中字段为空串）。"""
    return {
        "arxiv_id": arxiv_id,
        "book_id": row.book_id if row is not None else "",
        "title": (row.title if row is not None else title) or "",
        "file_path": (row.file_path if row is not None else "") or "",
        "sha256": (row.sha256 if row is not None else "") or "",
    }


class PaperService:
    def __init__(
        self,
        provider: ArxivSource,
        resources: ResourceService,
        *,
        advisor: PaperAdvisor | None = None,
        advisor_factory: Callable[[], PaperAdvisor] | None = None,
        selections: SelectionStore | None = None,
        session_factory=None,
        db_engine=None,
        domain_exists: Callable[[str], bool] | None = None,
        today: datetime | None = None,
    ):
        self.provider = provider
        self.resources = resources
        self.advisor = advisor
        # 服务端按任务现建顾问（预算与审计隔离，与 book_fetch 的 advisor_factory 同法）；
        # 注入实例（CLI/测试）优先于工厂。
        self.advisor_factory = advisor_factory
        self.today = today
        # F9 裁定：论文落盘领域须在 qed_domain 已存在；未登记（无库）时只要求显式非空。
        self.domain_exists = domain_exists
        # 调用方（CLI）建的引擎交回本服务统一释放；None=无数据库（in-memory 回退）。
        self.db_engine = db_engine
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
            # 先注册=最后执行（LIFO）：连接池在报告写完、客户端关闭后才释放。
            stack.callback(_dispose_engine, self.db_engine)
            if self.advisor:
                stack.callback(self.advisor.close)
            stack.callback(self.resources.close)
            stack.callback(self.provider.close)

    def search(self, query: str = "", *, category: str = "", author: str = "", limit: int = 10) -> list[Candidate]:
        return self.provider.search(query, category=category, author=author, limit=limit)

    def get(self, identifiers: Iterable[str]) -> list[Candidate]:
        return [self.provider.get(identifier) for identifier in identifiers]

    def download(self, candidate: Candidate, *, domain_id: str) -> ResourceRecord:
        # ARCH-019 共享布局：论文落领域通用桶 papers/<year>/（raw/<domain>/_general/papers/）。
        # F9 裁定（2026-10-01）：论文没有默认桶，domain_id 必填且须为已存在领域。
        bucket = self._require_domain(domain_id)
        destination = (
            raw_general_dir(self.resources.data_root, domain_id=bucket) / "papers" / (candidate.year or "unknown")
        )
        return self.resources.download_candidate(candidate, kind=ResourceKind.PAPER, destination_dir=destination)

    def _require_domain(self, domain_id: str) -> str:
        bucket = (domain_id or "").strip()
        if not bucket:
            raise ValueError("论文落盘需要显式指定领域（无默认桶）")
        if self.domain_exists is not None and not self.domain_exists(bucket):
            raise ValueError(f"论文落盘领域不存在，需先创建该领域：{bucket}")
        return bucket

    def _open_advisor(self) -> tuple[PaperAdvisor, bool]:
        """返回 (顾问, 是否本次自建)：注入实例优先，其次工厂；都没有即不可推荐。"""
        if self.advisor is not None:
            return self.advisor, False
        if self.advisor_factory is not None:
            return self.advisor_factory(), True
        raise ValueError("论文推荐需要配置百炼顾问")

    def recommend(
        self,
        profile: PaperProfile,
        *,
        goal: str = "",
        categories: Iterable[str] = (),
        limit: int = 10,
        top: int = 10,
        years_limit: int | None = None,
        domain_id: str = "",
        recipe: str = "",
    ) -> dict[str, Any]:
        advisor, owns_advisor = self._open_advisor()
        if not 1 <= limit <= 25:
            raise ValueError("每组 arXiv 结果数必须在 1 到 25 之间")
        if not 1 <= top <= 20:
            raise ValueError("推荐数量必须在 1 到 20 之间")
        years = self._resolve_years_limit(years_limit, profile.years_limit)
        extras = tuple(dict.fromkeys(item.strip() for item in categories if item.strip()))
        invalid = [item for item in extras if not CATEGORY_PATTERN.fullmatch(item)]
        if invalid:
            raise ValueError(f"非法 arXiv 分类：{', '.join(invalid)}")
        allowed = tuple(dict.fromkeys((*profile.allowed_categories, *extras)))
        selection_id = self.selections.new_id()
        report: dict[str, Any] = {
            "selection_id": selection_id,
            "schema_version": 2,
            "status": "planning",
            "created_at": datetime.now(UTC).isoformat(),
            "domain_id": (domain_id or "").strip(),
            "recipe": (recipe or "").strip(),
            "profile": asdict(profile),
            "temporary_goal": goal,
            "years_limit": years,
            "allowed_categories": list(allowed),
            "search_plan": [],
            "plan_coverage": [],
            "plan_source": "",
            "search_failures": [],
            "excluded_existing": [],
            "duplicates": {"same_content": [], "same_name": []},
            "candidates": [],
            "assessments": [],
            "recommendations": [],
            "model": {},
            "downloads": [],
        }
        plan_source, fallback_error = "", ""
        try:
            try:
                searches = advisor.plan(profile, goal, allowed)
                plan_source = "llm"
            except BailianError as exc:
                # QED-068-2：模型计划不可得时走确定性 seed 兜底；无 seed 时原异常上抛。
                seed = self._fallback_seed(goal, profile)
                if seed is None:
                    raise
                searches = self._fallback_searches(seed, allowed)
                plan_source = "fallback"
                fallback_error = str(exc)[:500]
            report["plan_source"] = plan_source
            self._validate_searches(searches, allowed)
            report["search_plan"] = [dict(asdict(item), plan_index=index) for index, item in enumerate(searches, 1)]
            candidates, coverage, plan_index_by_id = self._search_candidates(
                searches, limit, report, self._years_cutoff(years)
            )
            report["plan_coverage"] = coverage
            for entry in report["search_plan"]:
                entry["fetched"] = coverage[entry["plan_index"] - 1]["fetched"]
                entry["kept"] = coverage[entry["plan_index"] - 1]["kept"]
            existing_ids = self._existing_arxiv_ids()
            report["duplicates"] = self._duplicates_report(candidates, existing_ids)
            report["excluded_existing"] = sorted(item.identifiers.get("arxiv", "") for item in candidates if item.identifiers.get("arxiv", "") in existing_ids)
            candidates = [item for item in candidates if item.identifiers.get("arxiv", "") not in existing_ids][:MAX_CANDIDATES]
            report["candidates"] = [
                dict(asdict(item), plan_index=plan_index_by_id.get(item.identifiers.get("arxiv", ""), 0))
                for item in candidates
            ]
            if not candidates:
                report["status"] = "no_candidates"
                self._write_model(report, plan_source, fallback_error, advisor)
                self.selections.save(report)
                return report
            assessments = advisor.assess(profile, goal, candidates)
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
                    "plan_index": plan_index_by_id.get(candidate.identifiers.get("arxiv", ""), 0),
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
            self._write_model(report, plan_source, fallback_error, advisor)
            report["status"] = "ranked" if recommended_ranks else "no_recommendations"
            self.selections.save(report)
            return report
        except Exception as exc:
            report["status"] = "failed"
            report["error"] = str(exc)[:500]
            self._write_model(report, plan_source, fallback_error, advisor)
            self.selections.save(report)
            raise PaperSelectionError(f"论文推荐失败；报告 {selection_id}：{exc}", selection_id) from exc
        finally:
            if owns_advisor:
                advisor.close()

    def list_selections(self, *, domain_id: str = "", recipe: str = "") -> list[dict[str, Any]]:
        return self.selections.list(domain_id=domain_id, recipe=recipe)

    def get_selection(self, selection_id: str) -> dict[str, Any]:
        return self.selections.load(selection_id)

    def _write_model(self, report: dict[str, Any], plan_source: str, fallback_error: str,
                     advisor: PaperAdvisor | None = None) -> None:
        """模型审计 + plan_source 一并写入 model JSON（无表结构改动，读侧据此重建顶层字段）。"""
        advisor = advisor if advisor is not None else self.advisor
        model = advisor.metadata() if advisor else {}
        if plan_source:
            model["plan_source"] = plan_source
        if fallback_error:
            model["plan_fallback_error"] = fallback_error
        report["model"] = model

    @staticmethod
    def _fallback_seed(goal: str, profile: PaperProfile) -> str | None:
        """兜底种子（QED-068-2）：goal 优先，否则 profile.topics 首个非空；单行化、≤120 字符。"""
        for text in (goal, *profile.topics):
            seed = " ".join(text.split())[:120]
            if seed:
                return seed
        return None

    @staticmethod
    def _fallback_searches(seed: str, allowed: tuple[str, ...]) -> list[PaperSearch]:
        """确定性兜底计划：seed / recent advances seed / open challenges seed，分类取 allowed[0]。"""
        category = allowed[0] if allowed else ""
        return [
            PaperSearch((seed,), category, "deterministic fallback"),
            PaperSearch((f"recent advances {seed}",), category, "deterministic fallback"),
            PaperSearch((f"open challenges {seed}",), category, "deterministic fallback"),
        ]

    def _search_candidates(
        self, searches: list[PaperSearch], limit: int, report: dict[str, Any], cutoff: datetime | None
    ) -> tuple[list[Candidate], list[dict[str, Any]], dict[str, int]]:
        candidates: list[Candidate] = []
        seen: set[str] = set()
        coverage: list[dict[str, Any]] = []
        plan_index_by_id: dict[str, int] = {}
        for plan_index, search in enumerate(searches, 1):
            results: list[Candidate] = []
            try:
                results = self.provider.search_terms(
                    search.terms, category=search.category, limit=limit, sort_by="relevance", overfetch=True
                )
            except Exception as exc:
                report["search_failures"].append({"category": search.category, "terms": list(search.terms), "error": str(exc)[:500]})
            kept = 0
            for candidate in results:
                arxiv_id = candidate.identifiers.get("arxiv", "")
                if not arxiv_id or arxiv_id in seen or not self._within_years(candidate, cutoff):
                    continue
                seen.add(arxiv_id)
                candidates.append(candidate)
                plan_index_by_id[arxiv_id] = plan_index
                kept += 1
                if kept >= limit:
                    break
            coverage.append(
                {
                    "plan_index": plan_index,
                    "terms": list(search.terms),
                    "category": search.category,
                    "fetched": len(results),
                    "kept": kept,
                }
            )
        if not candidates and report["search_failures"]:
            raise RuntimeError("全部 arXiv 检索均失败")
        return candidates, coverage, plan_index_by_id

    def _years_cutoff(self, years_limit: int) -> datetime | None:
        if years_limit == 0:
            return None
        now = self.today or datetime.now(UTC)
        return now - timedelta(days=years_limit * DAYS_PER_YEAR)

    @staticmethod
    def _within_years(candidate: Candidate, cutoff: datetime | None) -> bool:
        if cutoff is None:
            return True
        timestamp = _published_timestamp(candidate.published_at)
        # 发布日缺失或不可解析时保留：宁可多给候选，也不因元数据缺失静默吞掉。
        return timestamp == float("-inf") or timestamp >= cutoff.timestamp()

    @staticmethod
    def _resolve_years_limit(explicit: int | None, profile_value: int | None) -> int:
        for label, value in (("显式参数", explicit), ("档案 years_limit", profile_value)):
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"非法 years_limit（{label}）：{value!r}，必须是不小于 0 的整数，0 表示不限年份")
            return value
        return DEFAULT_YEARS_LIMIT

    def _existing_arxiv_ids(self) -> set[str]:
        # QED-071 B-W3（D2/D14）：去重索引由 qt_selections.downloads 派生；
        # 资源岛 kind=paper 读取路径退役（岛内 paper 存量已随 A 轮清理丢失，派生严格优于现状）。
        return self.selections.downloaded_arxiv_ids()

    def _duplicates_report(self, candidates: list[Candidate], existing_ids: set[str]) -> dict:
        """papers 面的查重双报（QED-068 C 步 / 068-4，同口径见 download-pipeline.md）。

        `same_content`＝候选 arXiv ID 命中已下载留痕或已有书行（`excluded_existing` 的逐项
        展开）；`same_name`＝ID 未命中但候选标题 `casefold` 命中书库 owned 且已填内容身份的
        他行。两桶只出清单：候选不剔除、已有行不改动。DB 未配置（`resources.books=None`）时
        两桶恒空。
        """
        buckets: dict[str, list[dict]] = {"same_content": [], "same_name": []}
        books = self.resources.books
        if books is None:
            return buckets
        titles = [item.title for item in candidates if (item.title or "").strip()]
        by_folded: dict[str, list] = {}
        if titles:
            for row in books.find_owned_by_titles(titles):
                for key in {(row.title or "").strip().casefold(),
                            (row.original_title or "").strip().casefold()}:
                    if key:
                        by_folded.setdefault(key, []).append(row)
        for candidate in candidates:
            identifier = (candidate.identifiers or {}).get("arxiv", "")
            if not identifier:
                continue
            if identifier in existing_ids:
                hit = books.find_paper_by_arxiv(identifier)
                buckets["same_content"].append(_paper_duplicate_entry(identifier, candidate.title, hit))
                continue
            for row in by_folded.get((candidate.title or "").strip().casefold(), []):
                buckets["same_name"].append(_paper_duplicate_entry(identifier, candidate.title, row))
        return buckets

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
