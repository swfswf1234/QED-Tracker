from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from qed_tracker.application.papers import PaperService
from qed_tracker.application.resources import ResourceService
from qed_tracker.downloader import DownloadManager
from qed_tracker.models import Candidate, PaperAssessment, PaperProfile, PaperSearch


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


def test_recommendation_is_audited_and_download_requires_saved_pick(tmp_path, pdf_bytes):
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

    downloaded, failures = service.download_selection(report["selection_id"], [1])
    assert failures == 0
    assert downloaded["status"] == "downloaded"
    assert downloaded["downloads"][0]["resource_id"].startswith("sha256:")
    assert list((tmp_path / "raw" / "math" / "_general" / "papers" / "2026").glob("*.pdf"))
    assert service.selections.downloaded_arxiv_ids() >= {"2601.00003", "2601.00001"}
    with pytest.raises(ValueError, match="推荐序号"):
        service.download_selection(report["selection_id"], [2])
    service.close()


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
