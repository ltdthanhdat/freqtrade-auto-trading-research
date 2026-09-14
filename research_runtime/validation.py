from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Callable

from research_runtime.candidates import validate_candidate_source
from research_runtime.freqtrade_preflight import CandidatePreflightResult, preflight_candidate
from scripts.validate_baseline import (
    REQUIRED_TIMEFRAMES,
    _combined_hash,
    _strategy_files,
    collect_identity,
    run_validation,
)


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


def _assert_experiment_metadata(experiment: dict[str, Any], identity: dict[str, Any]) -> None:
    expected_pairs = experiment.get("pairs")
    actual_pairs = identity.get("accepted_pairs")
    if expected_pairs is not None and actual_pairs is not None and tuple(expected_pairs) != tuple(actual_pairs):
        raise ValueError("experiment metadata pairs mismatch")

    expected_strategy = experiment.get("strategy_name")
    actual_strategy = identity.get("strategy")
    if expected_strategy and actual_strategy and str(expected_strategy) != str(actual_strategy):
        raise ValueError("experiment metadata strategy mismatch")

    expected_path = experiment.get("strategy_path")
    actual_path = identity.get("strategy_path")
    if expected_path and actual_path and Path(str(expected_path)).resolve() != Path(str(actual_path)).resolve():
        raise ValueError("experiment metadata strategy path mismatch")

    expected_timeframes = experiment.get("timeframes")
    if expected_timeframes is not None and set(expected_timeframes) != set(REQUIRED_TIMEFRAMES):
        raise ValueError("experiment metadata timeframes mismatch")
    expected_detail = experiment.get("timeframe_detail")
    if expected_detail is not None and str(expected_detail) != "1m":
        raise ValueError("experiment metadata timeframe detail mismatch")


def _assert_candidate_identity(
    candidate_file: Path,
    strategy_name: str,
    *,
    expected_sha256: str | None,
    identity_bound: bool,
) -> str:
    if not candidate_file.is_file():
        raise ValueError("candidate path does not exist")
    validate_candidate_source(candidate_file.read_text(), strategy_name, identity_bound=identity_bound)
    digest = _sha256(candidate_file)
    if expected_sha256 and digest != expected_sha256:
        raise ValueError("candidate identity does not match experiment")
    return digest or ""


