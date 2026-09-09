"""Run the frozen baseline validation without modifying its inputs."""

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Callable, Sequence

import pandas as pd

from scripts.validation_core import (
    Checks,
    FoldMetrics,
    OosFold,
    ValidationPolicy,
    build_oos_folds,
    evaluate_verdict,
)


Executor = Callable[..., object]


@dataclass(frozen=True)
class ValidationIdentity:
    config_sha256: str
    strategy_sha256: str
    snapshot_sha256: str
    strategy_commit: str


@dataclass(frozen=True)
class ValidationRun:
    verdict: str
    reasons: tuple[str, ...]
    manifest_path: Path
    report_path: Path
    checks: Checks
    folds: tuple[OosFold, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _snapshot_sha256(datadir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(candidate for candidate in datadir.rglob("*") if candidate.is_file()):
        digest.update(path.relative_to(datadir).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def collect_identity(config: Path, strategy_file: Path, datadir: Path) -> ValidationIdentity:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    return ValidationIdentity(
        config_sha256=_sha256(config),
        strategy_sha256=_sha256(strategy_file),
        snapshot_sha256=_snapshot_sha256(datadir),
        strategy_commit=commit,
    )


def ensure_required_timeframes(datadir: Path, timeframes: Sequence[str]) -> tuple[str, ...]:
    missing = []
    for timeframe in timeframes:
        if not any(datadir.rglob(f"*{timeframe}*")):
            missing.append(timeframe)
    return tuple(missing)


def _freqtrade_command(args: argparse.Namespace, command: str) -> list[str]:
    return [
        "python",
        "-m",
        "freqtrade",
        command,
        "--config",
        str(args.config),
        "--datadir",
        str(args.datadir),
        "--strategy",
        args.strategy,
        "--strategy-path",
        str(args.strategy_path),
    ]


def _run_command(executor: Executor, command: list[str]) -> bool:
    result = executor(command, check=False, capture_output=True, text=True)
    return getattr(result, "returncode", 1) == 0


def run_correctness_checks(args: argparse.Namespace, executor: Executor) -> Checks:
    return Checks(
        lookahead=_run_command(executor, _freqtrade_command(args, "lookahead-analysis")),
        recursive=_run_command(executor, _freqtrade_command(args, "recursive-analysis")),
        attribution=True,
    )


def run_oos_folds(
    args: argparse.Namespace, executor: Executor, policy: ValidationPolicy, run_dir: Path
) -> tuple[OosFold, ...]:
    folds = build_oos_folds(pd.Timestamp(args.start, tz="UTC"), pd.Timestamp(args.end, tz="UTC"), policy)
    for index, fold in enumerate(folds, start=1):
        filename = run_dir / f"fold-{index}-{fold.oos_start:%Y%m%d}-{fold.oos_end:%Y%m%d}.json"
        command = _freqtrade_command(args, "backtesting") + [
            "--timerange",
            f"{fold.oos_start:%Y%m%d}-{fold.oos_end:%Y%m%d}",
            "--cache",
            "none",
            "--timeframe-detail",
            "1m",
            "--export",
            "trades",
            "--backtest-filename",
            str(filename),
        ]
        _run_command(executor, command)
    return tuple(folds)


def _write_result(
    run_dir: Path,
    identity: ValidationIdentity,
    checks: Checks,
    folds: tuple[OosFold, ...],
    policy: ValidationPolicy,
    reasons: list[str],
) -> ValidationRun:
    metrics = [FoldMetrics(0, 0.0, 0.0) for _ in folds]
    verdict = "FAIL" if reasons else evaluate_verdict(checks, metrics, 0.0, policy)
    if not checks.lookahead:
        reasons.append("lookahead analysis failed")
    if not checks.recursive:
        reasons.append("recursive analysis failed")
    if verdict == "FAIL" and not reasons:
        reasons.append("OOS trade metrics are unavailable")

    manifest_path = run_dir / "manifest.json"
    report_path = run_dir / "report.md"
    manifest = {
        **asdict(identity),
        "checks": asdict(checks),
        "folds": [asdict(fold) for fold in folds],
        "policy": asdict(policy),
        "verdict": verdict,
        "reasons": reasons,
    }
    manifest_path.write_text(json.dumps(manifest, default=str, indent=2) + "\n")
    report_path.write_text(
        "# Baseline validation\n\n"
        f"Verdict: `{verdict}`\n\n"
        + "\n".join(f"- {reason}" for reason in reasons)
        + "\n"
    )
    return ValidationRun(verdict, tuple(reasons), manifest_path, report_path, checks, folds)


def run_validation(args: argparse.Namespace, executor: Executor = subprocess.run) -> ValidationRun:
    policy = args.policy if isinstance(args.policy, ValidationPolicy) else ValidationPolicy.from_path(args.policy)
    run_dir = Path(args.runs_dir) / args.run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    identity = collect_identity(Path(args.config), Path(args.strategy_file), Path(args.datadir))
    missing = ensure_required_timeframes(Path(args.datadir), ("1m", "30m", "1h"))
    reasons = [f"missing timeframe {timeframe}" for timeframe in missing]
    if missing:
        return _write_result(run_dir, identity, Checks(False, False, False), (), policy, reasons)
    checks = run_correctness_checks(args, executor)
    folds = run_oos_folds(args, executor, policy, run_dir)
    return _write_result(run_dir, identity, checks, folds, policy, reasons)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--strategy-file", type=Path, required=True)
    parser.add_argument("--datadir", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--strategy-path", type=Path, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--runs-dir", type=Path, default=Path(".research/smc_fvg_pinbar/runs"))
    parser.add_argument("--run-id", default=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    return parser.parse_args()


if __name__ == "__main__":
    result = run_validation(parse_args())
    raise SystemExit(0 if result.verdict == "PASS" else 1)
