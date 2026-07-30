from qed_tracker.application.papers import PaperSelectionError
from qed_tracker.cli import main
from qed_tracker.selection_store import SelectionStoreError

SELECTION_ID = "sel-20260730T000000Z-12345678"


def _report(status="ranked"):
    return {
        "selection_id": SELECTION_ID,
        "status": status,
        "created_at": "2026-07-30T00:00:00+00:00",
        "profile": {"id": "llm-engineering"},
        "assessments": [],
        "recommendations": [],
    }


class FakePaperService:
    def __init__(self):
        self.closed = False
        self.download_calls = []

    def close(self):
        self.closed = True

    def recommend(self, profile, **kwargs):
        if kwargs["goal"] == "runtime failure":
            raise PaperSelectionError(f"论文推荐失败；报告 {SELECTION_ID}", SELECTION_ID)
        return _report("no_recommendations")

    def download_selection(self, selection_id, picks):
        self.download_calls.append((selection_id, tuple(picks)))
        if selection_id == "sel-20260730T000000Z-00000000":
            raise ValueError("只能下载报告中的推荐序号")
        if selection_id == "sel-20260730T000000Z-11111111":
            raise SelectionStoreError("论文选择报告不存在")
        failures = 1 if selection_id == SELECTION_ID else 2
        return _report("partially_downloaded" if failures == 1 else "download_failed"), failures


def test_paper_cli_returns_2_for_invalid_saved_pick(monkeypatch, tmp_path):
    service = FakePaperService()
    monkeypatch.setattr("qed_tracker.cli._paper_service", lambda settings, with_advisor=False: service)

    result = main([
        "--data-root", str(tmp_path), "papers", "selections", "download",
        "sel-20260730T000000Z-00000000", "--pick", "9",
    ])

    assert result == 2
    assert service.closed


def test_paper_cli_returns_3_when_recommendation_has_no_match(monkeypatch, tmp_path):
    service = FakePaperService()
    monkeypatch.setattr("qed_tracker.cli._paper_service", lambda settings, with_advisor=False: service)

    result = main([
        "--data-root", str(tmp_path), "papers", "recommend", "no match",
        "--profile", "llm-engineering",
    ])

    assert result == 3
    assert service.closed


def test_paper_cli_replays_fixed_selection_and_returns_4_for_partial_failure(monkeypatch, tmp_path):
    service = FakePaperService()
    monkeypatch.setattr("qed_tracker.cli._paper_service", lambda settings, with_advisor=False: service)

    result = main([
        "--data-root", str(tmp_path), "papers", "selections", "download",
        SELECTION_ID, "--pick", "1", "--pick", "2",
    ])

    assert result == 4
    assert service.download_calls == [(SELECTION_ID, (1, 2))]
    assert service.closed


def test_paper_cli_returns_5_for_model_or_complete_download_failure(monkeypatch, tmp_path):
    services = []

    def factory(settings, with_advisor=False):
        service = FakePaperService()
        services.append(service)
        return service

    monkeypatch.setattr("qed_tracker.cli._paper_service", factory)
    recommend_result = main([
        "--data-root", str(tmp_path), "papers", "recommend", "runtime failure",
        "--profile", "llm-engineering",
    ])
    download_result = main([
        "--data-root", str(tmp_path), "papers", "selections", "download",
        "sel-20260730T000000Z-99999999", "--pick", "1", "--pick", "2",
    ])
    missing_report_result = main([
        "--data-root", str(tmp_path), "papers", "selections", "download",
        "sel-20260730T000000Z-11111111", "--pick", "1",
    ])

    assert recommend_result == 5
    assert download_result == 5
    assert missing_report_result == 5
    assert all(service.closed for service in services)
