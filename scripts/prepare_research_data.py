"""Seed and verify the data snapshot used by an automated research cycle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

import pandas as pd

from scripts.seed_freqtrade_data import build_command
from scripts.validate_baseline import inspect_snapshot
from scripts.validation_core import ValidationPolicy, build_oos_folds


ROOT = Path(__file__).resolve().parents[1]


def _dataset_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("dataset must be a relative path")
    if path.parts[:1] != ("snapshots",):
        path = Path("snapshots") / path
    return path


def _timerange(value: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    parts = value.split("-")
    if len(parts) != 2 or any(len(part) != 8 or not part.isdigit() for part in parts):
        raise ValueError("timerange must use YYYYMMDD-YYYYMMDD")
    start, end = (pd.Timestamp(part, tz="UTC") for part in parts)
    if start >= end:
        raise ValueError("timerange start must precede end")
    return start, end


def prepare(
    *,
    config: Path,
    policy_path: Path,
    dataset: str,
    timerange: str,
) -> dict[str, object]:
    policy = ValidationPolicy.from_path(policy_path)
    if not policy.accepted_pairs:
        raise ValueError("validation policy has no accepted pairs")
    start, end = _timerange(timerange)
    dataset_path = _dataset_path(dataset)
    seed_args = argparse.Namespace(
        config=str(config),
        dataset=str(dataset_path),
        timeframes=["30m", "1h", "1m"],
        days=None,
        timerange=timerange,
        erase=False,
    )
    subprocess.run(
        build_command(seed_args, list(policy.accepted_pairs)),
        cwd=ROOT,
        check=True,
    )

    datadir = ROOT / "user_data/data" / dataset_path
    evidence, errors, warnings = inspect_snapshot(datadir, policy.accepted_pairs, start, end)
    if errors:
        raise RuntimeError("snapshot validation failed: " + "; ".join(errors))
    common = evidence.get("common_interval")
    if not isinstance(common, dict):
        raise RuntimeError("snapshot has no common OHLCV interval")
    effective_start = max(start, pd.Timestamp(common["start"])).ceil("D")
    effective_end = min(end, pd.Timestamp(common["end_exclusive"])).floor("D")
    folds = build_oos_folds(effective_start, effective_end, policy)
    if len(folds) < policy.required_folds:
        raise RuntimeError(
            f"snapshot has {len(folds)} OOS folds; requires {policy.required_folds}"
        )
    return {
        "dataset": str(dataset_path),
        "datadir": str(datadir),
        "requested_timerange": timerange,
        "effective_start": effective_start.isoformat(),
        "effective_end": effective_end.isoformat(),
        "folds": len(folds),
        "warnings": warnings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/config.futures.json"))
    parser.add_argument("--policy", type=Path, default=Path("config/validation.baseline.json"))
    parser.add_argument("--dataset", default="accepted_6pair_2026q3_full")
    parser.add_argument("--timerange", default="20260123-20260911")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = prepare(
            config=args.config,
            policy_path=args.policy,
            dataset=args.dataset,
            timerange=args.timerange,
        )
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"research data not ready: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
