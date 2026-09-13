"""Verify that a PASS manifest matches the effective dry-run inputs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from dataclasses import asdict
import json
import hashlib
from pathlib import Path

from research_runtime.core import HypothesisState, canonical_json
from research_runtime.store import ResearchStore
from scripts.validation_core import ValidationStateStore
from scripts.validate_baseline import collect_identity


GATE_FIELDS = (
    "config_sha256",
    "strategy_sha256",
    "policy_sha256",
    "strategy_commit",
    "strategy",
    "strategy_path",
    "strategy_files",
    "accepted_pairs",
    "dry_run",
)


def _manifest_entries(value: object) -> list[dict[str, str]]:
    if isinstance(value, list):
        entries: list[dict[str, str]] = []
        for item in value:
            entries.extend(_manifest_entries(item))
        return entries
    if not isinstance(value, dict):
        return []
    entries = []
    for path_key, hash_key in (("path", "sha256"), ("manifest_path", "manifest_sha256"), ("report_path", "report_sha256")):
        path = value.get(path_key)
        digest = value.get(hash_key)
        if isinstance(path, str) and isinstance(digest, str) and path and digest:
            entries.append({"path": path, "sha256": digest})
    for key, nested in value.items():
        if key not in {"path", "sha256", "manifest_path", "manifest_sha256", "report_path", "report_sha256"}:
            entries.extend(_manifest_entries(nested))
    return entries


def _partition_key(value: object) -> tuple[str, str, str] | None:
    if not isinstance(value, dict):
        return None
    kind, start_at, end_at = (value.get(key) for key in ("kind", "start_at", "end_at"))
    if not all(isinstance(item, str) and item for item in (kind, start_at, end_at)):
        return None
    try:
        normalized = tuple(
            datetime.fromisoformat(item.replace("Z", "+00:00"))
            .astimezone(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
            for item in (start_at, end_at)
        )
    except ValueError:
        return None
    return str(kind), normalized[0], normalized[1]


def _decode_partition_list(value: object) -> list[object]:
    if not value:
        return []
    try:
        decoded = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return decoded if isinstance(decoded, list) else []


def validate_manifest(
    manifest_path: Path,
    config: Path,
    policy: Path,
    strategy: str,
    strategy_path: Path,
    research_db: Path | None = None,
    state_db: Path | None = None,
) -> list[str]:
    try:
        manifest = json.loads(manifest_path.read_text())
        if not isinstance(manifest, dict):
            return ["validation manifest must be a JSON object"]
        errors: list[str] = []
        if not manifest.get("plan_sha256"):
            errors.append("validation manifest plan identity is required")
        if manifest.get("verdict") != "PASS":
            errors.append("validation verdict is not PASS")
        if manifest.get("research_only") is True or manifest.get("research_window_contaminated") is True:
            errors.append("validation manifest is research-only for a contaminated window")
        if manifest.get("holdout", {}).get("available") is not True:
            errors.append("an untouched holdout window is required before dry-run")
        if manifest.get("walk_forward", {}).get("enabled") is not True:
            errors.append("walk-forward validation is required before dry-run")
        current = asdict(
            collect_identity(
                config,
                strategy_path / f"{strategy}.py",
                None,
                policy,
                strategy,
                strategy_path,
            )
        )
        if current["dry_run"] is not True:
            errors.append("effective config must set dry_run=true")
        policy_pairs = tuple(json.loads(policy.read_text()).get("accepted_basket", ()))
        if tuple(current["accepted_pairs"]) != policy_pairs:
            errors.append("effective config basket does not match validation policy")
        for field in GATE_FIELDS:
            expected = manifest.get(field)
            actual = current[field]
            if field == "accepted_pairs" and isinstance(expected, list):
                expected = tuple(expected)
                actual = tuple(actual)
            if expected != actual:
                errors.append(f"validation manifest {field} does not match effective input")
        if research_db is not None:
            if not research_db.is_file():
                errors.append("research state database does not exist")
            else:
                store = ResearchStore(research_db)
                hypothesis_id = manifest.get("hypothesis_id")
                if not hypothesis_id:
                    errors.append("validation manifest hypothesis_id is required")
                else:
                    hypothesis = store.get_hypothesis(str(hypothesis_id))
                    if hypothesis is None:
                        errors.append("validation hypothesis is missing from research state")
                    else:
                        if hypothesis["state"] != HypothesisState.APPROVED_FOR_DRY_RUN:
                            errors.append("validation hypothesis is not APPROVED_FOR_DRY_RUN")
                        if manifest.get("cycle_id") != hypothesis.get("cycle_id"):
                            errors.append("validation cycle does not own hypothesis")
                        if not hypothesis.get("plan_json") or not hypothesis.get("plan_sha256"):
                            errors.append("research hypothesis plan identity is missing")
                        else:
                            try:
                                stored_plan_hash = hashlib.sha256(
                                    canonical_json(json.loads(hypothesis["plan_json"])).encode()
                                ).hexdigest()
                            except (TypeError, ValueError, json.JSONDecodeError):
                                stored_plan_hash = None
                            if stored_plan_hash != hypothesis.get("plan_sha256") or manifest.get("plan_sha256") != hypothesis.get("plan_sha256"):
                                errors.append("validation plan identity does not match research state")
                        candidate_path = Path(str(manifest.get("candidate_path", "")))
                        if not candidate_path.is_file():
                            errors.append("validation candidate artifact is missing")
                        else:
                            digest = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
                            if str(candidate_path) != str(hypothesis.get("candidate_path")):
                                errors.append("validation candidate path does not match research state")
                            if digest != hypothesis.get("candidate_sha256") or digest != manifest.get("candidate_sha256"):
                                errors.append("validation candidate identity does not match research state")

                        experiment = store.find_experiment(hypothesis["cycle_id"], hypothesis["id"])
                        runs = store.list_runs(experiment["id"]) if experiment else []
                        latest = runs[-1] if runs else None
                        if experiment is None or latest is None or latest.get("verdict") != "PASS":
                            errors.append("a linked PASS validation run is required")
                        else:
                            if manifest.get("run_id") and manifest.get("run_id") != latest.get("id"):
                                errors.append("validation manifest run identity does not match research state")
                            if manifest.get("experiment_id") and manifest.get("experiment_id") != experiment.get("id"):
                                errors.append("validation manifest experiment identity does not match research state")
                            for field in ("config_sha256", "policy_sha256", "snapshot_sha256"):
                                if experiment.get(field) != manifest.get(field, experiment.get(field)):
                                    errors.append(f"validation manifest {field} does not match experiment")
                            try:
                                artifact_manifest = json.loads(latest["artifact_manifest_json"])
                            except (KeyError, json.JSONDecodeError):
                                artifact_manifest = None
                            refs = _manifest_entries(artifact_manifest)
                            manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
                            matching_ref = next(
                                (
                                    ref for ref in refs
                                    if Path(ref["path"]).resolve() == manifest_path.resolve()
                                ),
                                None,
                            )
                            if matching_ref is None or matching_ref["sha256"] != manifest_digest:
                                errors.append("validation manifest is not the hash-verified linked PASS artifact")
                            planned = _decode_partition_list(experiment.get("oos_partitions_json"))
                            observed = manifest.get("oos_partitions")
                            planned_keys = {_partition_key(item) for item in planned}
                            observed_keys = {_partition_key(item) for item in observed} if isinstance(observed, list) else set()
                            if not planned_keys or None in planned_keys or observed_keys != planned_keys:
                                errors.append("validation OOS partitions do not match the experiment plan")
                            else:
                                with store.connect() as connection:
                                    for kind, start_at, end_at in observed_keys:
                                        if connection.execute(
                                            """
                                            SELECT 1 FROM oos_partition_consumptions
                                            WHERE snapshot_sha256 = ? AND kind = ? AND start_at = ? AND end_at = ?
                                              AND run_id = ? AND verdict = 'PASS'
                                            """,
                                            (experiment["snapshot_sha256"], kind, start_at, end_at, latest["id"]),
                                        ).fetchone() is None:
                                            errors.append("validation OOS partition consumption is missing")
        if state_db is not None and state_db.is_file():
            state = ValidationStateStore(state_db).current("global")
            if state and state.get("state") != "ACTIVE":
                errors.append(f"validation runtime state is {state.get('state')}")
        return list(dict.fromkeys(errors))
    except Exception as error:
        return [f"validation manifest check failed: {type(error).__name__}: {error}"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--strategy-path", type=Path, required=True)
    parser.add_argument("--research-db", type=Path)
    parser.add_argument("--state-db", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors = validate_manifest(
        args.manifest, args.config, args.policy, args.strategy, args.strategy_path, args.research_db, args.state_db
    )
    if errors:
        for error in errors:
            print(error, file=__import__("sys").stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
