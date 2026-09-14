from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_runtime.core import CycleStatus
from research_runtime.store import ResearchStore
from scripts.publish_research_report import main as publish_report_main
from scripts.reconcile_research_cycle import main as reconcile_main
from scripts.run_summary import write_run_summary


def test_run_summary_is_keyed_by_airflow_run_and_written_atomically(tmp_path: Path):
    path = write_run_summary(
        tmp_path,
        "scheduled__2026-09-14T07-15-00+00-00",
        {
            "status": "INCOMPLETE",
            "phase": "prepare_snapshot",
            "started_at": "2026-09-14T07:15:00Z",
            "completed_at": "2026-09-14T07:16:00Z",
            "reason": "missing 1m coverage",
        },
    )

    assert path == tmp_path / "runs" / "scheduled__2026-09-14T07-15-00-00-00" / "run-summary.json"
    payload = json.loads(path.read_text())
    assert payload["schema_version"] == 1
    assert payload["airflow_run_key"] == "scheduled__2026-09-14T07-15-00+00-00"
    assert not list(path.parent.glob("*.tmp"))


def test_run_summary_rejects_missing_terminal_fields(tmp_path: Path):
    with pytest.raises(ValueError, match="completed_at"):
        write_run_summary(
            tmp_path,
            "run-1",
            {"status": "FAILED", "phase": "research"},
        )


def test_run_summary_never_overwrites_another_run_identity(tmp_path: Path):
    write_run_summary(
        tmp_path,
        "run-1",
        {
            "status": "FAILED",
            "phase": "research",
            "started_at": "2026-09-14T07:00:00Z",
            "completed_at": "2026-09-14T07:01:00Z",
        },
    )

    with pytest.raises(ValueError, match="airflow_run_key"):
        write_run_summary(
            tmp_path,
            "run-1",
            {
                "airflow_run_key": "run-2",
                "status": "FAILED",
                "phase": "research",
                "started_at": "2026-09-14T07:00:00Z",
                "completed_at": "2026-09-14T07:01:00Z",
            },
        )


def test_recorded_validation_run_and_cycle_transition_have_completion_times(tmp_path: Path):
    store = ResearchStore(tmp_path / "research.sqlite")
    cycle_id = store.start_or_resume_cycle("2026-09-14T07:00:00Z")["cycle"]["id"]
    store.insert_hypothesis(
        cycle_id,
        {
            "id": "H-summary",
            "thesis": "thesis",
            "mechanism": "mechanism",
            "market_scope": "crypto",
            "required_data": ["OHLCV"],
            "falsifier": "negative",
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
            "id": "EXP-summary",
            "cycle_id": cycle_id,
            "hypothesis_id": "H-summary",
            "parent_strategy": "parent",
            "parent_sha256": "a",
            "changed_variable": "research",
            "config_path": "config",
            "config_sha256": "b",
            "pairs": [],
            "timeframes": ["30m"],
            "timeframe_detail": "1m",
            "snapshot_path": "snapshot",
            "snapshot_sha256": "c",
            "policy_path": "policy",
            "policy_sha256": "d",
            "strategy_name": "Candidate",
            "strategy_path": "src",
            "start_at": "2026-01-01T00:00:00Z",
            "end_at": "2026-02-01T00:00:00Z",
            "status": "PENDING",
        }
    )
    run, _ = store.record_validation_bundle(
        run={
            "id": "RUN-summary",
            "experiment_id": experiment["id"],
            "kind": "validation",
            "status": "PASS",
            "verdict": "PASS",
            "metrics": {},
            "artifact_manifest": {},
        },
        cycle_id=cycle_id,
        hypothesis_id="H-summary",
        target_state=None,
    )

    assert run["completed_at"] is not None
    cycle = store.set_cycle_status(cycle_id, CycleStatus.FAILED, "validation failed")
    assert cycle["completed_at"] is not None


def test_reconcile_cli_writes_a_precycle_terminal_summary(tmp_path: Path):
    artifacts = tmp_path / "artifacts"
    run_key = "manual__2026-09-15T07:15:00+00:00"

    exit_code = reconcile_main(
        [
            "--db",
            str(tmp_path / "research.sqlite"),
            "--artifacts",
            str(artifacts),
            "--run-key",
            run_key,
            "--observed-status",
            "FAILED",
            "--reason",
            "snapshot preparation failed",
        ]
    )

    assert exit_code == 0
    summary = json.loads(
        (artifacts / "runs" / "manual__2026-09-15T07-15-00-00-00" / "run-summary.json").read_text()
    )
    assert summary["status"] == "INCOMPLETE"
    assert summary["completed_at"]


def test_publish_report_reads_only_the_selected_summary(tmp_path: Path, capsys):
    write_run_summary(
        tmp_path,
        "run-1",
        {
            "status": "FAILED",
            "phase": "finalize_cycle",
            "started_at": "2026-09-15T07:00:00Z",
            "completed_at": "2026-09-15T07:01:00Z",
            "cycle_id": "C-1",
            "snapshot_sha256": "a" * 64,
        },
    )

    assert publish_report_main(["--artifacts", str(tmp_path), "--run-key", "run-1"]) == 0
    output = capsys.readouterr().out
    assert '"status":"FAILED"' in output
    assert '"cycle_id":"C-1"' in output
