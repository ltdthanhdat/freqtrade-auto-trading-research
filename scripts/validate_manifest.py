"""Verify that a PASS manifest matches the effective dry-run inputs."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import hashlib
from pathlib import Path

from research_runtime.core import HypothesisState
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
                    elif hypothesis["state"] != HypothesisState.APPROVED_FOR_DRY_RUN:
                        errors.append("validation hypothesis is not APPROVED_FOR_DRY_RUN")
                    else:
                        if manifest.get("cycle_id") != hypothesis.get("cycle_id"):
                            errors.append("validation cycle does not own hypothesis")
                        candidate_path = Path(str(manifest.get("candidate_path", "")))
                        if not candidate_path.is_file():
                            errors.append("validation candidate artifact is missing")
                        else:
                            digest = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
                            if str(candidate_path) != str(hypothesis.get("candidate_path")):
                                errors.append("validation candidate path does not match research state")
                            if digest != hypothesis.get("candidate_sha256") or digest != manifest.get("candidate_sha256"):
                                errors.append("validation candidate identity does not match research state")
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
