from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

import httpx
import pytest

from qed_tracker.application.papers import PaperSelectionError, PaperService
from qed_tracker.application.resources import ResourceService
from qed_tracker.db.selection_repository import SelectionStoreError
from qed_tracker.downloader import DownloadManager
from qed_tracker.models import Candidate, PaperAssessment, PaperProfile, PaperSearch
from qed_tracker.providers.bailian import BailianError


class FakeArxiv:
    def __init__(self, candidates):
        self.candidates = candidates
        self.searches = []

    def search_terms(self, terms, *, category, limit=10, sort_by="date", overfetch=False):
        self.searches.append({"terms": terms, "category": category, "limit": limit, "sort_by": sort_by, "overfetch": overfetch})
        return list(self.candidates)

    def search(self, query="", *, category="", author="", limit=10, sort_by="date"):
        return list(self.candidates)

    def get(self, identifier):
        return next(item for item in self.candidates if item.provider_id == identifier)

    def close(self):
        return None


class GroupedArxiv(FakeArxiv):
    def __init__(self, by_terms):
        super().__init__([])
        self.by_terms = by_terms

    def search_terms(self, terms, *, category, limit=10, sort_by="date", overfetch=False):
        self.searches.append({"terms": terms, "category": category, "limit": limit, "sort_by": sort_by, "overfetch": overfetch})
        return list(self.by_terms.get(tuple(terms), []))


class FakeAdvisor:
    def __init__(self, scores):
        self.scores = scores
        self.assessed = []

    def plan(self, profile, goal, allowed_categories):
        return [PaperSearch(("retrieval augmented generation",), allowed_categories[0], "覆盖目标")]

    def assess(self, profile, goal, candidates):
        self.assessed = list(candidates)
        return [PaperAssessment(item.provider_id, *self.scores[item.provider_id], f"评估 {item.provider_id}") for item in candidates]

    def metadata(self):
        return {"model": "fake", "contract_version": "paper-selection-v1", "calls": 2, "usage": [], "response_sha256": []}

    def close(self):
        return None


class TwoGroupAdvisor(FakeAdvisor):
    def plan(self, profile, goal, allowed_categories):
        return [
            PaperSearch(("group one",), allowed_categories[0], "第一组"),
            PaperSearch(("group two",), allowed_categories[0], "第二组"),
        ]


def _candidate(identifier: str, score_date: str, title: str) -> Candidate:
    return Candidate(
        "arxiv", identifier, title, ("Ada",), "en", "2026",
        page_url=f"https://arxiv.org/abs/{identifier}",
        download_url=f"https://arxiv.org/pdf/{identifier}",
        identifiers={"arxiv": identifier}, abstract=f"Abstract for {title}",
        subjects=("cs.CL",), published_at=score_date, updated_at=score_date,
    )


def _profile(years_limit: int | None = None) -> PaperProfile:
    return PaperProfile(
        "test", "Test", "Test profile", "Developers", ("RAG",), ("retrieval",), ("cs.CL",), (),
        years_limit=years_limit,
    )


def test_recommendation_is_audited_and_legacy_downloads_stay_derivable(tmp_path, pdf_bytes):
    first = _candidate("2601.00001", "2026-01-03T00:00:00+00:00", "Strong RAG")
    second = _candidate("2601.00002", "2026-01-02T00:00:00+00:00", "Weak RAG")
    existing = _candidate("2601.00003", "2026-01-01T00:00:00+00:00", "Existing")
    manager = DownloadManager(retries=1)
    manager.client.close()
    manager.client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=pdf_bytes)))
    advisor = FakeAdvisor({first.provider_id: (5, 5, 5), second.provider_id: (2, 2, 2)})
    provider = FakeArxiv([first, second, existing, first])
    service = PaperService(provider, ResourceService(tmp_path, manager), advisor=advisor)
    # QED-071 B-W3：论文去重改由 qt_selections.downloads 派生（岛 kind=paper 读取路径退役）
    service.selections.save({
        "selection_id": type(service.selections).new_id(),
        "status": "downloaded",
        "downloads": [{"arxiv_id": "2601.00003", "status": "downloaded", "rank": 1, "resource_id": "sha256:abc"}],
    })

    report = service.recommend(_profile(), goal="reliable RAG", top=5)

    assert report["status"] == "ranked"
    assert report["recommendations"] == [1]
    assert report["excluded_existing"] == [existing.provider_id]
    assert [item.provider_id for item in advisor.assessed] == [first.provider_id, second.provider_id]
    assert not (tmp_path / "papers").exists()
    assert service.get_selection(report["selection_id"])["model"]["model"] == "fake"

    assert not (tmp_path / "raw").exists(), "推荐阶段不得落盘"
    # QED-068 B 步：报告直写下载面退役，历史 downloads 派生口径保留（adopt 任务面查重用）
    assert service.selections.downloaded_arxiv_ids() >= {"2601.00003"}
    service.close()


