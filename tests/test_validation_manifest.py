from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess

from scripts.validate_baseline import collect_identity
from research_runtime.core import HypothesisState
from research_runtime.store import ResearchStore
from scripts.validation_core import ValidationStateStore


PAIRS = ("PLAY/USDT:USDT", "BIO/USDT:USDT")


def _setup(tmp_path: Path, *, verdict="PASS", dry_run=True, bundle=True):
    tmp_path.mkdir(parents=True, exist_ok=True)
    strategy_path = tmp_path / "strategies"
    strategy_path.mkdir()
    strategy_file = strategy_path / "Strategy.py"
    strategy_file.write_text("class Strategy: pass\n")
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {"dry_run": dry_run, "exchange": {"pair_whitelist": list(PAIRS)}}
        )
    )
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "accepted_basket": list(PAIRS),
                "in_sample_days": 1,
                "oos_days": 1,
                "required_folds": 3,
                "min_positive_oos_folds": 2,
                "min_oos_trades": 6,
                "max_drawdown": 0.15,
                "stress_fee": 0.001,
                "slippage_per_side": 0.0005,
                "bootstrap_seed": 7,
                "bootstrap_samples": 20,
                "bootstrap_block": "2W",
            }
        )
    )
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    identity = collect_identity(
        config, strategy_file, snapshot, policy, "Strategy", strategy_path
    )
    state_db = tmp_path / "research.sqlite"
    store = ResearchStore(state_db)
    cycle = store.start_or_resume_cycle({"dataset": "fixture", "requested_timerange": "20250101-20250102", "now": "2026-01-01T00:00:00Z"})["cycle"]
    candidate = tmp_path / "candidate.py"
    candidate.write_text("class Strategy: pass\n")
    digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
    plan_json = json.dumps({"schema_version": 1}, sort_keys=True, separators=(",", ":"))
    plan_sha256 = hashlib.sha256(plan_json.encode()).hexdigest()
    hypothesis = store.insert_hypothesis(
        cycle["id"],
        {"id": "H-gate", "thesis": "x", "mechanism": "y", "market_scope": "x", "required_data": ["OHLCV"], "falsifier": "z", "scores": {"evidence_quality": 1, "reproducibility": 1, "ohlcv_transferability": 1, "novelty": 1, "falsifiability": 1}},
    )
    with store.connect() as connection:
        connection.execute(
            "UPDATE hypotheses SET plan_json = ?, plan_sha256 = ? WHERE id = ?",
            (plan_json, plan_sha256, hypothesis["id"]),
        )
    store.set_candidate(hypothesis["id"], candidate, digest)
    store.transition_hypothesis(hypothesis["id"], HypothesisState.QUEUED, "runtime", "queue")
    store.transition_hypothesis(hypothesis["id"], HypothesisState.IMPLEMENTING, "runtime", "implement")
    store.transition_hypothesis(hypothesis["id"], HypothesisState.TESTING, "runtime", "test")
    store.transition_hypothesis(hypothesis["id"], HypothesisState.NEEDS_REVIEW, "runtime", "validation")
    store.transition_hypothesis(hypothesis["id"], HypothesisState.APPROVED_FOR_DRY_RUN, "local_user", "approved")
    manifest = tmp_path / "manifest.json"
    partition = {"kind": "WFO_OOS", "start_at": "2025-01-01T00:00:00Z", "end_at": "2025-01-02T00:00:00Z"}
    manifest.write_text(json.dumps({
        **asdict(identity),
        "verdict": verdict,
        "cycle_id": cycle["id"],
        "hypothesis_id": "H-gate",
        "candidate_path": str(candidate),
        "candidate_sha256": digest,
        "plan_sha256": plan_sha256,
        "exit_coverage": 1.0,
        "risk_ledger": {"coverage": 1.0},
        "oos_consumption": {"status": "consumed"},
        "experiment_id": "EXP-gate",
        "run_id": "RUN-gate",
        "oos_partitions": [partition],
        "holdout": {"available": True},
        "walk_forward": {"enabled": True},
    }))
    if not bundle:
        return config, policy, strategy_path, manifest
    store.insert_experiment({
        "id": "EXP-gate",
        "cycle_id": cycle["id"],
        "hypothesis_id": "H-gate",
        "parent_strategy": "fixture",
        "parent_sha256": "a" * 64,
        "changed_variable": "complete-plan",
        "config_path": str(config),
        "config_sha256": identity.config_sha256,
        "pairs": list(PAIRS),
        "timeframes": ["1m", "30m", "1h"],
        "timeframe_detail": "1m",
        "snapshot_path": str(snapshot),
        "snapshot_sha256": identity.snapshot_sha256,
        "policy_path": str(policy),
        "policy_sha256": identity.policy_sha256,
        "strategy_name": "Strategy",
        "strategy_path": str(strategy_path),
        "start_at": "2025-01-01T00:00:00Z",
        "end_at": "2025-01-03T00:00:00Z",
        "status": "PASS",
        "oos_partitions": [partition],
    })
    manifest_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()
    store.record_run({
        "id": "RUN-gate",
        "experiment_id": "EXP-gate",
        "kind": "validation",
        "status": "NEEDS_REVIEW",
        "verdict": "PASS",
        "metrics": {},
        "artifact_manifest": {"manifest_path": str(manifest), "manifest_sha256": manifest_sha256},
    })
    store.consume_partitions(
        dataset="fixture",
        snapshot_sha256=identity.snapshot_sha256,
        cycle_id=cycle["id"],
        experiment_id="EXP-gate",
        run_id="RUN-gate",
        verdict="PASS",
        partitions=[partition],
    )
    return config, policy, strategy_path, manifest


