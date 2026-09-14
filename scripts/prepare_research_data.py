"""Seed and verify the data snapshot used by an automated research cycle."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

import pandas as pd

from research_runtime.snapshots import (
    atomic_write_json,
    directory_sha256,
    publish_snapshot,
)
from scripts.run_summary import write_run_summary
from scripts.seed_freqtrade_data import build_command
from scripts.validate_baseline import inspect_snapshot
from scripts.validation_core import ValidationPolicy, build_oos_folds


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_TIMEFRAMES = ["30m", "1h", "1m"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _dataset_path(value: str) -> Path:
    path = Path(value)
    if not path.parts or path.is_absolute() or ".." in path.parts:
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


def _fold_payload(folds: list[Any]) -> list[dict[str, str]]:
    return [
        {
            "kind": "WFO_OOS",
            "start_at": fold.oos_start.isoformat(),
            "end_at": fold.oos_end.isoformat(),
        }
        for fold in folds
    ]


def _manifest_path_for(final_datadir: Path) -> Path:
    return final_datadir.with_name(f"{final_datadir.name}-snapshot-readiness.json")


def _result_from_manifest(
    manifest: dict[str, Any], manifest_path: Path, *, reused: bool
) -> dict[str, object]:
    result = dict(manifest)
    result["status"] = "READY"
    result["manifest_path"] = str(manifest_path)
    result["manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    result["reused"] = reused
    result.setdefault("seeded", not reused)
    result.setdefault("fold_count", len(result.get("folds", [])))
    return result


def _verify_existing_sealed(
    *,
    final_datadir: Path,
    manifest_path: Path,
    dataset: str,
    timerange: str,
    policy_sha256: str,
    accepted_pairs: tuple[str, ...],
) -> dict[str, Any]:
    if not manifest_path.is_file():
        raise RuntimeError("sealed snapshot identity is missing its readiness manifest")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("sealed snapshot identity has an unreadable readiness manifest") from exc
    if not isinstance(manifest, dict):
        raise RuntimeError("sealed snapshot identity manifest must be an object")
    mismatches: list[str] = []
    if manifest.get("schema_version") != 1:
        mismatches.append("schema_version")
    if manifest.get("status") != "SEALED":
        mismatches.append("status")
    if manifest.get("dataset") != dataset:
        mismatches.append("dataset")
    if manifest.get("requested_timerange") != timerange:
        mismatches.append("requested_timerange")
    if manifest.get("policy_sha256") != policy_sha256:
        mismatches.append("policy_sha256")
    if tuple(manifest.get("accepted_pairs", ())) != tuple(accepted_pairs):
        mismatches.append("accepted_pairs")
    if manifest.get("timeframes") != REQUIRED_TIMEFRAMES:
        mismatches.append("timeframes")
    if manifest.get("datadir") and Path(str(manifest["datadir"])).resolve() != final_datadir.resolve():
        mismatches.append("datadir")
    expected_hash = str(manifest.get("snapshot_sha256") or "")
    if len(expected_hash) != 64:
        mismatches.append("snapshot_sha256")
    else:
        try:
            actual_hash = directory_sha256(final_datadir)
        except (FileNotFoundError, OSError) as exc:
            raise RuntimeError("sealed snapshot data directory cannot be hashed") from exc
        if actual_hash != expected_hash:
            mismatches.append("snapshot_sha256")
    if not isinstance(manifest.get("folds"), list) or not manifest["folds"]:
        mismatches.append("folds")
    if mismatches:
        raise RuntimeError("sealed snapshot identity mismatch: " + ", ".join(mismatches))
    return manifest


def _write_prepare_failure_summary(
    *,
    run_key: str | None,
    summary_root: Path | None,
    started_at: str,
    error: Exception,
) -> None:
    if not run_key or summary_root is None:
        return
    payload = {
        "status": "INCOMPLETE",
        "phase": "prepare_snapshot",
        "started_at": started_at,
        "completed_at": _now(),
        "error": str(error)[-500:],
    }
    try:
        write_run_summary(summary_root, run_key, payload)
    except (OSError, ValueError):
        pass


def prepare(
    *,
    config: Path,
    policy_path: Path,
    dataset: str,
    timerange: str,
    data_root: Path | None = None,
    staging_root: Path | None = None,
    manifest_path: Path | None = None,
    snapshot_id: str | None = None,
    run_key: str | None = None,
    summary_root: Path | None = None,
    timeframes: list[str] | tuple[str, ...] | None = None,
) -> dict[str, object]:
    started_at = _now()
    try:
        policy = ValidationPolicy.from_path(policy_path)
        if timeframes is not None and list(timeframes) != REQUIRED_TIMEFRAMES:
            raise ValueError("research snapshots require timeframes 30m, 1h, and 1m")
        if not policy.accepted_pairs:
            raise ValueError("validation policy has no accepted pairs")
        start, end = _timerange(timerange)
        dataset_path = _dataset_path(snapshot_id or dataset)
        requested_dataset_path = _dataset_path(dataset)
        if dataset_path != requested_dataset_path:
            raise ValueError("snapshot_id and dataset must identify the same snapshot")
        data_root = Path(data_root) if data_root is not None else ROOT / "user_data/data"
        staging_root = Path(staging_root) if staging_root is not None else data_root / ".staging"
        final_datadir = data_root / dataset_path
        staging_datadir = staging_root / dataset_path
        if final_datadir.resolve() == staging_datadir.resolve():
            raise ValueError("snapshot staging directory must differ from final directory")
        manifest_path = (
            Path(manifest_path) if manifest_path is not None else _manifest_path_for(final_datadir)
        )
        policy_sha256 = hashlib.sha256(policy_path.read_bytes()).hexdigest()

        if final_datadir.exists():
            if not final_datadir.is_dir():
                raise RuntimeError("sealed snapshot path is not a directory")
            manifest = _verify_existing_sealed(
                final_datadir=final_datadir,
                manifest_path=manifest_path,
                dataset=str(dataset_path),
                timerange=timerange,
                policy_sha256=policy_sha256,
                accepted_pairs=policy.accepted_pairs,
            )
            return _result_from_manifest(manifest, manifest_path, reused=True)

        staging_datadir.parent.mkdir(parents=True, exist_ok=True)
        final_datadir.parent.mkdir(parents=True, exist_ok=True)
        if staging_datadir.parent.stat().st_dev != final_datadir.parent.stat().st_dev:
            raise OSError("snapshot staging and final directories must share a filesystem")
        if staging_datadir.exists():
            if staging_datadir.is_symlink():
                raise RuntimeError("staging snapshot path must not be a symlink")
            shutil.rmtree(staging_datadir)
        staging_datadir.mkdir(parents=True, exist_ok=False)

        try:
            seed_args = argparse.Namespace(
                config=str(config),
                dataset=str(dataset_path),
                timeframes=list(REQUIRED_TIMEFRAMES),
                days=None,
                timerange=timerange,
                erase=False,
                data_root=str(staging_root),
            )
            subprocess.run(
                build_command(seed_args, list(policy.accepted_pairs), data_root=staging_root),
                cwd=ROOT,
                check=True,
            )
            evidence, errors, warnings = inspect_snapshot(
                staging_datadir, policy.accepted_pairs, start, end
            )
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
            snapshot_sha256 = directory_sha256(staging_datadir)
            folds_payload = _fold_payload(folds)
            manifest = {
                "schema_version": 1,
                "status": "SEALED",
                "dataset": str(dataset_path),
                "datadir": str(final_datadir),
                "requested_timerange": timerange,
                "effective_start": effective_start.isoformat(),
                "effective_end": effective_end.isoformat(),
                "effective_coverage": {
                    "start": common["start"],
                    "end_exclusive": common["end_exclusive"],
                },
                "accepted_pairs": list(policy.accepted_pairs),
                "timeframes": list(REQUIRED_TIMEFRAMES),
                "folds": folds_payload,
                "fold_count": len(folds_payload),
                "policy_sha256": policy_sha256,
                "snapshot_sha256": snapshot_sha256,
                "sealed_at": _now(),
                "warnings": warnings,
            }
            publish_snapshot(staging_datadir, final_datadir)
            atomic_write_json(manifest_path, manifest)
            verified_manifest = _verify_existing_sealed(
                final_datadir=final_datadir,
                manifest_path=manifest_path,
                dataset=str(dataset_path),
                timerange=timerange,
                policy_sha256=policy_sha256,
                accepted_pairs=policy.accepted_pairs,
            )
            result = _result_from_manifest(verified_manifest, manifest_path, reused=False)
            result["seeded"] = True
            return result
        except Exception:
            if staging_datadir.exists() and staging_datadir.is_dir() and not staging_datadir.is_symlink():
                shutil.rmtree(staging_datadir)
            raise
    except Exception as exc:
        _write_prepare_failure_summary(
            run_key=run_key,
            summary_root=Path(summary_root) if summary_root is not None else None,
            started_at=started_at,
            error=exc,
        )
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/config.futures.json"))
    parser.add_argument("--policy", type=Path, default=Path("config/validation.baseline.json"))
    parser.add_argument("--dataset", default="accepted_6pair_2026q3_full")
    parser.add_argument("--timerange", default="20260124-20260911")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("user_data/data"),
        help="Root directory containing sealed snapshots.",
    )
    parser.add_argument("--staging-root", type=Path)
    parser.add_argument("--manifest", dest="manifest_path", type=Path)
    parser.add_argument("--snapshot-id")
    parser.add_argument("--run-key")
    parser.add_argument("--summary-root", type=Path)
    parser.add_argument("--timeframes", nargs="+", default=list(REQUIRED_TIMEFRAMES))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = prepare(
            config=args.config,
            policy_path=args.policy,
            dataset=args.dataset,
            timerange=args.timerange,
            data_root=args.data_root,
            staging_root=args.staging_root,
            manifest_path=args.manifest_path,
            snapshot_id=args.snapshot_id,
            run_key=args.run_key,
            summary_root=args.summary_root,
            timeframes=args.timeframes,
        )
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"research data not ready: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
