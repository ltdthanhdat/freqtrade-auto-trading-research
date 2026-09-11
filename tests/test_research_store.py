from datetime import datetime, timedelta, timezone

import pytest

from research_runtime.core import CycleStatus, HypothesisState
from research_runtime.store import ResearchStore


def test_store_creates_v2_tables_and_identity_columns(tmp_path):
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
            "validation_windows",
        }
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        cycle_columns = {row[1] for row in connection.execute("PRAGMA table_info(cycles)")}
        assert {"dataset", "requested_timerange", "holdout_start", "holdout_end", "search_cohort"} <= cycle_columns
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_cycle_identity_is_persisted_and_terminal_transitions_are_checked(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    result = store.start_or_resume_cycle(
        {
            "now": "2026-09-11T08:00:00Z",
            "dataset": "accepted",
            "requested_timerange": "20260124-20260911",
            "holdout_start": "2026-08-22T00:00:00Z",
            "holdout_end": "2026-09-11T00:00:00Z",
            "search_cohort": "cohort-a",
        }
    )
    cycle_id = result["cycle"]["id"]
    cycle = store.get_cycle(cycle_id)
    assert cycle["dataset"] == "accepted"
    assert cycle["requested_timerange"] == "20260124-20260911"
    assert cycle["search_cohort"] == "cohort-a"
    assert store.set_cycle_status(cycle_id, CycleStatus.NEEDS_REVIEW, "review") ["stage"] == "REVIEW"
    with pytest.raises(ValueError, match="illegal cycle transition"):
        store.set_cycle_status(cycle_id, CycleStatus.RUNNING, "reopen")


def test_record_run_keeps_retry_attempts_append_only(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    cycle_id = store.start_or_resume_cycle("2026-09-11T08:00:00Z")["cycle"]["id"]
    store.insert_hypothesis(
        cycle_id,
        {
            "id": "H-retry",
            "thesis": "x",
            "mechanism": "y",
            "market_scope": "crypto",
            "required_data": ["OHLCV"],
            "falsifier": "z",
            "scores": {"evidence_quality": 1, "reproducibility": 1, "ohlcv_transferability": 1, "novelty": 1, "falsifiability": 1},
        },
    )
    experiment = store.insert_experiment(
        {
            "id": "EXP-retry",
            "cycle_id": cycle_id,
            "hypothesis_id": "H-retry",
            "parent_strategy": "parent",
            "parent_sha256": "a",
            "changed_variable": "x",
            "config_path": "config",
            "config_sha256": "b",
            "pairs": [],
            "timeframes": ["30m"],
            "timeframe_detail": "1m",
            "snapshot_path": "snapshot",
            "snapshot_sha256": "c",
            "policy_path": "policy",
            "policy_sha256": "d",
            "strategy_name": "candidate",
            "strategy_path": "src",
            "start_at": "2026-01-01T00:00:00Z",
            "end_at": "2026-02-01T00:00:00Z",
            "status": "PENDING",
        }
    )
    store.record_run({"id": "RUN-a", "experiment_id": experiment["id"], "kind": "validation", "status": "RETRYABLE", "metrics": {}, "artifact_manifest": {}})
    store.record_run({"id": "RUN-b", "experiment_id": experiment["id"], "kind": "validation", "status": "PASS", "verdict": "PASS", "metrics": {}, "artifact_manifest": {}})
    assert [run["id"] for run in store.list_runs(experiment["id"])] == ["RUN-a", "RUN-b"]


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
