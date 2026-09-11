from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Callable

from scripts.validate_baseline import _combined_hash, _strategy_files, collect_identity, run_validation


@dataclass(frozen=True)
class ResearchVerdict:
    verdict: str
    state: str
    metrics: dict[str, Any]
    artifacts: dict[str, Any]
    manifest_path: Path | None = None
    report_path: Path | None = None
    manifest_hash: str | None = None
    report_hash: str | None = None
    error_code: str | None = None
    details: tuple[str, ...] = ()


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _identity_dict(identity: Any) -> dict[str, Any]:
    if is_dataclass(identity):
        return asdict(identity)
    if isinstance(identity, dict):
        return dict(identity)
    raise ValueError("collect_identity returned an invalid identity")


def _result_value(result: Any, key: str, default: Any = None) -> Any:
    if isinstance(result, dict):
        return result.get(key, default)
    return getattr(result, key, default)


def _path_value(value: Any) -> Path | None:
    if value is None:
        return None
    return Path(value)


def _state_for(verdict: str) -> str:
    return {
        "PASS": "NEEDS_REVIEW",
        "WARN": "INCONCLUSIVE",
        "FAIL": "REJECTED",
    }.get(verdict, "RETRYABLE")


def validate_candidate(
    experiment: dict[str, Any],
    *,
    artifact_root: str | Path | None = None,
    collect_identity_fn: Callable[..., Any] = collect_identity,
    run_validation_fn: Callable[..., Any] = run_validation,
) -> ResearchVerdict:
    required_hashes = ("parent_sha256", "config_sha256", "snapshot_sha256", "policy_sha256")
    missing = [field for field in required_hashes if not str(experiment.get(field, ""))]
    if missing:
        raise ValueError(f"missing experiment identity hashes: {', '.join(missing)}")
    candidate_file = Path(experiment.get("candidate_path", "")).resolve()
    if not candidate_file.is_file():
        raise ValueError("candidate path does not exist")
    strategy_name = str(experiment.get("strategy_name", ""))
    strategy_path = Path(experiment.get("strategy_path") or candidate_file.parent)
    strategy_file = Path(experiment.get("strategy_file") or candidate_file)
    if strategy_path.suffix == ".py":
        strategy_file = strategy_path
        strategy_path = strategy_path.parent
    parent_strategy = str(experiment.get("parent_strategy", ""))
    if parent_strategy and parent_strategy != "fixture":
        parent_root = Path(experiment.get("parent_strategy_path") or "src/strategies")
        parent_file = parent_root / f"{parent_strategy}.py"
        if not parent_file.is_file():
            raise ValueError("parent strategy file does not exist")
        if _combined_hash(_strategy_files(parent_file, parent_root)) != str(experiment["parent_sha256"]):
            raise ValueError("parent strategy identity does not match experiment")
    root = Path(artifact_root or experiment.get("artifact_root") or candidate_file.parent.parent)
    args = argparse.Namespace(
        config=Path(experiment["config_path"]),
        strategy_file=strategy_file,
        datadir=Path(experiment["snapshot_path"]),
        policy=Path(experiment["policy_path"]),
        strategy=strategy_name,
        strategy_path=strategy_path,
        start=experiment["start_at"],
        end=experiment["end_at"],
        runs_dir=Path(experiment.get("runs_dir") or root / "validation"),
        run_id=str(experiment.get("id") or "validation"),
        approved_identity=None,
        wfo=bool(experiment.get("wfo", True)),
    )
    try:
        identity = _identity_dict(
            collect_identity_fn(
                args.config,
                args.strategy_file,
                args.datadir,
                args.policy,
                args.strategy,
                args.strategy_path,
            )
        )
        args.approved_identity = identity
        for field in ("config_sha256", "snapshot_sha256", "policy_sha256"):
            expected = str(experiment[field])
            if identity.get(field) != expected:
                raise ValueError(f"{field} does not match candidate identity")
        result = run_validation_fn(args)
        verdict = str(_result_value(result, "verdict", ""))
        manifest_path = _path_value(_result_value(result, "manifest_path"))
        report_path = _path_value(_result_value(result, "report_path"))
        manifest_hash = _sha256(manifest_path)
        report_hash = _sha256(report_path)
        metrics = _result_value(result, "metrics", {})
        artifacts = _result_value(result, "artifacts", {})
        if manifest_path and manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text())
                annotations = {
                    key: experiment.get(key)
                    for key in ("cycle_id", "hypothesis_id", "candidate_path")
                    if experiment.get(key)
                }
                annotations["candidate_sha256"] = str(
                    experiment.get("candidate_sha256") or _sha256(candidate_file)
                )
                if annotations:
                    manifest.update(annotations)
                    manifest_path.write_text(
                        json.dumps(manifest, default=str, indent=2, allow_nan=False) + "\n"
                    )
                    manifest_hash = _sha256(manifest_path)
                if not metrics:
                    metrics = manifest.get("fold_metrics", {})
                if not artifacts:
                    artifacts = {"backtest_artifacts": manifest.get("backtest_artifacts", [])}
            except (OSError, json.JSONDecodeError):
                pass
        state = _state_for(verdict)
        error_code = None if state != "RETRYABLE" else "unknown_verdict"
        return ResearchVerdict(
            verdict=verdict,
            state=state,
            metrics=metrics if isinstance(metrics, dict) else {"value": metrics},
            artifacts=artifacts if isinstance(artifacts, dict) else {"value": artifacts},
            manifest_path=manifest_path,
            report_path=report_path,
            manifest_hash=manifest_hash,
            report_hash=report_hash,
            error_code=error_code,
        )
    except ValueError:
        raise
    except Exception as exc:
        return ResearchVerdict(
            verdict="RETRYABLE",
            state="RETRYABLE",
            metrics={},
            artifacts={},
            error_code="validation_exception",
            details=(f"{type(exc).__name__}: {exc}",),
        )