def test_download_honors_domain_bucket(tmp_path, pdf_bytes):
    """F5：论文落盘桶随 domain_id 变化（旧实现恒落 raw/math/_general/papers/）。"""
    manager = DownloadManager(retries=1)
    manager.client.close()
    manager.client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=pdf_bytes)))
    default_domain = _candidate("2601.00009", "2026-01-05T00:00:00+00:00", "Default Domain")
    other_domain = _candidate("2601.00010", "2026-01-06T00:00:00+00:00", "Other Domain")
    service = PaperService(FakeArxiv([default_domain, other_domain]), ResourceService(tmp_path, manager))

    service.download(default_domain, domain_id="math")
    service.download(other_domain, domain_id="cs")

    assert list((tmp_path / "raw" / "math" / "_general" / "papers" / "2026").glob("*.pdf"))
    assert list((tmp_path / "raw" / "cs" / "_general" / "papers" / "2026").glob("*.pdf"))
    service.close()


def test_download_has_no_default_bucket(tmp_path, pdf_bytes):
    """F9 裁定（2026-10-01）：论文**没有默认桶**——domain_id 必填且须为已存在领域。"""
    manager = DownloadManager(retries=1)
    manager.client.close()
    manager.client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=pdf_bytes)))
    candidate = _candidate("2601.00012", "2026-01-08T00:00:00+00:00", "No Default Bucket")
    resources = ResourceService(tmp_path, manager)
    known = PaperService(FakeArxiv([candidate]), resources, domain_exists=lambda d: d == "math-advanced")

    for blank in ("", "   "):
        with pytest.raises(ValueError, match="领域"):
            known.download(candidate, domain_id=blank)
    with pytest.raises(ValueError, match="cs"):
        known.download(candidate, domain_id="cs")
    assert not (tmp_path / "raw").exists(), "校验不过不得落盘"

    known.download(candidate, domain_id="math-advanced")
    assert list((tmp_path / "raw" / "math-advanced" / "_general" / "papers" / "2026").glob("*.pdf"))
    # 无领域登记表（未配库）时仍要求显式非空 domain_id，但不做存在性校验
    plain = PaperService(FakeArxiv([candidate]), resources)
    with pytest.raises(ValueError, match="领域"):
        plain.download(candidate, domain_id="")
    plain.close()
    known.close()


def test_recommendation_without_eligible_candidate_returns_report(tmp_path):
    candidate = _candidate("2601.00004", "2026-01-01T00:00:00+00:00", "Unrelated")
    manager = DownloadManager(retries=1)
    service = PaperService(
        FakeArxiv([candidate]),
        ResourceService(tmp_path, manager),
        advisor=FakeAdvisor({candidate.provider_id: (1, 1, 1)}),
    )
    report = service.recommend(_profile())
    assert report["status"] == "no_recommendations"
    assert report["recommendations"] == []
    # REQ-032：验证选择报告已持久化到数据库
    loaded = service.selections.load(report["selection_id"])
    assert loaded["selection_id"] == report["selection_id"]
    service.close()


