import pytest

from research_runtime.collectors import SourceRecord
from research_runtime.core import HypothesisState
from research_runtime.service import ResearchService
from research_runtime.store import ResearchStore


def proposal(cycle_id, source_id, index):
    return {
        "cycle_id": cycle_id,
        "thesis": f"momentum thesis {index}",
        "mechanism": f"bounded momentum persistence {index}",
        "market_scope": "crypto perpetuals 30m",
        "required_data": ["OHLCV"],
        "falsifier": "aggregate stressed OOS profit <= 0",
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


def test_cycle_is_bounded_and_stops_for_review(tmp_path):
    records = [
        SourceRecord(
            provider="openalex",
            title=f"source {index}",
            excerpt="full-text evidence",
            canonical_url=f"https://example.test/{index}",
            doi=None,
            license="CC-BY",
            retrieved_at="2026-09-11T08:00:00Z",
            fingerprint=f"fingerprint-{index}",
            metadata={"full_text": True},
        )
        for index in range(100)
    ]
    store = ResearchStore(tmp_path / "research.sqlite")
    service = ResearchService(
        store,
        artifact_root=tmp_path / "artifacts",
        collectors={"openalex": lambda _query, _limit: records},
        validator=lambda _experiment: {"verdict": "PASS", "artifacts": {}, "metrics": {}},
    )
    cycle = service.start_or_resume_cycle({"now": "2026-09-11T08:00:00Z"})["cycle"]
    service.collect_sources(
        {"cycle_id": cycle["id"], "provider": "openalex", "query": "momentum", "limit": 100}
    )
    sources = [store.get_source(f"S-fingerprint-{index}") for index in range(100)]
    hypotheses = [
        service.propose_hypothesis(proposal(cycle["id"], sources[index]["id"], index))
        for index in range(3)
    ]
    with pytest.raises(ValueError, match="hypothesis budget"):
        service.propose_hypothesis(proposal(cycle["id"], sources[0]["id"], 4))
    selected = hypotheses[0]["hypothesis"]
    service.write_candidate(
        {
            "cycle_id": cycle["id"],
            "hypothesis_id": selected["id"],
            "strategy_name": "ResearchCandidate",
            "source": "class ResearchCandidate:\n    pass\n",
        }
    )
    result = service.start_validation({"cycle_id": cycle["id"], "hypothesis_id": selected["id"]})
    replay = service.start_validation({"cycle_id": cycle["id"], "hypothesis_id": selected["id"]})
    assert result["state"] == HypothesisState.NEEDS_REVIEW
    assert replay["state"] == HypothesisState.NEEDS_REVIEW
    assert service.load_context({"cycle_id": cycle["id"]})["budgets"] == {
        "sources": 100,
        "hypotheses": 3,
        "candidates": 1,
    }
    assert store.get_cycle(cycle["id"])["source_count"] == 100
    assert store.get_cycle(cycle["id"])["candidate_count"] == 1
    with store.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
    assert not any("dry" in event["reason"].lower() for event in store.events(cycle["id"]))
