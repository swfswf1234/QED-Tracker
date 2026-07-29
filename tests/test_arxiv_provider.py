from datetime import UTC, datetime
from types import SimpleNamespace

from qed_tracker.providers.arxiv import ArxivProvider


def test_arxiv_result_is_normalized_to_candidate():
    item = SimpleNamespace(
        entry_id="https://arxiv.org/abs/2401.00001",
        title="  A   Paper\nTitle ",
        authors=[SimpleNamespace(name="Ada"), SimpleNamespace(name="Emmy")],
        published=datetime(2024, 1, 2, tzinfo=UTC),
        pdf_url="https://arxiv.org/pdf/2401.00001",
        summary="An\nabstract",
    )
    candidate = ArxivProvider._candidate(item)
    assert candidate.provider_id == "2401.00001"
    assert candidate.title == "A Paper Title"
    assert candidate.authors == ("Ada", "Emmy")
    assert candidate.identifiers == {"arxiv": "2401.00001"}
