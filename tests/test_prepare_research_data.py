import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import scripts.prepare_research_data as module


def _policy(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "accepted_basket": ["A/USDT:USDT"],
                "in_sample_days": 1,
                "oos_days": 1,
                "required_folds": 3,
                "min_positive_oos_folds": 2,
                "min_oos_trades": 1,
                "max_drawdown": 0.15,
                "stress_fee": 0.001,
                "slippage_per_side": 0.0005,
                "bootstrap_seed": 7,
                "bootstrap_samples": 20,
                "bootstrap_block": "2W",
            }
        )
    )


def test_prepare_passes_explicit_data_root_to_downloader_and_inspection(tmp_path, monkeypatch):
    policy = tmp_path / "policy.json"
    _policy(policy)
    calls = []
    monkeypatch.setattr(
        module,
        "inspect_snapshot",
        lambda datadir, *_args: (
            {"common_interval": {"start": "2025-01-01T00:00:00Z", "end_exclusive": "2025-01-10T00:00:00Z"}},
            [],
            [],
        ),
    )
    monkeypatch.setattr(
        module,
        "build_oos_folds",
        lambda *_args: [
            SimpleNamespace(
                oos_start=pd.Timestamp("2025-01-02T00:00:00Z"),
                oos_end=pd.Timestamp("2025-01-03T00:00:00Z"),
            )
        ]
        * 3,
    )
    monkeypatch.setattr(module.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)))

    result = module.prepare(
        config=tmp_path / "config.json",
        policy_path=policy,
        dataset="snapshots/run-1",
        timerange="20250101-20250110",
        data_root=tmp_path / "data",
    )

    assert result["datadir"] == str(tmp_path / "data" / "snapshots" / "run-1")
    assert calls[0][0][calls[0][0].index("--datadir") + 1] == str(
        tmp_path / "data" / ".staging" / "snapshots" / "run-1"
    )


def _write_policy(path: Path, *, required_folds: int = 3) -> None:
    path.write_text(
        json.dumps(
            {
                "accepted_basket": ["A/USDT:USDT"],
                "in_sample_days": 1,
                "oos_days": 1,
                "required_folds": required_folds,
                "min_positive_oos_folds": 1,
                "min_oos_trades": 1,
                "max_drawdown": 0.15,
                "stress_fee": 0.001,
                "slippage_per_side": 0.0005,
                "bootstrap_seed": 7,
                "bootstrap_samples": 20,
                "bootstrap_block": "2W",
            }
        ),
        encoding="utf-8",
    )


def _seed_files(datadir: Path, *, start: str = "2025-01-01", end: str = "2025-01-10", missing=None):
    futures = datadir / "futures"
    futures.mkdir(parents=True, exist_ok=True)
    for timeframe, frequency in (("30m", "30min"), ("1h", "1h"), ("1m", "1min")):
        if missing == timeframe:
            continue
        frame = pd.DataFrame(
            {
                "date": pd.date_range(start, end, freq=frequency, tz="UTC"),
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.0,
                "volume": 1.0,
            }
        )
        frame.to_feather(futures / f"A_USDT_USDT-{timeframe}-futures.feather")


def _seed_from_command(command, *, missing=None, start="2025-01-01", end="2025-01-10"):
    _seed_files(Path(command[command.index("--datadir") + 1]), missing=missing, start=start, end=end)


def test_prepare_missing_timeframe_never_publishes_final_snapshot(tmp_path, monkeypatch):
    policy = tmp_path / "policy.json"
    _write_policy(policy)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda command, **_kwargs: _seed_from_command(command, missing="1m"),
    )

    with pytest.raises(RuntimeError, match="snapshot validation failed"):
        module.prepare(
            config=tmp_path / "config.json",
            policy_path=policy,
            dataset="snapshots/run-1",
            timerange="20250101-20250110",
            data_root=tmp_path / "data",
            staging_root=tmp_path / "staging",
        )

    assert not (tmp_path / "data" / "snapshots" / "run-1").exists()


def test_prepare_short_common_history_never_publishes_final_snapshot(tmp_path, monkeypatch):
    policy = tmp_path / "policy.json"
    _write_policy(policy)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda command, **_kwargs: _seed_from_command(command, end="2025-01-03"),
    )

    with pytest.raises(RuntimeError):
        module.prepare(
            config=tmp_path / "config.json",
            policy_path=policy,
            dataset="snapshots/run-1",
            timerange="20250101-20250110",
            data_root=tmp_path / "data",
            staging_root=tmp_path / "staging",
        )

    assert not (tmp_path / "data" / "snapshots" / "run-1").exists()