def test_ranking_uses_score_then_known_date_then_arxiv_id(tmp_path):
    older = _candidate("2601.00003", "2026-01-01T00:00:00+00:00", "Older")
    newer = _candidate("2601.00002", "2026-01-02T00:00:00+00:00", "Newer")
    undated = _candidate("2601.00001", "", "Undated")
    manager = DownloadManager(retries=1)
    scores = {item.provider_id: (5, 4, 3) for item in (older, newer, undated)}
    service = PaperService(
        FakeArxiv([older, undated, newer]),
        ResourceService(tmp_path, manager),
        advisor=FakeAdvisor(scores),
    )

    report = service.recommend(_profile())

    ranked_ids = [item["candidate"]["provider_id"] for item in report["assessments"]]
    assert ranked_ids == [newer.provider_id, older.provider_id, undated.provider_id]
    service.close()


def test_failed_recommendation_is_saved_for_audit(tmp_path):
    class FailingAdvisor(FakeAdvisor):
        def plan(self, profile, goal, allowed_categories):
            raise RuntimeError("advisor unavailable")

    manager = DownloadManager(retries=1)
    service = PaperService(
        FakeArxiv([]),
        ResourceService(tmp_path, manager),
        advisor=FailingAdvisor({}),
    )

    with pytest.raises(RuntimeError, match="报告") as captured:
        service.recommend(_profile())

    report = service.get_selection(captured.value.selection_id)
    assert report["status"] == "failed"
    assert report["error"] == "advisor unavailable"
    service.close()


# ---------- QED-068-1（S1b）检索参数接线与年份窗口 ----------

_TODAY = datetime(2026, 6, 1, tzinfo=UTC)


def _service(tmp_path, provider, advisor, *, today=_TODAY):
    return PaperService(
        provider,
        ResourceService(tmp_path, DownloadManager(retries=1)),
        advisor=advisor,
        today=today,
    )


def test_recommend_requests_relevance_and_overfetch(tmp_path):
    candidate = _candidate("2601.00001", "2026-01-03T00:00:00+00:00", "Strong RAG")
    provider = FakeArxiv([candidate])
    service = _service(tmp_path, provider, FakeAdvisor({candidate.provider_id: (5, 5, 5)}))

    service.recommend(_profile(), limit=7, top=5)

    assert provider.searches[0]["sort_by"] == "relevance"
    assert provider.searches[0]["overfetch"] is True
    assert provider.searches[0]["limit"] == 7
    service.close()


def test_overfetch_truncates_per_group(tmp_path):
    group_one = [_candidate(f"2601.0001{i}", "2026-01-03T00:00:00+00:00", f"One {i}") for i in range(6)]
    group_two = [_candidate(f"2601.0002{i}", "2026-01-03T00:00:00+00:00", f"Two {i}") for i in range(6)]
    provider = GroupedArxiv({("group one",): group_one, ("group two",): group_two})
    scores = {item.provider_id: (5, 5, 5) for item in group_one + group_two}
    service = _service(tmp_path, provider, TwoGroupAdvisor(scores))

    report = service.recommend(_profile(), limit=4, top=4)

    kept = [item["candidate"]["provider_id"] for item in report["assessments"]]
    assert len(kept) == 8
    assert set(kept) == {item.provider_id for item in group_one[:4] + group_two[:4]}
    service.close()


def test_years_limit_default_three_filters_old_papers(tmp_path):
    recent = _candidate("2601.00001", "2024-01-01T00:00:00+00:00", "Recent")
    old = _candidate("2001.00001", "2020-01-01T00:00:00+00:00", "Old")
    provider = FakeArxiv([recent, old])
    scores = {item.provider_id: (5, 5, 5) for item in (recent, old)}
    service = _service(tmp_path, provider, FakeAdvisor(scores))

    report = service.recommend(_profile(), top=5)

    assert report["years_limit"] == 3
    assert [item["provider_id"] for item in report["candidates"]] == [recent.provider_id]
    service.close()