def _write_preflight_artifacts(
    experiment: dict[str, Any],
    root: Path,
    candidate_file: Path,
    strategy_name: str,
    strategy_path: Path,
    candidate_sha256: str,
    preflight: CandidatePreflightResult,
) -> tuple[Path, Path, str, str, dict[str, Any]]:
    run_id = str(experiment.get("id") or "validation")
    if not run_id or Path(run_id).name != run_id:
        raise ValueError("invalid validation run id")
    run_dir = Path(experiment.get("runs_dir") or root / "validation") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "preflight.json"
    report_path = run_dir / "report.md"
    payload: dict[str, Any] = {
        "candidate_path": str(candidate_file),
        "candidate_sha256": candidate_sha256,
        "strategy_name": strategy_name,
        "strategy_path": str(strategy_path),
        "config_path": str(experiment.get("config_path", "")),
        "config_sha256": experiment.get("config_sha256"),
        "error_code": "candidate_preflight",
        "details": list(preflight.details),
        "passed": False,
        "oos_partitions": [],
        "oos_consumption": {"status": "not_allocated"},
    }
    manifest_path.write_text(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    report_path.write_text(
        "# Candidate preflight\n\n"
        "Verdict: `FAIL`\n\n"
        + "\n".join(f"- {detail}" for detail in preflight.details)
        + "\n",
        encoding="utf-8",
    )
    manifest_hash = _sha256(manifest_path) or ""
    report_hash = _sha256(report_path) or ""
    artifacts = {
        "preflight": payload,
        "oos_partitions": [],
        "oos_consumption": {"status": "not_allocated"},
        "manifest_path": str(manifest_path),
        "report_path": str(report_path),
        "manifest_sha256": manifest_hash,
        "report_sha256": report_hash,
    }
    return manifest_path, report_path, manifest_hash, report_hash, artifacts


def validate_candidate(
    experiment: dict[str, Any],
    *,
    artifact_root: str | Path | None = None,
    collect_identity_fn: Callable[..., Any] = collect_identity,
    preflight_fn: Callable[..., CandidatePreflightResult] = preflight_candidate,
    run_validation_fn: Callable[..., Any] = run_validation,
) -> ResearchVerdict:
    required_hashes = ("parent_sha256", "config_sha256", "snapshot_sha256", "policy_sha256")
    missing = [field for field in required_hashes if not str(experiment.get(field, ""))]
    identity_bound = bool(experiment.get("identity_bound") or experiment.get("plan_sha256"))
    if identity_bound and not str(experiment.get("plan_sha256", "")):
        missing.append("plan_sha256")
    if missing:
        raise ValueError(f"missing experiment identity hashes: {', '.join(missing)}")
    candidate_file = Path(experiment.get("candidate_path", "")).resolve()
    strategy_name = str(experiment.get("strategy_name", ""))
    strategy_path = Path(experiment.get("strategy_path") or candidate_file.parent)
    strategy_file = Path(experiment.get("strategy_file") or candidate_file)
    if strategy_path.suffix == ".py":
        strategy_file = strategy_path
        strategy_path = strategy_path.parent
    initial_candidate_sha256 = _assert_candidate_identity(
        candidate_file,
        strategy_name,
        expected_sha256=str(experiment.get("candidate_sha256")) if experiment.get("candidate_sha256") else None,
        identity_bound=identity_bound,
    )
    initial_strategy_files = _strategy_files(strategy_file, strategy_path)
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
        plan_sha256=experiment.get("plan_sha256"),
        trading_plan=experiment.get("trading_plan"),
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
        _assert_experiment_metadata(experiment, identity)
        expected_strategy_sha256 = experiment.get("strategy_sha256")
        if expected_strategy_sha256 and identity.get("strategy_sha256") != expected_strategy_sha256:
            raise ValueError("strategy identity does not match experiment metadata")
        expected_dependencies = experiment.get("dependency_hashes")
        if expected_dependencies is not None:
            actual_dependencies = identity.get("strategy_files")
            if not isinstance(expected_dependencies, dict) or actual_dependencies != expected_dependencies:
                raise ValueError("dependency identity does not match experiment metadata")
        current_candidate_sha256 = _assert_candidate_identity(
            candidate_file,
            strategy_name,
            expected_sha256=str(experiment.get("candidate_sha256")) if experiment.get("candidate_sha256") else None,
            identity_bound=identity_bound,
        )
        if current_candidate_sha256 != initial_candidate_sha256:
            raise ValueError("candidate identity changed during validation")
        current_strategy_files = _strategy_files(strategy_file, strategy_path)
        if current_strategy_files != initial_strategy_files:
            raise ValueError("dependency identity changed during validation")
        preflight = preflight_fn(
            config_path=args.config,
            strategy_name=strategy_name,
            strategy_path=strategy_path,
        )
        if not isinstance(preflight, CandidatePreflightResult):
            raise ValueError("candidate preflight returned an invalid result")
        if not preflight.passed:
            (
                preflight_manifest_path,
                preflight_report_path,
                preflight_manifest_hash,
                preflight_report_hash,
                preflight_artifacts,
            ) = _write_preflight_artifacts(
                experiment,
                root,
                candidate_file,
                strategy_name,
                strategy_path,
                initial_candidate_sha256,
                preflight,
            )
            return ResearchVerdict(
                verdict="FAIL",
                state="REJECTED",
                metrics={},
                artifacts=preflight_artifacts,
                manifest_path=preflight_manifest_path,
                report_path=preflight_report_path,
                manifest_hash=preflight_manifest_hash,
                report_hash=preflight_report_hash,
                error_code="candidate_preflight",
                details=preflight.details,
            )
        result = run_validation_fn(args)
        verdict = str(_result_value(result, "verdict", ""))
        manifest_path = _path_value(_result_value(result, "manifest_path"))
        report_path = _path_value(_result_value(result, "report_path"))
        manifest_hash = _sha256(manifest_path)
        report_hash = _sha256(report_path)
        metrics = _result_value(result, "metrics", {})
        artifacts = _result_value(result, "artifacts", {})
        evidence_errors: list[str] = []
        manifest_loaded = False
        if manifest_path and manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text())
                manifest_loaded = isinstance(manifest, dict)
                if identity_bound and verdict == "PASS" and manifest_loaded:
                    plan_identity = manifest.get("plan_sha256")
                    if plan_identity is None and isinstance(manifest.get("plan"), dict):
                        plan_identity = manifest["plan"].get("sha256")
                    if plan_identity != experiment.get("plan_sha256"):
                        evidence_errors.append("complete-plan manifest plan identity is missing or mismatched")
                    exit_coverage = manifest.get("exit_coverage")
                    if exit_coverage is None and isinstance(manifest.get("complete_plan"), dict):
                        exit_coverage = manifest["complete_plan"].get("exit_coverage")
                    if isinstance(exit_coverage, dict):
                        exit_coverage = exit_coverage.get("coverage")
                    risk_ledger = manifest.get("risk_ledger")
                    risk_coverage = (
                        risk_ledger.get("coverage")
                        if isinstance(risk_ledger, dict)
                        else manifest.get("risk_ledger_coverage")
                    )
                    try:
                        exit_coverage_value = float(exit_coverage)
                    except (TypeError, ValueError):
                        exit_coverage_value = 0.0
                    try:
                        risk_coverage_value = float(risk_coverage)
                    except (TypeError, ValueError):
                        risk_coverage_value = 0.0
                    if not math.isfinite(exit_coverage_value) or exit_coverage_value < 1.0:
                        evidence_errors.append("complete-plan exit coverage is incomplete")
                    if not math.isfinite(risk_coverage_value) or risk_coverage_value < 1.0:
                        evidence_errors.append("complete-plan risk-ledger coverage is incomplete")
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
                if evidence_errors and verdict == "PASS":
                    verdict = "FAIL"
                    manifest["verdict"] = "FAIL"
                    manifest.setdefault("reasons", []).extend(evidence_errors)
                if annotations or evidence_errors:
                    manifest_path.write_text(
                        json.dumps(manifest, default=str, indent=2, allow_nan=False) + "\n"
                    )
                    manifest_hash = _sha256(manifest_path)
                if not metrics:
                    metrics = manifest.get("fold_metrics", {})
                manifest_artifacts = {
                    "backtest_artifacts": manifest.get("backtest_artifacts", []),
                    "oos_partitions": manifest.get("oos_partitions", []),
                    "oos_consumption": manifest.get("oos_consumption", {}),
                    "complete_plan": manifest.get("complete_plan", {}),
                    "exit_reason_counts": manifest.get("exit_reason_counts", {}),
                    "exit_coverage": manifest.get("exit_coverage", 0.0),
                    "risk_ledger": manifest.get("risk_ledger", {}),
                    "net_realized_r": manifest.get("net_realized_r"),
                    "loss_overrun_p95": manifest.get("loss_overrun_p95"),
                    "costs": manifest.get("costs", {}),
                    "holding_duration": manifest.get("holding_duration", {}),
                    "mae_mfe": manifest.get("mae_mfe", {}),
                }
                if isinstance(artifacts, dict):
                    artifacts = {**manifest_artifacts, **artifacts}
                else:
                    artifacts = manifest_artifacts
            except (OSError, json.JSONDecodeError):
                pass
        if identity_bound and verdict == "PASS" and not manifest_loaded:
            evidence_errors.append("complete-plan manifest evidence is missing")
            verdict = "FAIL"
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
            details=tuple(evidence_errors),
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
