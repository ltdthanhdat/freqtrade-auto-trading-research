from datetime import datetime, timedelta, timezone

import pytest

from research_runtime.core import HypothesisState
from research_runtime.store import ResearchStore


def test_store_creates_exact_v1_tables(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    with store.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert tables == {
            "cycles",
            "sources",
            "hypotheses",
            "hypothesis_sources",
            "experiments",
            "runs",
            "state_events",
        }
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_cycle_lease_excludes_live_worker_and_resumes_expired_lease(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite", lease_seconds=60)
    first_now = datetime(2026, 9, 11, 8, 0, tzinfo=timezone.utc)
    first = store.start_or_resume_cycle(first_now)
    blocked = store.start_or_resume_cycle(first_now + timedelta(seconds=10))
    assert blocked["cycle"]["id"] == first["cycle"]["id"]
    assert blocked["acquired"] is False

    resumed = store.start_or_resume_cycle(first_now + timedelta(seconds=61))
    assert resumed["cycle"]["id"] == first["cycle"]["id"]
    assert resumed["acquired"] is True
    assert store.get_cycle(first["cycle"]["id"])["status"] == "RUNNING"
    events = store.events(first["cycle"]["id"])
    assert any(event["to_state"] == "INTERRUPTED" for event in events)


def test_source_deduplication_and_budget(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    cycle_id = store.start_or_resume_cycle("2026-09-11T08:00:00Z")["cycle"]["id"]
    source = {
        "provider": "openalex",
        "canonical_url": "https://doi.org/10.1234/example",
        "doi": "10.1234/example",
        "title": "A source",
        "excerpt": "Evidence",
        "license": "CC-BY",
        "retrieved_at": "2026-09-11T08:00:00Z",
        "fingerprint": "fingerprint-1",
        "metadata": {},
    }
    first = store.insert_source(cycle_id, source)
    duplicate = store.insert_source(cycle_id, {**source, "fingerprint": "fingerprint-2"})
    assert first["inserted"] is True
    assert duplicate["inserted"] is False
    assert duplicate["id"] == first["id"]

    for index in range(99):
        store.insert_source(cycle_id, {**source, "canonical_url": f"https://example.test/{index}", "doi": None, "fingerprint": f"fp-{index}"})
    with pytest.raises(ValueError, match="source budget"):
        store.insert_source(cycle_id, {**source, "canonical_url": "https://example.test/overflow", "doi": None, "fingerprint": "fp-overflow"})


def test_hypothesis_budget_and_legal_transition_are_append_only(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    cycle_id = store.start_or_resume_cycle("2026-09-11T08:00:00Z")["cycle"]["id"]
    payload = {
        "thesis": "momentum persists",
        "mechanism": "continuation",
        "market_scope": "crypto",
        "required_data": ["OHLCV"],
        "falsifier": "negative stressed OOS",
        "scores": {
            "evidence_quality": 20,
            "reproducibility": 20,
            "ohlcv_transferability": 15,
            "novelty": 5,
            "falsifiability": 10,
        },
        "metadata": {},
    }
    hypotheses = [store.insert_hypothesis(cycle_id, {**payload, "id": f"H-{index}"}) for index in range(3)]
    assert len(hypotheses) == 3
    with pytest.raises(ValueError, match="hypothesis budget"):
        store.insert_hypothesis(cycle_id, {**payload, "id": "H-overflow"})

    store.transition_hypothesis("H-0", HypothesisState.QUEUED, "runtime", "selected")
    store.transition_hypothesis("H-0", HypothesisState.IMPLEMENTING, "runtime", "writing candidate")
    events_before = store.events(cycle_id)
    with pytest.raises(ValueError, match="illegal transition"):
        store.transition_hypothesis("H-0", HypothesisState.APPROVED_FOR_DRY_RUN, "local_user", "skip")
    assert store.events(cycle_id) == events_before


def test_review_requires_actor_and_reason(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    cycle_id = store.start_or_resume_cycle("2026-09-11T08:00:00Z")["cycle"]["id"]
    payload = {
        "id": "H-review",
        "thesis": "x",
        "mechanism": "y",
        "market_scope": "crypto",
        "required_data": ["OHLCV"],
        "falsifier": "z",
        "scores": {
            "evidence_quality": 1,
            "reproducibility": 1,
            "ohlcv_transferability": 1,
            "novelty": 1,
            "falsifiability": 1,
        },
    }
    store.insert_hypothesis(cycle_id, payload)
    store.transition_hypothesis("H-review", HypothesisState.QUEUED, "runtime", "queue")
    with pytest.raises(ValueError, match="actor"):
        store.transition_hypothesis("H-review", HypothesisState.IMPLEMENTING, "", "queue")
    with pytest.raises(ValueError, match="reason"):
        store.transition_hypothesis("H-review", HypothesisState.IMPLEMENTING, "runtime", " ")
