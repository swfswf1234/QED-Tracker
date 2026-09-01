from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from qed_tracker.application.papers import PaperService
from qed_tracker.application.resources import ResourceService
from qed_tracker.downloader import DownloadManager
from qed_tracker.inventory import Inventory
from qed_tracker.models import Candidate, PaperAssessment, PaperProfile, PaperSearch, ResourceKind


class FakeArxiv:
    def __init__(self, candidates):
        self.candidates = candidates
        self.searches = []

    def search_terms(self, terms, *, category, limit=10):
        self.searches.append((terms, category, limit))
        return list(self.candidates)

    def search(self, query="", *, category="", author="", limit=10):
        return list(self.candidates)

    def get(self, identifier):
        return next(item for item in self.candidates if item.provider_id == identifier)

    def close(self):
        return None


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


def _candidate(identifier: str, score_date: str, title: str) -> Candidate:
    return Candidate(
        "arxiv", identifier, title, ("Ada",), "en", "2026",
        page_url=f"https://arxiv.org/abs/{identifier}",
        download_url=f"https://arxiv.org/pdf/{identifier}",
        identifiers={"arxiv": identifier}, abstract=f"Abstract for {title}",
        subjects=("cs.CL",), published_at=score_date, updated_at=score_date,
    )


def _profile() -> PaperProfile:
    return PaperProfile("test", "Test", "Test profile", "Developers", ("RAG",), ("retrieval",), ("cs.CL",), ())


def test_recommendation_is_audited_and_download_requires_saved_pick(tmp_path, pdf_bytes):
    first = _candidate("2601.00001", "2026-01-03T00:00:00+00:00", "Strong RAG")
    second = _candidate("2601.00002", "2026-01-02T00:00:00+00:00", "Weak RAG")
    existing = _candidate("2601.00003", "2026-01-01T00:00:00+00:00", "Existing")
    existing_pdf = tmp_path / "existing.pdf"
    existing_pdf.write_bytes(pdf_bytes + b"\n% existing variant\n")
    inventory = Inventory(tmp_path)
    inventory.register(existing_pdf, kind=ResourceKind.PAPER, title=existing.title, identifiers=existing.identifiers)
    manager = DownloadManager(retries=1)
    manager.client.close()
    manager.client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=pdf_bytes)))
    advisor = FakeAdvisor({first.provider_id: (5, 5, 5), second.provider_id: (2, 2, 2)})
    provider = FakeArxiv([first, second, existing, first])
    service = PaperService(provider, ResourceService(inventory, manager), advisor=advisor)

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
    assert inventory.list(ResourceKind.PAPER.value)
    with pytest.raises(ValueError, match="推荐序号"):
        service.download_selection(report["selection_id"], [2])
    service.close()


def test_recommendation_without_eligible_candidate_returns_report(tmp_path):
    candidate = _candidate("2601.00004", "2026-01-01T00:00:00+00:00", "Unrelated")
    manager = DownloadManager(retries=1)
    service = PaperService(
        FakeArxiv([candidate]),
        ResourceService(Inventory(tmp_path), manager),
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
        ResourceService(Inventory(tmp_path), manager),
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
        ResourceService(Inventory(tmp_path), manager),
        advisor=FailingAdvisor({}),
    )

    with pytest.raises(RuntimeError, match="报告") as captured:
        service.recommend(_profile())

    report = service.get_selection(captured.value.selection_id)
    assert report["status"] == "failed"
    assert report["error"] == "advisor unavailable"
    service.close()
