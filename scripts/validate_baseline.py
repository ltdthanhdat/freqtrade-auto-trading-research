"""Run the frozen baseline validation without modifying its inputs."""

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Callable, Sequence
import zipfile

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
DrawdownAdapter = Callable[[list[FoldMetrics]], float]


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
        attribution=False,
    )


def _load_exported_trades(path: Path) -> pd.DataFrame:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.endswith(".json") and "config" not in name]
            if not names:
                raise ValueError("trade export contains no result json")
            data = json.loads(archive.read(names[0]))
    else:
        data = json.loads(path.read_text())
    strategy = data.get("strategy", {})
    if not strategy:
        raise ValueError("trade export contains no strategy results")
    trades = pd.DataFrame(next(iter(strategy.values())).get("trades", []))
    if "profit_ratio" not in trades:
        raise ValueError("trade export contains no profit_ratio")
    return trades


def _fold_metrics(trades: pd.DataFrame) -> FoldMetrics:
    returns = pd.to_numeric(trades["profit_ratio"], errors="raise")
    equity = (1 + returns).cumprod()
    drawdown = 1 - equity / equity.cummax()
    return FoldMetrics(len(trades), float(returns.sum()), float(drawdown.max()))


def _attribution_is_evidenced(trades: pd.DataFrame) -> bool:
    if trades.empty or not {"pair", "enter_tag"}.issubset(trades.columns):
        return False
    contribution = trades.groupby(["pair", "enter_tag"], dropna=False)["profit_ratio"].sum()
    return (contribution > 0).sum() > 1


def _validate_folds(folds: tuple[OosFold, ...]) -> list[str]:
    if not folds:
        return ["no OOS folds available"]
    if any(folds[index].oos_end > folds[index + 1].oos_start for index in range(len(folds) - 1)):
        return ["OOS folds overlap"]
    if any(fold.oos_start >= fold.oos_end for fold in folds):
        return ["OOS fold has an invalid range"]
    return []


def run_oos_folds(
    args: argparse.Namespace, executor: Executor, policy: ValidationPolicy, run_dir: Path
) -> tuple[tuple[OosFold, ...], list[FoldMetrics], pd.DataFrame, list[str]]:
    folds = build_oos_folds(pd.Timestamp(args.start, tz="UTC"), pd.Timestamp(args.end, tz="UTC"), policy)
    fold_metrics: list[FoldMetrics] = []
    trade_frames: list[pd.DataFrame] = []
    reasons = _validate_folds(tuple(folds))
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
        if not _run_command(executor, command):
            reasons.append(f"fold {index} backtest failed")
            continue
        try:
            trades = _load_exported_trades(filename)
        except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as error:
            reasons.append(f"fold {index} trade export is invalid: {error}")
            continue
        fold_metrics.append(_fold_metrics(trades))
        trade_frames.append(trades)
    all_trades = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    return tuple(folds), fold_metrics, all_trades, reasons


def _identity_reasons(identity: ValidationIdentity, approved: object) -> list[str]:
    if not isinstance(approved, dict):
        return ["approved baseline identity is required"]
    return [
        f"{field.removesuffix('_sha256')} identity does not match approved baseline"
        for field, value in asdict(identity).items()
        if approved.get(field) != value
    ]


def _load_approved_identity(value: object) -> object:
    if isinstance(value, Path):
        return json.loads(value.read_text())
    return value


def _p95_drawdown(args: argparse.Namespace, metrics: list[FoldMetrics]) -> tuple[float, list[str]]:
    adapter = getattr(args, "p95_drawdown", None)
    if not callable(adapter):
        return float("inf"), ["bootstrap drawdown evidence is unavailable"]
    return float(adapter(metrics)), []


def _write_result(
    run_dir: Path,
    identity: ValidationIdentity,
    checks: Checks,
    folds: tuple[OosFold, ...],
    fold_metrics: list[FoldMetrics],
    p95_dd: float,
    policy: ValidationPolicy,
    reasons: list[str],
) -> ValidationRun:
    verdict = "FAIL" if reasons else evaluate_verdict(checks, fold_metrics, p95_dd, policy)
    if not checks.lookahead:
        reasons.append("lookahead analysis failed")
    if not checks.recursive:
        reasons.append("recursive analysis failed")
    if not checks.attribution:
        reasons.append("attribution evidence is insufficient")
    if any(metric.max_drawdown > policy.max_drawdown for metric in fold_metrics):
        reasons.append("OOS drawdown exceeds policy")
    if verdict == "FAIL" and not reasons:
        reasons.append("OOS trade metrics are unavailable")

    manifest_path = run_dir / "manifest.json"
    report_path = run_dir / "report.md"
    manifest = {
        **asdict(identity),
        "checks": asdict(checks),
        "folds": [asdict(fold) for fold in folds],
        "fold_metrics": [asdict(metric) for metric in fold_metrics],
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
    reasons = _identity_reasons(
        identity, _load_approved_identity(getattr(args, "approved_identity", None))
    )
    reasons.extend(f"missing timeframe {timeframe}" for timeframe in missing)
    if missing:
        return _write_result(run_dir, identity, Checks(False, False, False), (), [], float("inf"), policy, reasons)
    checks = run_correctness_checks(args, executor)
    folds, fold_metrics, trades, fold_reasons = run_oos_folds(args, executor, policy, run_dir)
    reasons.extend(fold_reasons)
    checks = Checks(checks.lookahead, checks.recursive, _attribution_is_evidenced(trades))
    p95_dd, adapter_reasons = _p95_drawdown(args, fold_metrics)
    reasons.extend(adapter_reasons)
    return _write_result(run_dir, identity, checks, folds, fold_metrics, p95_dd, policy, reasons)


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
    parser.add_argument("--approved-identity", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    result = run_validation(parse_args())
    raise SystemExit(0 if result.verdict == "PASS" else 1)