def test_years_limit_zero_means_unlimited(tmp_path):
    recent = _candidate("2601.00001", "2024-01-01T00:00:00+00:00", "Recent")
    old = _candidate("2001.00001", "2020-01-01T00:00:00+00:00", "Old")
    provider = FakeArxiv([recent, old])
    scores = {item.provider_id: (5, 5, 5) for item in (recent, old)}
    service = _service(tmp_path, provider, FakeAdvisor(scores))

    report = service.recommend(_profile(), years_limit=0, top=5)

    assert report["years_limit"] == 0
    assert len(report["candidates"]) == 2
    service.close()


def test_years_limit_profile_applies_without_explicit(tmp_path):
    profile = _profile(years_limit=1)
    recent = _candidate("2601.00001", "2026-01-01T00:00:00+00:00", "Within one year")
    older = _candidate("2401.00001", "2024-01-01T00:00:00+00:00", "Outside one year")
    provider = FakeArxiv([recent, older])
    scores = {item.provider_id: (5, 5, 5) for item in (recent, older)}
    service = _service(tmp_path, provider, FakeAdvisor(scores))

    report = service.recommend(profile, top=5)

    assert report["years_limit"] == 1
    assert [item["provider_id"] for item in report["candidates"]] == [recent.provider_id]
    service.close()


def test_explicit_years_limit_overrides_profile(tmp_path):
    profile = _profile(years_limit=1)
    recent = _candidate("2601.00001", "2026-01-01T00:00:00+00:00", "Within one year")
    older = _candidate("2401.00001", "2024-01-01T00:00:00+00:00", "Outside one year")
    provider = FakeArxiv([recent, older])
    scores = {item.provider_id: (5, 5, 5) for item in (recent, older)}
    service = _service(tmp_path, provider, FakeAdvisor(scores))

    report = service.recommend(profile, years_limit=5, top=5)

    assert report["years_limit"] == 5
    assert len(report["candidates"]) == 2
    service.close()


@pytest.mark.parametrize("value", [-1, "3", 1.5, True])
def test_invalid_years_limit_is_rejected(tmp_path, value):
    candidate = _candidate("2601.00001", "2026-01-01T00:00:00+00:00", "Any")
    service = _service(tmp_path, FakeArxiv([candidate]), FakeAdvisor({candidate.provider_id: (5, 5, 5)}))

    with pytest.raises(ValueError, match="years_limit"):
        service.recommend(_profile(), years_limit=value)
    service.close()


def test_undated_candidate_survives_years_window(tmp_path):
    undated = _candidate("2601.00001", "", "Undated")
    service = _service(tmp_path, FakeArxiv([undated]), FakeAdvisor({undated.provider_id: (5, 5, 5)}))

    report = service.recommend(_profile(), top=5)

    assert [item["provider_id"] for item in report["candidates"]] == [undated.provider_id]
    service.close()


# ---------- QED-068-3（S2）报告 schema v2：溯源与覆盖核对 ----------


def _two_group_provider_for_coverage():
    group_one = [
        _candidate("2601.00011", "2026-01-03T00:00:00+00:00", "One A"),
        _candidate("2601.00012", "2026-01-03T00:00:00+00:00", "One B"),
    ]
    stale = _candidate("2001.00099", "2020-01-01T00:00:00+00:00", "Stale")
    # 第二组：一条被年份窗口过滤、一条与第一组重复 → kept=0 显式信号
    group_two = [stale, group_one[0]]
    return group_one, group_two, GroupedArxiv({("group one",): group_one, ("group two",): group_two})


def test_plan_coverage_counts_fetched_and_kept(tmp_path):
    group_one, _group_two, provider = _two_group_provider_for_coverage()
    scores = {item.provider_id: (5, 5, 5) for item in group_one}
    service = _service(tmp_path, provider, TwoGroupAdvisor(scores))

    report = service.recommend(_profile(), limit=4, top=4)

    assert report["schema_version"] == 2
    assert report["plan_coverage"] == [
        {"plan_index": 1, "terms": ["group one"], "category": "cs.CL", "fetched": 2, "kept": 2},
        {"plan_index": 2, "terms": ["group two"], "category": "cs.CL", "fetched": 2, "kept": 0},
    ]
    search_plan = report["search_plan"]
    assert [entry["fetched"] for entry in search_plan] == [2, 2]
    assert [entry["kept"] for entry in search_plan] == [2, 0]
    assert [entry["plan_index"] for entry in search_plan] == [1, 2]
    service.close()