def test_prepare_seals_valid_snapshot_and_reuses_matching_identity(tmp_path, monkeypatch):
    policy = tmp_path / "policy.json"
    _write_policy(policy)
    calls = []
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda command, **_kwargs: calls.append(command) or _seed_from_command(command),
    )
    manifest = tmp_path / "artifacts" / "snapshot-readiness.json"
    kwargs = {
        "config": tmp_path / "config.json",
        "policy_path": policy,
        "dataset": "snapshots/run-1",
        "timerange": "20250101-20250110",
        "data_root": tmp_path / "data",
        "staging_root": tmp_path / "staging",
        "manifest_path": manifest,
        "snapshot_id": "snapshots/run-1",
    }

    first = module.prepare(**kwargs)
    assert first["status"] == "READY"
    assert first["reused"] is False
    assert len(first["folds"]) >= 3
    assert len(first["snapshot_sha256"]) == 64
    manifest_payload = json.loads(manifest.read_text())
    assert manifest_payload["status"] == "SEALED"
    assert manifest_payload["snapshot_sha256"] == first["snapshot_sha256"]
    first_call_count = len(calls)

    second = module.prepare(**kwargs)
    assert second["reused"] is True
    assert len(calls) == first_call_count


def test_prepare_failure_writes_terminal_run_summary(tmp_path, monkeypatch):
    policy = tmp_path / "policy.json"
    _write_policy(policy)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda command, **_kwargs: _seed_from_command(command, missing="1m"),
    )

    with pytest.raises(RuntimeError):
        module.prepare(
            config=tmp_path / "config.json",
            policy_path=policy,
            dataset="snapshots/run-1",
            timerange="20250101-20250110",
            data_root=tmp_path / "data",
            staging_root=tmp_path / "staging",
            run_key="scheduled__run-1",
            summary_root=tmp_path / "artifacts",
        )

    summary = json.loads(
        (tmp_path / "artifacts" / "runs" / "scheduled__run-1" / "run-summary.json").read_text()
    )
    assert summary["status"] == "INCOMPLETE"
    assert summary["phase"] == "prepare_snapshot"
    assert summary["completed_at"]


def test_prepare_rejects_mismatched_existing_sealed_identity(tmp_path, monkeypatch):
    policy = tmp_path / "policy.json"
    _write_policy(policy)
    monkeypatch.setattr(module.subprocess, "run", lambda command, **_kwargs: _seed_from_command(command))
    manifest = tmp_path / "artifacts" / "snapshot-readiness.json"
    kwargs = {
        "config": tmp_path / "config.json",
        "policy_path": policy,
        "dataset": "snapshots/run-1",
        "timerange": "20250101-20250110",
        "data_root": tmp_path / "data",
        "staging_root": tmp_path / "staging",
        "manifest_path": manifest,
        "snapshot_id": "snapshots/run-1",
    }
    module.prepare(**kwargs)

    with pytest.raises(RuntimeError, match="sealed snapshot identity"):
        module.prepare(**{**kwargs, "timerange": "20250102-20250110"})


def test_prepare_reuses_ready_snapshot_and_requires_policy_folds(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "ROOT", tmp_path)
    policy = tmp_path / "policy.json"
    _policy(policy)
    futures = tmp_path / "user_data/data/snapshots/test/futures"
    futures.mkdir(parents=True)
    for timeframe, frequency in (("1m", "1min"), ("30m", "30min"), ("1h", "1h")):
        frame = pd.DataFrame(
            {
                "date": pd.date_range("2025-01-01", "2025-01-10", freq=frequency, tz="UTC"),
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.0,
                "volume": 1.0,
            }
        )
        frame.to_feather(futures / f"A_USDT_USDT-{timeframe}-futures.feather")
    manifest = tmp_path / "user_data/data/snapshots/test-snapshot-readiness.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "SEALED",
                "dataset": "snapshots/test",
                "datadir": str(tmp_path / "user_data/data/snapshots/test"),
                "requested_timerange": "20250101-20250110",
                "accepted_pairs": ["A/USDT:USDT"],
                "timeframes": ["30m", "1h", "1m"],
                "folds": [{"kind": "WFO_OOS"}] * 3,
                "policy_sha256": hashlib.sha256(policy.read_bytes()).hexdigest(),
                "snapshot_sha256": module.directory_sha256(tmp_path / "user_data/data/snapshots/test"),
            }
        ),
        encoding="utf-8",
    )
    calls = []
    monkeypatch.setattr(module.subprocess, "run", lambda command, **kwargs: calls.append(command))

    result = module.prepare(
        config=tmp_path / "config.json",
        policy_path=policy,
        dataset="test",
        timerange="20250101-20250110",
    )

    assert len(result["folds"]) >= 3
    assert result["seeded"] is False
    assert calls == []


def test_dataset_path_rejects_parent_escape():
    with pytest.raises(ValueError, match="relative path"):
        module._dataset_path("../outside")