def _make_gate(config, policy, strategy_path, manifest):
    override = manifest.parent / "test-override.mk"
    override.write_text("install:\n\t@:\nFREQ := true\n")
    return subprocess.run(
        [
            "make",
            "--no-print-directory",
            "-f",
            "Makefile",
            "-f",
            str(override),
            "dry-run",
            f"CONFIG={config}",
            f"VALIDATION_POLICY={policy}",
            "STRATEGY=Strategy",
            f"SPATH={strategy_path}",
        f"VALIDATION_MANIFEST={manifest}",
            f"RESEARCH_DB={manifest.parent / 'research.sqlite'}",
            f"VALIDATION_STATE_DB={manifest.parent / 'validation-state.sqlite'}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_validate_manifest_requires_linked_pass_bundle(tmp_path):
    config, policy, strategy_path, manifest = _setup(tmp_path, bundle=False)
    errors = __import__("scripts.validate_manifest", fromlist=["validate_manifest"]).validate_manifest(
        manifest,
        config,
        policy,
        "Strategy",
        strategy_path,
        research_db=manifest.parent / "research.sqlite",
    )
    assert any("linked PASS" in error or "run" in error for error in errors)


def test_make_gate_accepts_only_matching_pass_identity(tmp_path):
    values = _setup(tmp_path)

    assert _make_gate(*values).returncode == 0


def test_make_gate_blocks_incomplete_complete_plan_evidence(tmp_path):
    config, policy, strategy_path, manifest = _setup(tmp_path)
    values = json.loads(manifest.read_text())
    values.pop("exit_coverage")
    values["risk_ledger"] = {"coverage": 0.5}
    values["oos_consumption"] = {"status": "incomplete"}
    manifest.write_text(json.dumps(values))

    errors = __import__("scripts.validate_manifest", fromlist=["validate_manifest"]).validate_manifest(
        manifest, config, policy, "Strategy", strategy_path
    )

    assert any("exit coverage" in error for error in errors)
    assert any("risk-ledger coverage" in error for error in errors)
    assert any("OOS consumption" in error for error in errors)


def test_make_gate_blocks_missing_warn_fail_changed_identity_and_live_config(tmp_path):
    config, policy, strategy_path, manifest = _setup(tmp_path)
    missing = tmp_path / "missing.json"
    assert _make_gate(config, policy, strategy_path, missing).returncode != 0

    for verdict in ("WARN", "FAIL"):
        manifest.write_text(json.dumps({"verdict": verdict}))
        assert _make_gate(config, policy, strategy_path, manifest).returncode != 0

    config, policy, strategy_path, manifest = _setup(tmp_path / "changed")
    config.write_text(config.read_text().replace("BIO/USDT:USDT", "SPACE/USDT:USDT"))
    assert _make_gate(config, policy, strategy_path, manifest).returncode != 0

    config, policy, strategy_path, manifest = _setup(tmp_path / "live", dry_run=False)
    result = _make_gate(config, policy, strategy_path, manifest)
    assert result.returncode != 0
    assert "dry_run=true" in result.stderr


def test_make_gate_blocks_freqtrade_environment_override_to_live(tmp_path, monkeypatch):
    config, policy, strategy_path, manifest = _setup(tmp_path)
    monkeypatch.setenv("FREQTRADE__DRY_RUN", "false")

    result = _make_gate(config, policy, strategy_path, manifest)

    assert result.returncode != 0
    assert "dry_run=true" in result.stderr


def test_make_gate_blocks_paused_decay_state(tmp_path):
    config, policy, strategy_path, manifest = _setup(tmp_path)
    ValidationStateStore(manifest.parent / "validation-state.sqlite").transition(
        "global", "PAUSED", "decay", {}, None, "r1"
    )
    result = _make_gate(config, policy, strategy_path, manifest)
    assert result.returncode != 0
    assert "runtime state is PAUSED" in result.stderr


def test_active_validation_paths_use_sqlite_artifacts_not_legacy_research():
    makefile = Path("Makefile").read_text()
    readme = Path("README.md").read_text()
    assert "APPROVED_IDENTITY ?= config/approved-baseline-identity.json" in makefile
    assert "RESEARCH_RUNS_DIR ?= user_data/research-artifacts/validation" in makefile
    assert "--runs-dir $(RESEARCH_RUNS_DIR)" in makefile
    assert "research-cycle: research-data" in makefile
    assert "scripts.prepare_research_data" in makefile
    assert ".research/smc_fvg_pinbar/runs" not in makefile
    assert "config/approved-baseline-identity.json" in readme
    assert "user_data/research-artifacts/validation" in readme
