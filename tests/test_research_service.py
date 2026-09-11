import pytest

from research_runtime.collectors import ProviderRetryableError, SourceRecord
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


def test_collect_sources_retries_temporary_provider_failure_and_records_error(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    cycle_id = store.start_or_resume_cycle("2026-09-11T08:00:00Z")["cycle"]["id"]
    attempts = []

    def collector(query, limit):
        attempts.append((query, limit))
        raise ProviderRetryableError("rate limited")

    service = ResearchService(
        store,
        tmp_path / "artifacts",
        collectors={"openalex": collector},
        sleeper=lambda _seconds: None,
    )
    result = service.collect_sources(
        {"cycle_id": cycle_id, "provider": "openalex", "query": "RSI", "limit": 2}
    )
    assert len(attempts) == 3
    assert result["accepted_ids"] == []
    assert result["duplicate_ids"] == []
    assert result["provider_errors"][0]["code"] == "retry_exhausted"
    assert any(event["reason"] == "source collection failed" for event in store.events(cycle_id))


def test_collect_sources_does_not_request_more_than_remaining_budget(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    cycle_id = store.start_or_resume_cycle("2026-09-11T08:00:00Z")["cycle"]["id"]
    for index in range(99):
        store.insert_source(
            cycle_id,
            {
                "provider": "fixture",
                "canonical_url": f"https://example.test/{index}",
                "title": f"source {index}",
                "excerpt": "evidence",
                "retrieved_at": "2026-09-11T08:00:00Z",
                "fingerprint": f"fp-{index}",
                "metadata": {},
            },
        )
    called = False

    def collector(_query, _limit):
        nonlocal called
        called = True
        return []

    service = ResearchService(store, tmp_path / "artifacts", collectors={"fixture": collector})
    with pytest.raises(ValueError, match="source budget remaining"):
        service.collect_sources(
            {"cycle_id": cycle_id, "provider": "fixture", "query": "x", "limit": 2}
        )
    assert called is False


def test_collect_sources_persists_records_and_duplicates_separately(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    cycle_id = store.start_or_resume_cycle("2026-09-11T08:00:00Z")["cycle"]["id"]
    record = SourceRecord(
        provider="fixture",
        title="source",
        excerpt="evidence",
        canonical_url="https://example.test/source",
        doi=None,
        license=None,
        retrieved_at="2026-09-11T08:00:00Z",
        fingerprint="fp-source",
        metadata={},
    )
    service = ResearchService(
        store,
        tmp_path / "artifacts",
        collectors={"fixture": lambda _query, _limit: [record, record]},
    )
    result = service.collect_sources(
        {"cycle_id": cycle_id, "provider": "fixture", "query": "x", "limit": 2}
    )
    assert len(result["accepted_ids"]) == 1
    assert result["duplicate_ids"] == [result["accepted_ids"][0]]
