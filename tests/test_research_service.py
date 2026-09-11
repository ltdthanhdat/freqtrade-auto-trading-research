import pytest

from research_runtime.core import HypothesisState
from research_runtime.service import ResearchService
from research_runtime.store import ResearchStore


def proposal(cycle_id, source_id, *, required_data=("OHLCV",), mechanism="continuation"):
    return {
        "cycle_id": cycle_id,
        "thesis": "momentum persists",
        "mechanism": mechanism,
        "market_scope": "crypto",
        "required_data": list(required_data),
        "falsifier": "negative stressed OOS",
        "scores": {
            "evidence_quality": 20,
            "reproducibility": 20,
            "ohlcv_transferability": 15,
            "novelty": 5,
            "falsifiability": 10,
        },
        "supporting_source_ids": [source_id],
        "contradicting_source_ids": [],
    }


def make_service(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    cycle_id = store.start_or_resume_cycle("2026-09-11T08:00:00Z")["cycle"]["id"]
    source_id = store.insert_source(
        cycle_id,
        {
            "provider": "openalex",
            "canonical_url": "https://example.test/source",
            "title": "source",
            "excerpt": "full text",
            "retrieved_at": "2026-09-11T08:00:00Z",
            "fingerprint": "source-fingerprint",
            "metadata": {"full_text": True},
        },
    )["id"]
    return ResearchService(store, tmp_path / "artifacts"), cycle_id, source_id


def test_proposal_requires_provenance_and_moves_unsupported_data_to_backlog(tmp_path):
    service, cycle_id, source_id = make_service(tmp_path)
    with pytest.raises(ValueError, match="source provenance"):
        service.propose_hypothesis({**proposal(cycle_id, "missing"), "supporting_source_ids": ["missing"]})
    backlog = service.propose_hypothesis(
        proposal(cycle_id, source_id, required_data=("OHLCV", "options_chain"))
    )["hypothesis"]
    assert backlog["state"] == HypothesisState.BACKLOG


def test_duplicate_mechanism_attaches_evidence_without_new_hypothesis(tmp_path):
    service, cycle_id, source_id = make_service(tmp_path)
    first = service.propose_hypothesis(proposal(cycle_id, source_id))["hypothesis"]
    duplicate = service.propose_hypothesis(
        {**proposal(cycle_id, source_id, mechanism="  CONTINUATION "), "metadata": {"new": True}}
    )
    assert duplicate["duplicate"] is True
    assert duplicate["hypothesis"]["id"] == first["id"]
    assert service.store.get_cycle(cycle_id)["hypothesis_count"] == 1


def test_service_records_interpretation_and_finalizes_cycle(tmp_path):
    service, cycle_id, source_id = make_service(tmp_path)
    hypothesis = service.propose_hypothesis(proposal(cycle_id, source_id))["hypothesis"]
    result = service.record_interpretation(
        {"cycle_id": cycle_id, "hypothesis_id": hypothesis["id"], "interpretation": "pass"}
    )
    assert result["recorded"] is True
    final = service.finalize_cycle(
        {"cycle_id": cycle_id, "status": "NEEDS_REVIEW", "reason": "validation passed"}
    )
    assert final["cycle"]["status"] == "NEEDS_REVIEW"