def test_plan_coverage_persists_and_rebuilds_on_load(tmp_path):
    group_one, _group_two, provider = _two_group_provider_for_coverage()
    scores = {item.provider_id: (5, 5, 5) for item in group_one}
    service = _service(tmp_path, provider, TwoGroupAdvisor(scores))

    report = service.recommend(_profile(), limit=4, top=4)
    loaded = service.get_selection(report["selection_id"])

    assert loaded["schema_version"] == 2
    assert loaded["plan_coverage"] == report["plan_coverage"]
    service.close()


def test_candidate_entry_has_plan_index(tmp_path):
    group_one, group_two, provider = _two_group_provider_for_coverage()
    stale = group_two[0]
    scores = {item.provider_id: (5, 5, 5) for item in group_one}
    service = _service(tmp_path, provider, TwoGroupAdvisor(scores))

    report = service.recommend(_profile(), limit=4, top=4)

    assert [entry["plan_index"] for entry in report["candidates"]] == [1, 1]
    assert {entry["rank"]: entry["plan_index"] for entry in report["assessments"]} == {1: 1, 2: 1}
    # 与既有候选同组的重复不再带第二组序号；纯第二组新增（如有）才标 2
    assert stale.provider_id not in {entry["candidate"]["provider_id"] for entry in report["assessments"]}
    loaded = service.get_selection(report["selection_id"])
    assert [entry["plan_index"] for entry in loaded["candidates"]] == [1, 1]
    service.close()


def test_v1_report_still_readable_and_adoptable(tmp_path, pdf_bytes):
    """QED-068 B 步：报告直写下载面退役，v1 旧契约报告仍可读、rank 仍按 recommendations 校验。"""
    candidate = _candidate("2601.00001", "2026-01-03T00:00:00+00:00", "Legacy report pick")
    manager = DownloadManager(retries=1)
    manager.client.close()
    manager.client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=pdf_bytes)))
    service = PaperService(FakeArxiv([]), ResourceService(tmp_path, manager), advisor=FakeAdvisor({}))
    selection_id = service.selections.new_id()
    v1_report = {
        "selection_id": selection_id,
        "schema_version": 1,
        "status": "ranked",
        "created_at": "2026-01-05T00:00:00+00:00",
        "search_plan": [{"terms": ["legacy term"], "category": "cs.CL", "reason": "旧契约"}],
        "recommendations": [1],
        "assessments": [
            {
                "rank": 1,
                "candidate": asdict(candidate),
                "assessment": asdict(PaperAssessment(candidate.provider_id, 5, 5, 5, "旧评估")),
                "score": 100,
                "recommended": True,
            }
        ],
        "downloads": [],
    }
    service.selections.save(v1_report)

    loaded = service.get_selection(selection_id)
    assert loaded["schema_version"] == 1
    assert loaded["plan_coverage"] == []

    assert loaded["recommendations"] == [1]
    assert not hasattr(service, "download_selection")
    assert service.selections.downloaded_arxiv_ids() == set()
    service.close()


def test_unknown_schema_version_rejected_on_load(tmp_path):
    service = _service(tmp_path, FakeArxiv([]), FakeAdvisor({}))
    selection_id = service.selections.new_id()
    service.selections.save({"selection_id": selection_id, "schema_version": 3, "status": "ranked"})

    with pytest.raises(SelectionStoreError, match="schema_version"):
        service.get_selection(selection_id)
    service.close()


# ---------- QED-068-2（S3）确定性 fallback 与 plan_source 审计 ----------


