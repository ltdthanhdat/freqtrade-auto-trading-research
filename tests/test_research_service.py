import json

import pytest

from research_runtime.collectors import ProviderRetryableError, SourceRecord
from research_runtime.core import CycleStatus, HypothesisState
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


def complete_plan():
    return {
        "schema_version": 1,
        "family_id": "family-a",
        "required_data": ["OHLCV"],
        "entry_plan": {
            "signal_definition": "confirmed continuation",
            "confirmation": "completed candle close",
            "timestamp_semantics": "signal at close",
            "order_assumption": "market",
            "validity_window": "one candle",
            "duplicate_signal_policy": "one entry",
            "pre_fill_invalidation": "cancel on stop cross",
        },
        "exit_designs": [
            {
                "name": "complete",
                "protective_stop": {"type": "FVG_ABSOLUTE", "formula": "structural stop"},
                "profit_exit": {"type": "R_MULTIPLE", "formula": "one R", "multiple": 1},
                "time_exit": {"type": "NONE"},
                "trailing_exit": {"type": "NONE"},
                "regime_exit": {"type": "NONE"},
                "exit_precedence": ["PROTECTIVE_STOP", "PROFIT_TARGET"],
                "gap_behavior": "exchange dependent",
                "stop_update_policy": "fixed",
                "emergency_behavior": "fallback",
            }
        ],
        "sizing_plan": {"risk_basis": "initial stop"},
        "cost_model": {"fees": "configured"},
        "development_protocol": {"windows": ["development"], "attempt_limit": 1},
        "outer_acceptance_policy": {"required_folds": 3},
        "falsifiers": ["negative stressed OOS"],
        "evidence_map": {"entry": ["entry"], "stop": ["stop"], "profit_exit": ["profit"]},
    }


