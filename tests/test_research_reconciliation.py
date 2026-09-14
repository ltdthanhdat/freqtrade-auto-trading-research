from __future__ import annotations

import hashlib
import json
from pathlib import Path

from research_runtime.core import CycleStatus
from research_runtime.store import ResearchStore


def _experiment(store: ResearchStore, cycle_id: str, tmp_path: Path) -> str:
    store.insert_hypothesis(
        cycle_id,
        {
            "id": f"H-{cycle_id}",
            "thesis": "thesis",
            "mechanism": f"mechanism-{cycle_id}",
            "market_scope": "crypto",
            "required_data": ["OHLCV"],
            "falsifier": "negative result",
            "scores": {
                "evidence_quality": 1,
                "reproducibility": 1,
                "ohlcv_transferability": 1,
                "novelty": 1,
                "falsifiability": 1,
            },
        },
    )
    experiment = store.insert_experiment(
        {
            "id": f"EXP-{cycle_id}",
            "cycle_id": cycle_id,
            "hypothesis_id": f"H-{cycle_id}",
            "parent_strategy": "parent",
            "parent_sha256": "a" * 64,
            "changed_variable": "research",
            "config_path": "config.json",
            "config_sha256": "b" * 64,
            "pairs": ["BTC/USDT:USDT"],
            "timeframes": ["30m", "1h", "1m"],
            "timeframe_detail": "1m",
            "snapshot_path": "snapshot",
            "snapshot_sha256": "c" * 64,
            "policy_path": "policy.json",
            "policy_sha256": "d" * 64,
            "strategy_name": "Candidate",
            "strategy_path": str(tmp_path),
            "start_at": "2026-01-01T00:00:00Z",
            "end_at": "2026-02-01T00:00:00Z",
            "status": "PENDING",
        }
    )
    return experiment["id"]


def _artifact_manifest(tmp_path: Path, verdict: str) -> dict[str, object]:
    manifest = tmp_path / f"{verdict.lower()}-manifest.json"
    report = tmp_path / f"{verdict.lower()}-report.md"
    manifest.write_text(json.dumps({"verdict": verdict}), encoding="utf-8")
    report.write_text(f"verdict={verdict}\n", encoding="utf-8")
    return {
        "manifest_path": str(manifest),
        "report_path": str(report),
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
    }


def _record_run(store: ResearchStore, experiment_id: str, verdict: str, artifacts: dict[str, object]) -> None:
    store.record_run(
        {
            "id": f"RUN-{experiment_id}",
            "experiment_id": experiment_id,
            "kind": "validation",
            "status": "NEEDS_REVIEW" if verdict == "PASS" else "REJECTED",
            "verdict": verdict,
            "metrics": {},
            "artifact_manifest": artifacts,
            "created_at": "2026-09-14T07:10:00Z",
            "completed_at": "2026-09-14T07:11:00Z",
        }
    )


def test_reconciliation_maps_verified_pass_to_review_and_is_idempotent(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite")
    cycle_id = store.start_or_resume_cycle("2026-09-14T07:00:00Z")["cycle"]["id"]
    experiment_id = _experiment(store, cycle_id, tmp_path)
    _record_run(store, experiment_id, "PASS", _artifact_manifest(tmp_path, "PASS"))

    result = store.reconcile_cycle(
        cycle_id,
        observed_status="SUCCEEDED",
        reason="container completed",
        now="2026-09-14T07:12:00Z",
    )

    assert result["action"] == "RECONCILED"
    assert result["cycle"]["status"] == CycleStatus.NEEDS_REVIEW
    assert result["cycle"]["completed_at"] is not None
    event_count = len(store.events(cycle_id))

    replay = store.reconcile_cycle(
        cycle_id,
        observed_status="SUCCEEDED",
        reason="container completed again",
        now="2026-09-14T07:13:00Z",
    )

    assert replay["action"] == "NO_OP"
    assert len(store.events(cycle_id)) == event_count


def test_reconciliation_maps_verified_fail_and_warn(tmp_path: Path):
    for verdict, expected in (("FAIL", CycleStatus.FAILED), ("WARN", CycleStatus.INCOMPLETE)):
        store = ResearchStore(tmp_path / f"{verdict}.sqlite")
        cycle_id = store.start_or_resume_cycle("2026-09-14T07:00:00Z")["cycle"]["id"]
        experiment_id = _experiment(store, cycle_id, tmp_path)
        _record_run(store, experiment_id, verdict, _artifact_manifest(tmp_path, verdict))

        result = store.reconcile_cycle(
            cycle_id,
            observed_status="SUCCEEDED",
            reason=f"{verdict} result",
            now="2026-09-14T07:12:00Z",
        )

        assert result["action"] == "RECONCILED"
        assert result["cycle"]["status"] == expected


def test_reconciliation_fails_closed_for_unverified_result_and_stale_run(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite")
    cycle_id = store.start_or_resume_cycle("2026-09-14T07:00:00Z")["cycle"]["id"]
    experiment_id = _experiment(store, cycle_id, tmp_path)
    _record_run(store, experiment_id, "PASS", {"manifest_path": "missing", "report_path": "missing"})

    result = store.reconcile_cycle(
        cycle_id,
        observed_status="SUCCEEDED",
        reason="missing artifacts",
        now="2026-09-14T07:12:00Z",
    )
    assert result["action"] == "RECONCILED"
    assert result["cycle"]["status"] == CycleStatus.INCOMPLETE

    stale_store = ResearchStore(tmp_path / "stale.sqlite")
    stale_id = stale_store.start_or_resume_cycle("2026-09-14T07:00:00Z")["cycle"]["id"]
    stale = stale_store.reconcile_cycle(
        stale_id,
        observed_status="TIMEOUT",
        reason="container timed out",
        now="2026-09-14T08:00:00Z",
    )
    assert stale["action"] == "RECONCILED"
    assert stale["cycle"]["status"] == CycleStatus.INCOMPLETE


def test_watchdog_with_an_active_lease_stays_running(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite", lease_seconds=3600)
    cycle_id = store.start_or_resume_cycle(
        {"now": "2026-09-14T07:00:00Z", "lease_owner": "dag-a"}
    )["cycle"]["id"]

    result = store.reconcile_cycle(
        cycle_id,
        observed_status="WATCHDOG",
        reason="container still running",
        lease_owner="dag-a",
        now="2026-09-14T07:10:00Z",
    )

    assert result["action"] == "STILL_RUNNING"
    assert result["cycle"]["status"] == CycleStatus.RUNNING
