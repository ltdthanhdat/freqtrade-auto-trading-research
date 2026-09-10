from dataclasses import asdict
import json
from pathlib import Path
import subprocess

from scripts.validate_baseline import collect_identity


PAIRS = ("PLAY/USDT:USDT", "BIO/USDT:USDT")


def _setup(tmp_path: Path, *, verdict="PASS", dry_run=True):
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
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({**asdict(identity), "verdict": verdict}))
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
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_make_gate_accepts_only_matching_pass_identity(tmp_path):
    values = _setup(tmp_path)

    assert _make_gate(*values).returncode == 0


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