def make_identity_service(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    cycle_id = store.start_or_resume_cycle(
        {
            "now": "2026-09-11T08:00:00Z",
            "dataset": "identity",
            "requested_timerange": "20260101-20260901",
            "search_cohort": "cohort-a",
        }
    )["cycle"]["id"]
    service = ResearchService(store, tmp_path / "artifacts")
    source_ids = {}
    for name, relevance in (
        ("entry", "direct"),
        ("stop", "direct"),
        ("profit", "direct"),
        ("contradiction", "contradicting"),
    ):
        source_id = store.insert_source(
            cycle_id,
            {
                "provider": "fixture",
                "canonical_url": f"https://example.test/{name}",
                "title": name,
                "excerpt": name,
                "retrieved_at": "2026-09-11T08:00:00Z",
                "fingerprint": f"identity-{name}",
                "metadata": {"collector": "fixture"},
            },
        )["id"]
        service.record_source_assessment(
            {
                "cycle_id": cycle_id,
                "source_id": source_id,
                "assessment": {
                    "relevance": relevance,
                    "asset": "crypto",
                    "timeframe": "30m",
                    "mechanism": "continuation",
                },
            }
        )
        source_ids[name] = source_id
    return service, cycle_id, source_ids


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


def test_identity_bound_proposal_persists_complete_plan_and_claim_roles(tmp_path):
    service, cycle_id, sources = make_identity_service(tmp_path)
    payload = {
        **proposal(cycle_id, sources["entry"]),
        "supporting_source_ids": [sources["entry"], sources["stop"], sources["profit"]],
        "contradicting_source_ids": [sources["contradiction"]],
        "trading_plan": complete_plan(),
        "evidence_links": [
            {"source_id": sources["entry"], "stance": "SUPPORT", "note": "entry", "evidence": {"roles": ["ENTRY_SUPPORT"], "supported_claim": "entry", "transfer_assumption": "crypto", "limitations": "limited"}},
            {"source_id": sources["stop"], "stance": "SUPPORT", "note": "stop", "evidence": {"roles": ["STOP_SUPPORT"], "supported_claim": "stop", "transfer_assumption": "crypto", "limitations": "limited"}},
            {"source_id": sources["profit"], "stance": "SUPPORT", "note": "profit", "evidence": {"roles": ["PROFIT_EXIT_SUPPORT"], "supported_claim": "profit", "transfer_assumption": "crypto", "limitations": "limited"}},
            {"source_id": sources["contradiction"], "stance": "CONTRADICT", "note": "falsifier", "evidence": {"roles": ["CONTRADICTION", "FALSIFIER"], "supported_claim": "risk", "transfer_assumption": "crypto", "limitations": "limited"}},
        ],
    }

    result = service.propose_hypothesis(payload)
    hypothesis = result["hypothesis"]

    assert json.loads(hypothesis["plan_json"])["schema_version"] == 1
    assert len(hypothesis["plan_sha256"]) == 64
    links = service.store.list_hypothesis_sources(hypothesis["id"])
    assert {link["stance"] for link in links} == {"SUPPORT", "CONTRADICT"}
    assert all(json.loads(link["evidence_json"])["roles"] for link in links)


def test_identity_bound_proposal_rejects_stance_overlap_and_cross_cycle_source(tmp_path):
    service, cycle_id, sources = make_identity_service(tmp_path)
    base = {
        **proposal(cycle_id, sources["entry"]),
        "supporting_source_ids": [sources["entry"]],
        "contradicting_source_ids": [sources["entry"]],
        "trading_plan": complete_plan(),
    }
    with pytest.raises(ValueError, match="overlap"):
        service.propose_hypothesis(base)

    service.store.set_cycle_status(cycle_id, CycleStatus.COMPLETED, "finish")
    other_cycle = service.store.start_or_resume_cycle(
        {"now": "2026-09-11T08:01:00Z", "dataset": "other"}
    )["cycle"]["id"]
    other_source = service.store.insert_source(
        other_cycle,
        {"provider": "fixture", "canonical_url": "https://example.test/other", "title": "other", "excerpt": "e", "retrieved_at": "2026-09-11T08:01:00Z", "fingerprint": "other-source", "metadata": {}},
    )["id"]
    with pytest.raises(ValueError, match="source provenance"):
        service.propose_hypothesis({**base, "supporting_source_ids": [other_source], "contradicting_source_ids": [sources["contradiction"]]})


def test_entry_only_evidence_cannot_authorize_complete_exit_plan(tmp_path):
    service, cycle_id, sources = make_identity_service(tmp_path)
    payload = {
        **proposal(cycle_id, sources["entry"]),
        "supporting_source_ids": [sources["entry"]],
        "contradicting_source_ids": [sources["contradiction"]],
        "trading_plan": complete_plan(),
        "evidence_links": [
            {"source_id": sources["entry"], "stance": "SUPPORT", "note": "entry", "evidence": {"roles": ["ENTRY_SUPPORT"], "supported_claim": "entry", "transfer_assumption": "crypto", "limitations": "limited"}},
            {"source_id": sources["contradiction"], "stance": "CONTRADICT", "note": "falsifier", "evidence": {"roles": ["CONTRADICTION"], "supported_claim": "risk", "transfer_assumption": "crypto", "limitations": "limited"}},
        ],
    }
    hypothesis = service.propose_hypothesis(payload)["hypothesis"]

    with pytest.raises(ValueError, match="exit evidence"):
        service.write_candidate(
            {"cycle_id": cycle_id, "hypothesis_id": hypothesis["id"], "strategy_name": "CandidateA", "source": "class CandidateA: pass\n"}
        )


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


def test_source_views_are_cycle_scoped_bounded_and_assessment_aware(tmp_path):
    service, cycle_id, source_id = make_service(tmp_path)
    long_excerpt = "x" * 5001
    service.store.insert_source(
        cycle_id,
        {
            "provider": "fixture",
            "canonical_url": "https://example.test/long",
            "title": "long source",
            "excerpt": long_excerpt,
            "retrieved_at": "2026-09-11T07:59:00Z",
            "fingerprint": "long-source",
            "metadata": {"collector_fact": "kept"},
        },
    )
    service.store.insert_source_assessment(
        cycle_id,
        source_id,
        {"relevance": "indirect", "asset": "crypto", "timeframe": "30m", "mechanism": "old"},
        actor="runtime",
        created_at="2026-09-11T08:00:01Z",
    )
    service.store.insert_source_assessment(
        cycle_id,
        source_id,
        {"relevance": "direct", "asset": "crypto", "timeframe": "30m", "mechanism": "new"},
        actor="runtime",
        created_at="2026-09-11T08:00:02Z",
    )

    result = service.call("list_source_views", {"cycle_id": cycle_id, "limit": 2})

    assert len(result["sources"]) == 2
    long_view = next(item for item in result["sources"] if item["title"] == "long source")
    assert len(long_view["excerpt"]) == 4000
    view = next(item for item in result["sources"] if item["title"] == "source")
    assert view["collector_metadata"] == {"full_text": True}
    assert len(view["collector_metadata_sha256"]) == 64
    assert view["assessment"] == {
        "relevance": "direct",
        "asset": "crypto",
        "timeframe": "30m",
        "mechanism": "new",
    }
    assert view["assessment_count"] == 2
    assert result["next_cursor"]


def test_record_source_assessment_cannot_mutate_collector_facts(tmp_path):
    service, cycle_id, source_id = make_service(tmp_path)

    with pytest.raises(ValueError, match="immutable collector facts"):
        service.record_source_assessment(
            {
                "cycle_id": cycle_id,
                "source_id": source_id,
                "assessment": {
                    "relevance": "direct",
                    "asset": "crypto",
                    "timeframe": "30m",
                    "mechanism": "continuation",
                    "full_text_available": True,
                    "canonical_url": "https://forged.example",
                },
            }
        )

    source = service.store.get_source(source_id)
    assert source["metadata_json"] == '{"full_text":true}'


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


def test_write_candidate_selects_only_highest_scored_hypothesis(tmp_path):
    service, cycle_id, source_id = make_service(tmp_path)
    lower = service.propose_hypothesis(proposal(cycle_id, source_id, mechanism="lower"))["hypothesis"]
    higher_payload = proposal(cycle_id, source_id, mechanism="higher")
    higher_payload["scores"]["evidence_quality"] = 30
    higher = service.propose_hypothesis(higher_payload)["hypothesis"]

    with pytest.raises(ValueError, match="highest-scoring"):
        service.write_candidate(
            {"cycle_id": cycle_id, "hypothesis_id": lower["id"], "strategy_name": "CandidateA", "source": "class CandidateA: pass\n"}
        )
    result = service.write_candidate(
        {"cycle_id": cycle_id, "hypothesis_id": higher["id"], "strategy_name": "CandidateA", "source": "class CandidateA: pass\n"}
    )
    assert result["candidate"]["strategy_name"] == "CandidateA"
    assert service.store.get_hypothesis(higher["id"])["state"] == HypothesisState.IMPLEMENTING


def test_write_candidate_requires_explicit_full_text_or_independent_evidence(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    cycle_id = store.start_or_resume_cycle("2026-09-11T08:00:00Z")["cycle"]["id"]
    source_id = store.insert_source(
        cycle_id,
        {
            "provider": "openalex",
            "canonical_url": "https://example.test/abstract",
            "title": "abstract only",
            "excerpt": "abstract",
            "retrieved_at": "2026-09-11T08:00:00Z",
            "fingerprint": "abstract-source",
            "metadata": {},
        },
    )["id"]
    service = ResearchService(store, tmp_path / "artifacts")
    hypothesis = service.propose_hypothesis(proposal(cycle_id, source_id))["hypothesis"]
    with pytest.raises(ValueError, match="full-text or corroborating"):
        service.write_candidate(
            {"cycle_id": cycle_id, "hypothesis_id": hypothesis["id"], "strategy_name": "CandidateA", "source": "class CandidateA: pass\n"}
        )


def test_structured_evidence_requires_a_contradicting_source(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    cycle_id = store.start_or_resume_cycle("2026-09-11T08:00:00Z")["cycle"]["id"]
    support = store.insert_source(
        cycle_id,
        {
            "provider": "openalex",
            "canonical_url": "https://example.test/direct",
            "title": "direct",
            "excerpt": "direct",
            "retrieved_at": "2026-09-11T08:00:00Z",
            "fingerprint": "structured-support",
            "metadata": {"relevance": "direct", "asset": "crypto", "timeframe": "30m", "mechanism": "continuation"},
        },
    )["id"]
    service = ResearchService(store, tmp_path / "artifacts")
    hypothesis = service.propose_hypothesis(proposal(cycle_id, support)) ["hypothesis"]
    with pytest.raises(ValueError, match="full-text or corroborating"):
        service.write_candidate(
            {"cycle_id": cycle_id, "hypothesis_id": hypothesis["id"], "strategy_name": "CandidateA", "source": "class CandidateA: pass\n"}
        )


def test_identity_bound_cycle_requires_structured_support_and_contradiction(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    cycle_id = store.start_or_resume_cycle(
        {"now": "2026-09-11T08:00:00Z", "dataset": "accepted", "requested_timerange": "20260101-20260901", "search_cohort": "cohort"}
    )["cycle"]["id"]
    source_id = store.insert_source(
        cycle_id,
        {"provider": "openalex", "canonical_url": "https://example.test/source", "title": "source", "excerpt": "e", "retrieved_at": "2026-09-11T08:00:00Z", "fingerprint": "bound-source", "metadata": {"relevance": "direct", "asset": "crypto", "timeframe": "30m", "mechanism": "continuation"}},
    )["id"]
    service = ResearchService(store, tmp_path / "artifacts")
    with pytest.raises(ValueError, match="structured evidence"):
        service.propose_hypothesis(proposal(cycle_id, source_id))


def test_identity_bound_assessment_rejects_free_text(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    cycle_id = store.start_or_resume_cycle(
        {"now": "2026-09-11T08:00:00Z", "dataset": "accepted", "requested_timerange": "20260101-20260901", "search_cohort": "cohort"}
    )["cycle"]["id"]
    source_id = store.insert_source(
        cycle_id,
        {"provider": "openalex", "canonical_url": "https://example.test/source", "title": "source", "excerpt": "e", "retrieved_at": "2026-09-11T08:00:00Z", "fingerprint": "free-text-source", "metadata": {}},
    )["id"]
    service = ResearchService(store, tmp_path / "artifacts")
    with pytest.raises(ValueError, match="structured source assessment"):
        service.record_source_assessment(
            {"cycle_id": cycle_id, "source_id": source_id, "assessment": "relevant evidence"}
        )


def test_start_validation_records_run_and_is_idempotent(tmp_path):
    service, cycle_id, source_id = make_service(tmp_path)
    hypothesis = service.propose_hypothesis(proposal(cycle_id, source_id))["hypothesis"]
    hypothesis = service.write_candidate(
        {"cycle_id": cycle_id, "hypothesis_id": hypothesis["id"], "strategy_name": "CandidateA", "source": "class CandidateA: pass\n"}
    )["hypothesis"]
    calls = []
    service.validator = lambda experiment: calls.append(experiment) or {
        "verdict": "PASS",
        "metrics": {"profit": 1},
        "artifacts": {"manifest": "m"},
    }
    result = service.start_validation({"cycle_id": cycle_id, "hypothesis_id": hypothesis["id"]})
    replay = service.start_validation({"cycle_id": cycle_id, "hypothesis_id": hypothesis["id"]})
    assert calls[0]["candidate_path"] == hypothesis["candidate_path"]
    assert result["state"] == HypothesisState.NEEDS_REVIEW
    assert replay["state"] == HypothesisState.NEEDS_REVIEW
    assert len(calls) == 1
    with service.store.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1


def test_start_validation_does_not_promote_retryable_result(tmp_path):
    service, cycle_id, source_id = make_service(tmp_path)
    hypothesis = service.propose_hypothesis(proposal(cycle_id, source_id))["hypothesis"]
    service.write_candidate(
        {"cycle_id": cycle_id, "hypothesis_id": hypothesis["id"], "strategy_name": "CandidateA", "source": "class CandidateA: pass\n"}
    )
    service.validator = lambda _experiment: (_ for _ in ()).throw(OSError("temporary"))
    result = service.start_validation({"cycle_id": cycle_id, "hypothesis_id": hypothesis["id"]})
    assert result["state"] == "RETRYABLE"
    assert service.store.get_hypothesis(hypothesis["id"])["state"] == HypothesisState.TESTING


def test_retryable_validation_creates_a_new_attempt(tmp_path):
    service, cycle_id, source_id = make_service(tmp_path)
    hypothesis = service.propose_hypothesis(proposal(cycle_id, source_id))["hypothesis"]
    service.write_candidate(
        {"cycle_id": cycle_id, "hypothesis_id": hypothesis["id"], "strategy_name": "CandidateA", "source": "class CandidateA: pass\n"}
    )
    attempts = iter([OSError("temporary"), {"verdict": "PASS", "metrics": {}, "artifacts": {}}])
    service.validator = lambda _experiment: next(attempts)
    first = service.start_validation({"cycle_id": cycle_id, "hypothesis_id": hypothesis["id"]})
    second = service.start_validation({"cycle_id": cycle_id, "hypothesis_id": hypothesis["id"]})
    assert first["state"] == "RETRYABLE"
    assert second["state"] == HypothesisState.NEEDS_REVIEW
    runs = service.store.list_runs(second["experiment_id"])
    assert len(runs) == 2
    assert runs[0]["id"] != runs[1]["id"]
