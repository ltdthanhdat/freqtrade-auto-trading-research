import json
from pathlib import Path

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
    calls = []
    monkeypatch.setattr(module.subprocess, "run", lambda command, **kwargs: calls.append(command))

    result = module.prepare(
        config=tmp_path / "config.json",
        policy_path=policy,
        dataset="test",
        timerange="20250101-20250110",
    )

    assert result["folds"] >= 3
    assert result["seeded"] is False
    assert calls == []


def test_dataset_path_rejects_parent_escape():
    with pytest.raises(ValueError, match="relative path"):
        module._dataset_path("../outside")
