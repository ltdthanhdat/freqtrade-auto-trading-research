"""Verify that a PASS manifest matches the effective dry-run inputs."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

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
) -> list[str]:
    try:
        manifest = json.loads(manifest_path.read_text())
        if not isinstance(manifest, dict):
            return ["validation manifest must be a JSON object"]
        errors: list[str] = []
        if manifest.get("verdict") != "PASS":
            errors.append("validation verdict is not PASS")
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors = validate_manifest(
        args.manifest, args.config, args.policy, args.strategy, args.strategy_path
    )
    if errors:
        for error in errors:
            print(error, file=__import__("sys").stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
