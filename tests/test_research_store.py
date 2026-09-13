from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3

import pytest

from research_runtime.core import CycleStatus, HypothesisState
from research_runtime.store import ResearchStore


def test_store_creates_v3_tables_and_identity_columns(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    with store.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert {
            "cycles",
            "sources",
            "hypotheses",
            "hypothesis_sources",
            "experiments",
            "runs",
            "state_events",
            "validation_windows",
            "cycle_sources",
            "source_assessments",
            "legacy_evidence_quarantine",
            "comparison_cohorts",
            "comparison_cohort_members",
            "oos_partition_consumptions",
        } <= tables
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        cycle_columns = {row[1] for row in connection.execute("PRAGMA table_info(cycles)")}
        assert {
            "dataset",
            "requested_timerange",
            "holdout_start",
            "holdout_end",
            "search_cohort",
            "ranking_sealed_at",
            "ranking_json",
            "ranking_sha256",
        } <= cycle_columns
        hypothesis_columns = {row[1] for row in connection.execute("PRAGMA table_info(hypotheses)")}
        assert {"approval_blocked_reason", "family_id", "plan_json", "plan_sha256"} <= hypothesis_columns
        experiment_columns = {row[1] for row in connection.execute("PRAGMA table_info(experiments)")}
        assert {"oos_partitions_json", "owner_id"} <= experiment_columns
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


def test_cross_cycle_source_reuse_adds_cycle_membership(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    first_cycle = store.start_or_resume_cycle({"now": "2026-09-11T08:00:00Z", "dataset": "a"})["cycle"]["id"]
    store.set_cycle_status(first_cycle, CycleStatus.COMPLETED, "finish")
    second_cycle = store.start_or_resume_cycle({"now": "2026-09-11T08:01:00Z", "dataset": "b"})["cycle"]["id"]
    source = {
        "provider": "fixture",
        "canonical_url": "https://example.test/reused",
        "title": "reused",
        "excerpt": "evidence",
        "retrieved_at": "2026-09-11T08:00:00Z",
        "fingerprint": "reused-source",
        "metadata": {"collector": "fixture"},
    }

    first = store.insert_source(first_cycle, source)
    duplicate = store.insert_source(second_cycle, {**source, "retrieved_at": "2026-09-11T08:01:00Z"})

    assert first["inserted"] is True
    assert duplicate["inserted"] is False
    assert duplicate["id"] == first["id"]
    with store.connect() as connection:
        memberships = connection.execute(
            "SELECT cycle_id FROM cycle_sources WHERE source_id = ? ORDER BY cycle_id",
            (first["id"],),
        ).fetchall()
        assert [row[0] for row in memberships] == sorted([first_cycle, second_cycle])
        counts = connection.execute(
            "SELECT id, source_count FROM cycles WHERE id IN (?, ?) ORDER BY id",
            (first_cycle, second_cycle),
        ).fetchall()
        assert [row[1] for row in counts] == [1, 1]


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


def test_source_facts_and_assessments_are_immutable(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    cycle_id = store.start_or_resume_cycle("2026-09-11T08:00:00Z")["cycle"]["id"]
    source_id = store.insert_source(
        cycle_id,
        {
            "provider": "fixture",
            "canonical_url": "https://example.test/immutable",
            "title": "immutable",
            "excerpt": "evidence",
            "retrieved_at": "2026-09-11T08:00:00Z",
            "fingerprint": "immutable-source",
            "metadata": {"full_text_available": False},
        },
    )["id"]
    with pytest.raises(sqlite3.IntegrityError):
        with store.connect() as connection:
            connection.execute("UPDATE sources SET title = 'forged' WHERE id = ?", (source_id,))
    with pytest.raises(sqlite3.IntegrityError):
        with store.connect() as connection:
            connection.execute("DELETE FROM sources WHERE id = ?", (source_id,))

    store.insert_source_assessment(
        cycle_id,
        source_id,
        {"relevance": "direct", "asset": "crypto", "timeframe": "30m", "mechanism": "continuation"},
        actor="runtime",
    )
    with pytest.raises(sqlite3.IntegrityError):
        with store.connect() as connection:
            connection.execute("DELETE FROM source_assessments")
    with pytest.raises(sqlite3.IntegrityError):
        with store.connect() as connection:
            connection.execute("UPDATE source_assessments SET relevance = 'indirect'")


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


def make_v2_integrity_fixture(path):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE cycles (
          id TEXT PRIMARY KEY, status TEXT NOT NULL, stage TEXT NOT NULL,
          source_count INTEGER NOT NULL DEFAULT 0, hypothesis_count INTEGER NOT NULL DEFAULT 0,
          candidate_count INTEGER NOT NULL DEFAULT 0, lease_until TEXT, created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL, dataset TEXT, requested_timerange TEXT, policy_sha256 TEXT,
          search_cohort TEXT, holdout_start TEXT, holdout_end TEXT
        );
        CREATE TABLE sources (
          id TEXT PRIMARY KEY, cycle_id TEXT NOT NULL REFERENCES cycles(id), provider TEXT NOT NULL,
          canonical_url TEXT, doi TEXT, title TEXT NOT NULL, excerpt TEXT NOT NULL, license TEXT,
          retrieved_at TEXT NOT NULL, fingerprint TEXT NOT NULL UNIQUE, metadata_json TEXT NOT NULL,
          UNIQUE(provider, canonical_url), UNIQUE(doi)
        );
        CREATE TABLE hypotheses (
          id TEXT PRIMARY KEY, cycle_id TEXT NOT NULL REFERENCES cycles(id), thesis TEXT NOT NULL,
          mechanism TEXT NOT NULL, market_scope TEXT NOT NULL, required_data_json TEXT NOT NULL,
          falsifier TEXT NOT NULL, evidence_quality INTEGER NOT NULL, reproducibility INTEGER NOT NULL,
          ohlcv_transferability INTEGER NOT NULL, novelty INTEGER NOT NULL, falsifiability INTEGER NOT NULL,
          total_score INTEGER NOT NULL, state TEXT NOT NULL, candidate_path TEXT,
          candidate_sha256 TEXT, metadata_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE hypothesis_sources (
          hypothesis_id TEXT NOT NULL REFERENCES hypotheses(id), source_id TEXT NOT NULL REFERENCES sources(id),
          stance TEXT NOT NULL, note TEXT NOT NULL, PRIMARY KEY(hypothesis_id, source_id, stance)
        );
        CREATE TABLE experiments (
          id TEXT PRIMARY KEY, cycle_id TEXT NOT NULL REFERENCES cycles(id), hypothesis_id TEXT NOT NULL REFERENCES hypotheses(id),
          parent_strategy TEXT NOT NULL, parent_sha256 TEXT NOT NULL, changed_variable TEXT NOT NULL,
          config_path TEXT NOT NULL, config_sha256 TEXT NOT NULL, pairs_json TEXT NOT NULL, timeframes_json TEXT NOT NULL,
          timeframe_detail TEXT NOT NULL, snapshot_path TEXT NOT NULL, snapshot_sha256 TEXT NOT NULL,
          policy_path TEXT NOT NULL, policy_sha256 TEXT NOT NULL, strategy_name TEXT NOT NULL, strategy_path TEXT NOT NULL,
          start_at TEXT NOT NULL, end_at TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE runs (
          id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiments(id), kind TEXT NOT NULL,
          status TEXT NOT NULL, verdict TEXT, metrics_json TEXT NOT NULL, artifact_manifest_json TEXT NOT NULL,
          error_code TEXT, created_at TEXT NOT NULL, completed_at TEXT
        );
        CREATE TABLE state_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
          from_state TEXT, to_state TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL,
          cycle_id TEXT NOT NULL REFERENCES cycles(id), run_id TEXT REFERENCES runs(id),
          payload_json TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE validation_windows (
          id INTEGER PRIMARY KEY AUTOINCREMENT, cycle_id TEXT NOT NULL REFERENCES cycles(id),
          dataset TEXT NOT NULL, requested_timerange TEXT NOT NULL, policy_sha256 TEXT NOT NULL,
          verdict TEXT NOT NULL, created_at TEXT NOT NULL,
          UNIQUE(dataset, requested_timerange, policy_sha256, cycle_id)
        );
        PRAGMA user_version = 2;
        """
    )
    cycle_values = ("C-v2", "COMPLETED", "DONE", 3, 1, 0, None, "2026-09-11T08:00:00Z", "2026-09-11T08:00:00Z", "dataset", "20260101-20260901", "policy", "cohort", None, None)
    connection.execute(
        "INSERT INTO cycles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", cycle_values
    )
    connection.execute(
        "INSERT INTO cycles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("C-other", "COMPLETED", "DONE", 1, 0, 0, None, "2026-09-11T08:00:00Z", "2026-09-11T08:00:00Z", "dataset", "20260101-20260901", "policy", "cohort", None, None),
    )
    sources = [
        ("S-one", "C-v2", "fixture", "https://example.test/one", None, "one", "one", None, "2026-09-11T08:00:00Z", "fp-one", "{}"),
        ("S-two", "C-v2", "fixture", "https://example.test/two", None, "two", "two", None, "2026-09-11T08:00:00Z", "fp-two", "{}"),
        ("S-other", "C-other", "fixture", "https://example.test/other", None, "other", "other", None, "2026-09-11T08:00:00Z", "fp-other", "{}"),
    ]
    connection.executemany("INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", sources)
    scores = (20, 20, 15, 5, 10, 70)
    connection.execute(
        "INSERT INTO hypotheses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("H-v2", "C-v2", "thesis", "mechanism", "crypto", '["OHLCV"]', "falsifier", *scores, "SCORED", None, None, "{}", "2026-09-11T08:00:00Z", "2026-09-11T08:00:00Z"),
    )
    connection.executemany(
        "INSERT INTO hypothesis_sources VALUES (?, ?, ?, ?)",
        [("H-v2", "S-one", "SUPPORT", "overlap support"), ("H-v2", "S-one", "CONTRADICT", "overlap contradiction"), ("H-v2", "S-two", "SUPPORT", "same cycle"), ("H-v2", "S-other", "SUPPORT", "cross cycle")],
    )
    connection.commit()
    connection.close()


def test_v2_migration_preserves_rows_and_quarantines_unsafe_links(tmp_path):
    path = tmp_path / "v2.sqlite"
    make_v2_integrity_fixture(path)

    store = ResearchStore(path)

    with store.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM hypotheses").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM cycle_sources").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM hypothesis_sources").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM legacy_evidence_quarantine").fetchone()[0] == 3
        blocked = connection.execute(
            "SELECT approval_blocked_reason FROM hypotheses WHERE id = 'H-v2'"
        ).fetchone()[0]
        assert blocked
        quarantined = connection.execute(
            "SELECT original_row_json, original_sha256, reason FROM legacy_evidence_quarantine ORDER BY id"
        ).fetchall()
        assert all(row[0] and len(row[1]) == 64 and row[2] for row in quarantined)
    assert store.integrity_report() == {"integrity_check": "ok", "foreign_key_errors": []}


def test_ranking_seal_is_deterministic_and_blocks_mutation(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    cycle_id = store.start_or_resume_cycle("2026-09-11T08:00:00Z")["cycle"]["id"]
    for identifier, score in (("H-low", 40), ("H-high", 60), ("H-mid", 50)):
        store.insert_hypothesis(
            cycle_id,
            {
                "id": identifier,
                "thesis": identifier,
                "mechanism": identifier,
                "market_scope": "crypto",
                "required_data": ["OHLCV"],
                "falsifier": "negative OOS",
                "scores": {
                    "evidence_quality": score - 35,
                    "reproducibility": 20,
                    "ohlcv_transferability": 15,
                    "novelty": 5,
                    "falsifiability": 10,
                },
            },
        )

    first = store.seal_hypothesis_ranking(cycle_id)
    replay = store.seal_hypothesis_ranking(cycle_id)

    assert first == replay
    assert [item["hypothesis_id"] for item in first["ranking"]] == ["H-high", "H-mid", "H-low"]
    assert all(len(item["evidence_sha256"]) == 64 for item in first["ranking"])
    assert len(first["ranking_sha256"]) == 64
    assert store.get_cycle(cycle_id)["stage"] == "RANKED"

    with pytest.raises(ValueError, match="ranking sealed"):
        store.insert_hypothesis(
            cycle_id,
            {
                "id": "H-after",
                "thesis": "after",
                "mechanism": "after",
                "market_scope": "crypto",
                "required_data": ["OHLCV"],
                "falsifier": "negative",
                "scores": {"evidence_quality": 1, "reproducibility": 1, "ohlcv_transferability": 1, "novelty": 1, "falsifiability": 1},
            },
        )
    with pytest.raises(sqlite3.IntegrityError):
        with store.connect() as connection:
            connection.execute("UPDATE hypotheses SET total_score = 1 WHERE id = 'H-high'")
    with pytest.raises(ValueError, match="ranking sealed"):
        store.insert_source(
            cycle_id,
            {"provider": "fixture", "canonical_url": "https://example.test/after", "title": "after", "excerpt": "e", "retrieved_at": "2026-09-11T08:00:00Z", "fingerprint": "after-source", "metadata": {}},
        )


def test_sealed_hypothesis_source_links_are_immutable(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    cycle_id = store.start_or_resume_cycle("2026-09-11T08:00:00Z")["cycle"]["id"]
    source_ids = [
        store.insert_source(
            cycle_id,
            {"provider": "fixture", "canonical_url": f"https://example.test/link-{index}", "title": "link", "excerpt": "e", "retrieved_at": "2026-09-11T08:00:00Z", "fingerprint": f"link-{index}", "metadata": {}},
        )["id"]
        for index in range(2)
    ]
    store.insert_hypothesis(
        cycle_id,
        {"id": "H-links", "thesis": "links", "mechanism": "links", "market_scope": "crypto", "required_data": ["OHLCV"], "falsifier": "negative", "scores": {"evidence_quality": 1, "reproducibility": 1, "ohlcv_transferability": 1, "novelty": 1, "falsifiability": 1}},
    )
    store.add_hypothesis_source("H-links", source_ids[0], "SUPPORT", "before")
    store.seal_hypothesis_ranking(cycle_id)

    with pytest.raises(ValueError, match="ranking sealed"):
        store.add_hypothesis_source("H-links", source_ids[1], "SUPPORT", "after")
    with pytest.raises(sqlite3.IntegrityError):
        with store.connect() as connection:
            connection.execute(
                "INSERT INTO hypothesis_sources (hypothesis_id, source_id, stance, note, evidence_json) VALUES (?, ?, 'SUPPORT', 'after', '{}')",
                ("H-links", source_ids[1]),
            )


def _cohort_member(store, tmp_path, index):
    cycle_id = f"C-cohort-{index}"
    store.ensure_cycle(cycle_id, status=CycleStatus.COMPLETED, now=f"2026-09-11T08:0{index}:00Z")
    plan_json = json.dumps({"schema_version": 1}, sort_keys=True, separators=(",", ":"))
    plan_sha256 = hashlib.sha256(plan_json.encode()).hexdigest()
    hypothesis = store.insert_hypothesis(
        cycle_id,
        {
            "id": f"H-cohort-{index}",
            "thesis": "frozen",
            "mechanism": f"family-{index}",
            "market_scope": "crypto",
            "required_data": ["OHLCV"],
            "falsifier": "negative OOS",
            "scores": {"evidence_quality": 1, "reproducibility": 1, "ohlcv_transferability": 1, "novelty": 1, "falsifiability": 1},
        },
    )
    candidate = tmp_path / f"candidate-{index}.py"
    candidate.write_text(f"class Candidate{index}: pass\n")
    candidate_sha256 = hashlib.sha256(candidate.read_bytes()).hexdigest()
    with store.connect() as connection:
        connection.execute(
            "UPDATE hypotheses SET plan_json = ?, plan_sha256 = ? WHERE id = ?",
            (plan_json, plan_sha256, hypothesis["id"]),
        )
    store.set_candidate(hypothesis["id"], candidate, candidate_sha256)
    return {
        "cycle_id": cycle_id,
        "hypothesis_id": hypothesis["id"],
        "candidate_sha256": candidate_sha256,
        "plan_sha256": plan_sha256,
        "dependency_sha256": "d" * 64,
    }


def _cohort_payload(members):
    return {
        "id": "COHORT-1",
        "dataset": "snapshot",
        "config_sha256": "c" * 64,
        "policy_sha256": "p" * 64,
        "snapshot_sha256": "s" * 64,
        "comparison_start_at": "2026-01-01T00:00:00Z",
        "comparison_end_at": "2026-02-01T00:00:00Z",
        "holdout_start_at": "2026-02-01T00:00:00Z",
        "holdout_end_at": "2026-03-01T00:00:00Z",
        "selection_rule": {"metric": "stressed_net_profit", "tie_breaker": "drawdown"},
        "members": members,
    }


def test_evaluation_cohort_seals_exactly_three_frozen_members(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    members = [_cohort_member(store, tmp_path, index) for index in range(3)]
    with pytest.raises(ValueError, match="exactly three"):
        store.create_evaluation_cohort(_cohort_payload(members[:2]))

    cohort = store.create_evaluation_cohort(_cohort_payload(members))
    assert cohort["id"] == "COHORT-1"
    assert cohort["status"] == "SEALED"
    assert len(cohort["members"]) == 3
    assert len(cohort["manifest_sha256"]) == 64
    assert store.create_evaluation_cohort(_cohort_payload(members)) == cohort
    store.select_evaluation_cohort("COHORT-1", members[0]["hypothesis_id"])
    holdout = {"kind": "HOLDOUT", "start_at": "2026-02-01T00:00:00Z", "end_at": "2026-03-01T00:00:00Z"}
    assert store.authorize_cohort_partition(members[0]["hypothesis_id"], holdout, "s" * 64) == "COHORT-1"
    with pytest.raises(ValueError, match="selected cohort member"):
        store.authorize_cohort_partition(members[1]["hypothesis_id"], holdout, "s" * 64)


def test_evaluation_cohort_rejects_mutated_member_identity(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    members = [_cohort_member(store, tmp_path, index) for index in range(3)]
    store.create_evaluation_cohort(_cohort_payload(members))
    with store.connect() as connection:
        connection.execute(
            "UPDATE hypotheses SET candidate_sha256 = ? WHERE id = ?",
            ("x" * 64, members[0]["hypothesis_id"]),
        )
    with pytest.raises(ValueError, match="cohort identity"):
        store.validate_evaluation_cohort("COHORT-1")


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