class PlanFailingAdvisor(FakeAdvisor):
    def __init__(self, scores, error="百炼结构化响应无效：契约破损"):
        super().__init__(scores)
        self.error = error
        self.plan_calls = 0

    def plan(self, profile, goal, allowed_categories):
        self.plan_calls += 1
        raise BailianError(self.error)


def test_plan_source_is_llm_on_normal_recommend(tmp_path):
    candidate = _candidate("2601.00001", "2026-01-03T00:00:00+00:00", "Strong RAG")
    service = _service(tmp_path, FakeArxiv([candidate]), FakeAdvisor({candidate.provider_id: (5, 5, 5)}))

    report = service.recommend(_profile(), goal="reliable RAG", top=5)

    assert report["plan_source"] == "llm"
    loaded = service.get_selection(report["selection_id"])
    assert loaded["plan_source"] == "llm"
    assert loaded["model"]["plan_source"] == "llm"
    service.close()


def test_fallback_plan_on_bailian_error(tmp_path):
    first = _candidate("2601.00021", "2026-01-03T00:00:00+00:00", "F1")
    second = _candidate("2601.00022", "2026-01-03T00:00:00+00:00", "F2")
    third = _candidate("2601.00023", "2026-01-03T00:00:00+00:00", "F3")
    provider = GroupedArxiv(
        {
            ("reliable RAG",): [first, second],
            ("recent advances reliable RAG",): [third],
            ("open challenges reliable RAG",): [],
        }
    )
    advisor = PlanFailingAdvisor({item.provider_id: (5, 5, 5) for item in (first, second, third)})
    service = _service(tmp_path, provider, advisor)

    report = service.recommend(_profile(), goal="reliable RAG", limit=4, top=4)

    assert advisor.plan_calls == 1  # 兜底不新增模型调用
    assert report["status"] == "ranked"
    assert report["plan_source"] == "fallback"
    assert [list(entry["terms"]) for entry in report["search_plan"]] == [
        ["reliable RAG"],
        ["recent advances reliable RAG"],
        ["open challenges reliable RAG"],
    ]
    assert all(entry["category"] == "cs.CL" for entry in report["search_plan"])
    assert all(entry["reason"] == "deterministic fallback" for entry in report["search_plan"])
    assert [entry["kept"] for entry in report["plan_coverage"]] == [2, 1, 0]

    loaded = service.get_selection(report["selection_id"])
    assert loaded["plan_source"] == "fallback"
    assert loaded["model"]["plan_source"] == "fallback"
    assert "百炼结构化响应无效" in loaded["model"]["plan_fallback_error"]
    service.close()


def test_fallback_seed_from_profile_topics(tmp_path):
    provider = GroupedArxiv({})
    advisor = PlanFailingAdvisor({})
    service = _service(tmp_path, provider, advisor)

    report = service.recommend(_profile(), goal="")

    assert [list(entry["terms"]) for entry in report["search_plan"]] == [
        ["retrieval"],
        ["recent advances retrieval"],
        ["open challenges retrieval"],
    ]
    assert report["status"] == "no_candidates"
    service.close()


def test_fallback_seed_is_single_line_and_capped(tmp_path):
    provider = GroupedArxiv({})
    advisor = PlanFailingAdvisor({})
    service = _service(tmp_path, provider, advisor)

    report = service.recommend(_profile(), goal=("x" * 200) + "\nsecond line", top=5)

    seed = report["search_plan"][0]["terms"][0]
    assert seed == "x" * 120
    service.close()


def test_fallback_without_seed_reraises(tmp_path):
    profile = PaperProfile("test", "Test", "Test profile", "Developers", ("RAG",), (), ("cs.CL",), ())
    advisor = PlanFailingAdvisor({})
    service = _service(tmp_path, FakeArxiv([]), advisor)

    with pytest.raises(PaperSelectionError) as captured:
        service.recommend(profile, goal="")

    report = service.get_selection(captured.value.selection_id)
    assert report["status"] == "failed"
    assert "百炼结构化响应无效" in report["error"]
    service.close()


# ---------------- 查重双报同口径（QED-068 C 步 / 068-4） ----------------


class StubBooks:
    """papers 双报用到的书库查询面（避免默认测试触真实 DB）。"""

    def __init__(self, owned_rows=(), paper_rows=None):
        self.owned_rows = list(owned_rows)
        self.paper_rows = paper_rows or {}
        self.title_calls: list[tuple[str, ...]] = []

    def find_owned_by_titles(self, titles, *, exclude_book_ids=()):
        self.title_calls.append(tuple(titles))
        wanted = {str(t).strip().casefold() for t in titles}
        return [row for row in self.owned_rows if str(row.title).strip().casefold() in wanted]

    def find_paper_by_arxiv(self, arxiv_id):
        return self.paper_rows.get(arxiv_id)


def _book_row(book_id: str, title: str, sha256: str = "f" * 64):
    from types import SimpleNamespace

    return SimpleNamespace(
        book_id=book_id, title=title, original_title="", kind="paper", status="downloaded",
        file_path=f"raw/test/_general/papers/2026/{book_id}.pdf", sha256=sha256, size_bytes=1, page_count=1,
    )


def _paper_service(tmp_path, candidates, scores, *, books=None, advisor=None):
    manager = DownloadManager(retries=1)
    manager.client.close()
    manager.client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"")))
    resources = ResourceService(tmp_path, manager, books=books)
    return PaperService(
        FakeArxiv(candidates), resources, advisor=advisor or FakeAdvisor(scores),
    )


def test_recommend_reports_duplicate_buckets_on_same_basis(tmp_path):
    """papers 面双报：ID 命中＝same_content（excluded_existing 逐项展开），标题命中不同内容＝same_name。"""
    downloaded = _candidate("2601.00003", "2026-01-01T00:00:00+00:00", "Existing Paper")
    twin = _candidate("2601.00004", "2026-01-02T00:00:00+00:00", "Held Title")
    fresh = _candidate("2601.00005", "2026-01-03T00:00:00+00:00", "Brand New")
    books = StubBooks(
        owned_rows=[_book_row("test-b77", "held title"), _book_row("test-b78", "Existing Paper")],
        paper_rows={"2601.00003": _book_row("test-b78", "Existing Paper")},
    )
    service = _paper_service(
        tmp_path, [downloaded, twin, fresh],
        {downloaded.provider_id: (5, 5, 5), twin.provider_id: (5, 5, 5), fresh.provider_id: (5, 5, 5)},
        books=books,
    )
    service.selections.save({
        "selection_id": type(service.selections).new_id(),
        "status": "downloaded",
        "downloads": [{"arxiv_id": "2601.00003", "status": "downloaded", "rank": 1, "resource_id": "sha256:x"}],
    })

    report = service.recommend(_profile(), goal="g", top=5)

    assert report["excluded_existing"] == ["2601.00003"]
    content = report["duplicates"]["same_content"]
    assert [item["arxiv_id"] for item in content] == ["2601.00003"]
    assert content[0]["book_id"] == "test-b78"
    names = report["duplicates"]["same_name"]
    assert [(item["arxiv_id"], item["book_id"]) for item in names] == [("2601.00004", "test-b77")]
    # 双报只出清单：twin 仍进候选池，不改已有行
    assert "2601.00004" in [item["candidate"]["identifiers"]["arxiv"] for item in report["assessments"]]
    loaded = service.get_selection(report["selection_id"])
    assert [item["arxiv_id"] for item in loaded["duplicates"]["same_name"]] == ["2601.00004"]
    service.close()


def test_recommend_duplicates_empty_without_db(tmp_path):
    """DB 未配置（books=None）：两桶恒空，推荐链路不受影响。"""
    candidate = _candidate("2601.00006", "2026-01-04T00:00:00+00:00", "No DB")
    service = _paper_service(tmp_path, [candidate], {candidate.provider_id: (5, 5, 5)})

    report = service.recommend(_profile(), goal="g", top=5)

    assert report["duplicates"] == {"same_content": [], "same_name": []}
    assert report["status"] == "ranked"
    service.close()
