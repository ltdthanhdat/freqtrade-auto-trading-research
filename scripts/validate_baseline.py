"""Run the frozen baseline validation without modifying its inputs."""

from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from typing import Callable
import zipfile

import numpy as np
import pandas as pd

from freqtrade.configuration.environment_vars import environment_vars_to_dict
from freqtrade.configuration.load_config import load_from_files
from freqtrade.misc import deep_merge_dicts

from scripts.validation_core import (
    BootstrapSummary,
    Checks,
    FoldMetrics,
    OosFold,
    ValidationPolicy,
    bootstrap_equity_paths,
    build_oos_folds,
    evaluate_verdict,
)


Executor = Callable[..., object]
REQUIRED_TIMEFRAMES = {
    "1m": pd.Timedelta(minutes=1),
    "30m": pd.Timedelta(minutes=30),
    "1h": pd.Timedelta(hours=1),
}
RESULT_PATTERN = "backtest-result-*.zip"


@dataclass(frozen=True)
class ValidationIdentity:
    config_sha256: str
    strategy_sha256: str
    snapshot_sha256: str
    policy_sha256: str
    strategy_commit: str
    strategy: str
    strategy_path: str
    strategy_files: dict[str, str]
    accepted_pairs: tuple[str, ...]
    dry_run: bool


@dataclass(frozen=True)
class ValidationRun:
    verdict: str
    reasons: tuple[str, ...]
    manifest_path: Path
    report_path: Path
    checks: Checks
    folds: tuple[OosFold, ...]


@dataclass(frozen=True)
class FoldExport:
    trades: pd.DataFrame
    starting_balance: float
    timerange: str
    enable_protections: bool


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _effective_config(path: Path) -> dict[str, object]:
    config = load_from_files([str(path.resolve())])
    return deep_merge_dicts(environment_vars_to_dict(), config)


def _mapping_sha256(value: dict[str, object]) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _snapshot_sha256(datadir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(candidate for candidate in datadir.rglob("*") if candidate.is_file()):
        digest.update(path.relative_to(datadir).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _local_imports(path: Path, strategy_path: Path) -> list[Path]:
    tree = ast.parse(path.read_text(), filename=str(path))
    candidates: list[Path] = []
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        for module in modules:
            module_path = Path(*module.split("."))
            possible = [
                Path.cwd() / module_path.with_suffix(".py"),
                strategy_path / module_path.with_suffix(".py"),
                strategy_path / f"{module_path.name}.py",
            ]
            candidates.extend(
                candidate.resolve() for candidate in possible if candidate.is_file()
            )
    return candidates


def _strategy_files(strategy_file: Path, strategy_path: Path) -> dict[str, str]:
    pending = [strategy_file.resolve()]
    found: dict[str, str] = {}
    while pending:
        path = pending.pop()
        key = _display_path(path)
        if key in found:
            continue
        found[key] = _sha256(path)
        pending.extend(_local_imports(path, strategy_path.resolve()))
    return dict(sorted(found.items()))


def _combined_hash(files: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for name, file_hash in files.items():
        digest.update(name.encode())
        digest.update(file_hash.encode())
    return digest.hexdigest()


def collect_identity(
    config: Path,
    strategy_file: Path,
    datadir: Path | None,
    policy: Path,
    strategy: str,
    strategy_path: Path,
) -> ValidationIdentity:
    config_values = _effective_config(config)
    json.loads(policy.read_text())
    files = _strategy_files(strategy_file, strategy_path)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    return ValidationIdentity(
        config_sha256=_mapping_sha256(config_values),
        strategy_sha256=_combined_hash(files),
        snapshot_sha256=_snapshot_sha256(datadir) if datadir is not None else "",
        policy_sha256=_sha256(policy),
        strategy_commit=commit,
        strategy=strategy,
        strategy_path=_display_path(strategy_path),
        strategy_files=files,
        accepted_pairs=tuple(config_values.get("exchange", {}).get("pair_whitelist", ())),
        dry_run=config_values.get("dry_run") is True,
    )


def _pair_filename(pair: str) -> str:
    return pair.replace("/", "_").replace(":", "_")


def inspect_snapshot(
    datadir: Path,
    pairs: tuple[str, ...],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[dict[str, dict[str, object]], list[str], list[str]]:
    evidence: dict[str, dict[str, object]] = {}
    errors: list[str] = []
    warnings: list[str] = []
    starts: list[pd.Timestamp] = []
    ends: list[pd.Timestamp] = []
    required_columns = {"date", "open", "high", "low", "close", "volume"}

    for pair in pairs:
        for timeframe, interval in REQUIRED_TIMEFRAMES.items():
            matches = list(datadir.rglob(f"{_pair_filename(pair)}-{timeframe}-futures.feather"))
            label = f"{pair} {timeframe}"
            if len(matches) != 1:
                errors.append(
                    f"missing OHLCV for {label}"
                    if not matches
                    else f"ambiguous OHLCV for {label}"
                )
                continue
            path = matches[0]
            try:
                frame = pd.read_feather(path)
                if frame.empty or not required_columns.issubset(frame.columns):
                    raise ValueError("required OHLCV columns are missing or empty")
                dates = pd.to_datetime(frame["date"], utc=True, errors="raise")
                values = frame[["open", "high", "low", "close", "volume"]].apply(
                    pd.to_numeric, errors="raise"
                )
                if dates.isna().any() or not np.isfinite(values.to_numpy(dtype=float)).all():
                    raise ValueError("OHLCV contains missing or non-finite values")
                if dates.duplicated().any() or not dates.is_monotonic_increasing:
                    raise ValueError("candle dates are duplicated or not chronological")
                if (values["volume"] < 0).any():
                    raise ValueError("OHLCV volume is negative")
                if (values["high"] < values[["open", "close", "low"]].max(axis=1)).any():
                    raise ValueError("OHLCV high is invalid")
                if (values["low"] > values[["open", "close", "high"]].min(axis=1)).any():
                    raise ValueError("OHLCV low is invalid")
                in_window = dates[(dates >= start) & (dates < end)]
                if len(in_window) > 1 and (in_window.diff().dropna() > interval).any():
                    raise ValueError("OHLCV has candle gaps in the validation window")
                first, last = dates.iloc[0], dates.iloc[-1]
                starts.append(first)
                ends.append(last + interval)
                evidence[label] = {
                    "path": _display_path(path),
                    "rows": len(frame),
                    "start": first.isoformat(),
                    "end_exclusive": (last + interval).isoformat(),
                }
            except Exception as error:
                errors.append(f"invalid OHLCV for {label}: {error}")

    if starts and ends and not errors:
        common_start, common_end = max(starts), min(ends)
        evidence["common_interval"] = {
            "start": common_start.isoformat(),
            "end_exclusive": common_end.isoformat(),
        }
        if common_start > start or common_end < end:
            warnings.append(
                "common OHLCV history does not cover the complete frozen validation window"
            )
    return evidence, errors, warnings


def _freqtrade_command(args: argparse.Namespace, command: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "freqtrade",
        command,
        "--no-color",
        "--config",
        str(args.config),
        "--datadir",
        str(args.datadir),
        "--strategy",
        args.strategy,
        "--strategy-path",
        str(args.strategy_path),
    ]


def _command_text(result: object) -> str:
    return f"{getattr(result, 'stdout', '') or ''}\n{getattr(result, 'stderr', '') or ''}"


def _parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().casefold()
    if normalized in {"true", "yes", "1"}:
        return True
    if normalized in {"false", "no", "0"}:
        return False
    raise ValueError(f"invalid boolean {value!r}")


def run_correctness_checks(
    args: argparse.Namespace, executor: Executor, run_dir: Path
) -> tuple[Checks, dict[str, object], list[str]]:
    timerange = f"{pd.Timestamp(args.start):%Y%m%d}-{pd.Timestamp(args.end):%Y%m%d}"
    errors: list[str] = []
    evidence: dict[str, object] = {}

    lookahead_csv = run_dir / "lookahead.csv"
    lookahead_result = executor(
        _freqtrade_command(args, "lookahead-analysis")
        + [
            "--timerange",
            timerange,
            "--timeframe-detail",
            "1m",
            "--export",
            "none",
            "--lookahead-analysis-exportfilename",
            str(lookahead_csv),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    lookahead_transcript = run_dir / "lookahead.txt"
    lookahead_transcript.write_text(_command_text(lookahead_result))
    lookahead_ok = False
    if getattr(lookahead_result, "returncode", 1) != 0:
        errors.append("lookahead analysis command failed")
    else:
        try:
            rows = pd.read_csv(lookahead_csv)
            required = {
                "strategy",
                "has_bias",
                "total_signals",
                "biased_entry_signals",
                "biased_exit_signals",
                "biased_indicators",
            }
            if not required.issubset(rows.columns):
                raise ValueError("required columns are missing")
            matching = rows.loc[rows["strategy"] == args.strategy]
            if len(matching) != 1:
                raise ValueError("strategy result is missing or ambiguous")
            row = matching.iloc[0]
            total = int(row["total_signals"])
            biased_entries = int(row["biased_entry_signals"])
            biased_exits = int(row["biased_exit_signals"])
            indicators = (
                "" if pd.isna(row["biased_indicators"]) else str(row["biased_indicators"])
            )
            has_bias = _parse_bool(row["has_bias"])
            evidence["lookahead"] = {
                "artifact": _display_path(lookahead_csv),
                "transcript": _display_path(lookahead_transcript),
                "total_signals": total,
                "has_bias": has_bias,
                "biased_entry_signals": biased_entries,
                "biased_exit_signals": biased_exits,
                "biased_indicators": indicators,
            }
            if total <= 0:
                raise ValueError("no signals were analyzed")
            lookahead_ok = (
                not has_bias and biased_entries == 0 and biased_exits == 0 and not indicators
            )
            if not lookahead_ok:
                errors.append("lookahead analysis detected bias")
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append(f"lookahead analysis evidence is inconclusive: {error}")

    recursive_result = executor(
        _freqtrade_command(args, "recursive-analysis") + ["--timerange", timerange],
        check=False,
        capture_output=True,
        text=True,
    )
    recursive_text = _command_text(recursive_result)
    recursive_transcript = run_dir / "recursive.txt"
    recursive_transcript.write_text(recursive_text)
    no_lookahead = "No lookahead bias on indicators found." in recursive_text
    found_lookahead = "=> found lookahead in indicator" in recursive_text
    recursive_table = "Recursive Analysis" in recursive_text
    no_variance = "No variance on indicator(s) found due to recursive formula." in recursive_text
    conclusive = no_lookahead and (recursive_table or no_variance)
    evidence["recursive"] = {
        "transcript": _display_path(recursive_transcript),
        "conclusive": conclusive,
        "lookahead_detected": found_lookahead,
        "recursive_variance_reported": recursive_table,
    }
    recursive_ok = (
        getattr(recursive_result, "returncode", 1) == 0
        and conclusive
        and not found_lookahead
    )
    if getattr(recursive_result, "returncode", 1) != 0:
        errors.append("recursive analysis command failed")
    elif found_lookahead:
        errors.append("recursive analysis detected lookahead bias")
    elif not conclusive:
        errors.append("recursive analysis evidence is inconclusive")

    return Checks(lookahead_ok, recursive_ok, False), evidence, errors


def _load_exported_trades(path: Path, strategy: str) -> FoldExport:
    with zipfile.ZipFile(path) as archive:
        names = [
            name
            for name in archive.namelist()
            if name.endswith(".json") and "config" not in name
        ]
        if len(names) != 1:
            raise ValueError("trade export must contain exactly one result json")
        data = json.loads(archive.read(names[0]))
    strategies = data.get("strategy")
    if not isinstance(strategies, dict) or set(strategies) != {strategy}:
        raise ValueError("trade export strategy identity is missing or ambiguous")
    summary = strategies[strategy]
    if not isinstance(summary, dict) or not isinstance(summary.get("trades"), list):
        raise ValueError("trade export contains no trade list")
    starting_balance = float(summary.get("starting_balance"))
    if not math.isfinite(starting_balance) or starting_balance <= 0:
        raise ValueError("trade export has no valid starting balance")
    return FoldExport(
        trades=pd.DataFrame(summary["trades"]),
        starting_balance=starting_balance,
        timerange=str(summary.get("timerange", "")),
        enable_protections=summary.get("enable_protections") is True,
    )


def _stress_trades(
    trades: pd.DataFrame, starting_balance: float, policy: ValidationPolicy
) -> pd.DataFrame:
    required = {
        "pair",
        "enter_tag",
        "is_short",
        "profit_ratio",
        "profit_abs",
        "stake_amount",
        "open_date",
        "close_date",
    }
    if trades.empty:
        stressed = pd.DataFrame(
            columns=sorted(required | {"stressed_profit_abs", "portfolio_return"})
        )
        stressed.attrs["starting_balance"] = starting_balance
        return stressed
    if not required.issubset(trades.columns):
        raise ValueError("trade export is missing required attribution/equity fields")
    stressed = trades.copy()
    for column in ("profit_ratio", "profit_abs", "stake_amount"):
        stressed[column] = pd.to_numeric(stressed[column], errors="raise")
        if not np.isfinite(stressed[column].to_numpy(dtype=float)).all():
            raise ValueError(f"trade export contains non-finite {column}")
    if (stressed["stake_amount"] < 0).any():
        raise ValueError("trade export contains negative stake_amount")
    stressed["open_date"] = pd.to_datetime(stressed["open_date"], utc=True, errors="raise")
    stressed["close_date"] = pd.to_datetime(stressed["close_date"], utc=True, errors="raise")
    stressed = stressed.sort_values("close_date").reset_index(drop=True)
    stressed["stressed_profit_abs"] = stressed["profit_abs"] - (
        stressed["stake_amount"] * 2 * policy.slippage_per_side
    )
    stressed["portfolio_return"] = stressed["stressed_profit_abs"] / starting_balance
    stressed.attrs["starting_balance"] = starting_balance
    return stressed


def _fold_metrics(trades: pd.DataFrame) -> FoldMetrics:
    starting_balance = float(trades.attrs.get("starting_balance", float("nan")))
    if (
        not math.isfinite(starting_balance)
        or starting_balance <= 0
        or "profit_abs" not in trades
    ):
        raise ValueError("absolute-profit portfolio equity requires a valid starting balance")
    raw = pd.to_numeric(trades["profit_abs"], errors="raise")
    stressed = pd.to_numeric(
        trades["stressed_profit_abs"] if "stressed_profit_abs" in trades else raw,
        errors="raise",
    )
    if not np.isfinite(raw).all() or not np.isfinite(stressed).all():
        raise ValueError("portfolio profit contains non-finite values")
    equity = np.concatenate(
        ([starting_balance], starting_balance + stressed.cumsum().to_numpy())
    )
    if not np.isfinite(equity).all():
        raise ValueError("portfolio equity contains non-finite values")
    drawdown = 1 - equity / np.maximum.accumulate(equity)
    return FoldMetrics(
        trades=len(trades),
        net_profit=float(stressed.sum() / starting_balance),
        max_drawdown=float(drawdown.max()),
        raw_net_profit=float(raw.sum() / starting_balance),
        stressed_profit_abs=float(stressed.sum()),
    )


def _canonical_entry_tag(value: object) -> str:
    if not isinstance(value, str):
        return "untagged"
    signal_kind = value.split("|", 1)[0].strip().casefold()
    return signal_kind or "untagged"


def _attribution(trades: pd.DataFrame) -> tuple[dict[str, object], bool]:
    if trades.empty:
        return {
            "by_pair": {},
            "by_tag": {},
            "by_side": {},
            "single_source": True,
        }, False
    required = {"pair", "enter_tag", "is_short", "stressed_profit_abs"}
    if not required.issubset(trades.columns):
        raise ValueError("attribution fields are incomplete")
    normalized = trades.copy()
    normalized["entry_tag"] = normalized["enter_tag"].map(_canonical_entry_tag)
    normalized["side"] = np.where(normalized["is_short"].astype(bool), "short", "long")

    def grouped(column: str) -> dict[str, float]:
        values = normalized.groupby(column, dropna=False)["stressed_profit_abs"].sum()
        return {
            str(key): float(value)
            for key, value in sorted(values.items(), key=lambda item: str(item[0]))
        }

    by_pair, by_tag, by_side = grouped("pair"), grouped("entry_tag"), grouped("side")
    positive_pairs = sum(value > 0 for value in by_pair.values())
    positive_tags = sum(value > 0 for value in by_tag.values())
    single_source = positive_pairs < 2 or positive_tags < 2
    return {
        "by_pair": by_pair,
        "by_tag": by_tag,
        "by_side": by_side,
        "single_source": single_source,
    }, not single_source


def _validate_folds(folds: tuple[OosFold, ...], policy: ValidationPolicy) -> list[str]:
    warnings: list[str] = []
    if len(folds) < policy.required_folds:
        warnings.append(f"requires {policy.required_folds} OOS folds, found {len(folds)}")
    if any(
        folds[index].oos_end > folds[index + 1].oos_start
        for index in range(len(folds) - 1)
    ):
        raise ValueError("OOS folds overlap")
    if any(fold.oos_start >= fold.oos_end for fold in folds):
        raise ValueError("OOS fold has an invalid range")
    return warnings


def run_oos_folds(
    args: argparse.Namespace,
    executor: Executor,
    policy: ValidationPolicy,
    run_dir: Path,
) -> tuple[tuple[OosFold, ...], list[FoldMetrics], pd.DataFrame, list[str], list[str]]:
    folds = tuple(
        build_oos_folds(
            pd.Timestamp(args.start, tz="UTC"),
            pd.Timestamp(args.end, tz="UTC"),
            policy,
        )
    )
    metrics: list[FoldMetrics] = []
    frames: list[pd.DataFrame] = []
    artifacts: list[str] = []
    errors: list[str] = []
    warnings = _validate_folds(folds, policy)
    for index, fold in enumerate(folds, start=1):
        directory = run_dir / f"fold-{index:02d}"
        directory.mkdir()
        timerange = f"{fold.oos_start:%Y%m%d}-{fold.oos_end:%Y%m%d}"
        result = executor(
            _freqtrade_command(args, "backtesting")
            + [
                "--timerange",
                timerange,
                "--cache",
                "none",
                "--timeframe-detail",
                "1m",
                "--enable-protections",
                "--fee",
                str(policy.stress_fee),
                "--export",
                "trades",
                "--backtest-directory",
                str(directory),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        (directory / "freqtrade.txt").write_text(_command_text(result))
        if getattr(result, "returncode", 1) != 0:
            errors.append(f"fold {index} backtest failed")
            continue
        candidates = sorted(directory.glob(RESULT_PATTERN))
        if len(candidates) != 1:
            errors.append(
                f"fold {index} expected one timestamped ZIP result, found {len(candidates)}"
            )
            continue
        artifact = candidates[0]
        artifacts.append(_display_path(artifact))
        try:
            exported = _load_exported_trades(artifact, args.strategy)
            if exported.timerange != timerange:
                raise ValueError("trade export timerange does not match fold")
            if not exported.enable_protections:
                raise ValueError("trade export did not enable protections")
            trades = _stress_trades(exported.trades, exported.starting_balance, policy)
            metrics.append(_fold_metrics(trades))
            frames.append(trades)
        except Exception as error:
            errors.append(f"fold {index} trade export is invalid: {error}")
    all_trades = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return folds, metrics, all_trades, artifacts, errors + warnings


def _identity_reasons(identity: ValidationIdentity, approved: object) -> list[str]:
    if not isinstance(approved, dict):
        return ["approved baseline identity is required"]
    reasons: list[str] = []
    for field, value in asdict(identity).items():
        approved_value = approved.get(field)
        if field == "accepted_pairs" and isinstance(approved_value, list):
            approved_value = tuple(approved_value)
        if approved_value != value:
            label = (
                "strategy"
                if field in {"strategy_sha256", "strategy_files"}
                else field.removesuffix("_sha256")
            )
            reason = f"{label} identity does not match approved baseline"
            if reason not in reasons:
                reasons.append(reason)
    return reasons


def _load_approved_identity(value: object) -> object:
    if isinstance(value, Path):
        return json.loads(value.read_text())
    return value


def _write_result(
    run_dir: Path,
    *,
    identity: ValidationIdentity | None,
    checks: Checks,
    folds: tuple[OosFold, ...] = (),
    fold_metrics: list[FoldMetrics] | None = None,
    bootstrap: BootstrapSummary | None = None,
    policy: ValidationPolicy | None = None,
    attribution: dict[str, object] | None = None,
    correctness_evidence: dict[str, object] | None = None,
    data_coverage: dict[str, object] | None = None,
    backtest_artifacts: list[str] | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> ValidationRun:
    fold_metrics = fold_metrics or []
    errors = errors or []
    warnings = warnings or []
    bootstrap_gate_eligible = bool(
        policy
        and bootstrap
        and len(fold_metrics) >= policy.required_folds
        and sum(metric.trades for metric in fold_metrics) >= policy.min_oos_trades
    )
    p95_dd = bootstrap.p95_max_drawdown if bootstrap_gate_eligible and bootstrap else None
    if errors or policy is None:
        verdict = "FAIL"
    else:
        verdict = evaluate_verdict(checks, fold_metrics, p95_dd, policy)
        if verdict == "PASS" and warnings:
            verdict = "WARN"
    reasons = list(dict.fromkeys([*errors, *warnings]))
    if verdict == "FAIL" and not reasons:
        reasons.append("validation evidence is invalid or incomplete")

    manifest_path = run_dir / "manifest.json"
    report_path = run_dir / "report.md"
    manifest = {
        **(asdict(identity) if identity else {}),
        "checks": asdict(checks),
        "correctness_evidence": correctness_evidence or {},
        "data_coverage": data_coverage or {},
        "folds": [asdict(fold) for fold in folds],
        "fold_metrics": [asdict(metric) for metric in fold_metrics],
        "backtest_artifacts": backtest_artifacts or [],
        "bootstrap_summary": asdict(bootstrap) if bootstrap else None,
        "bootstrap_gate_eligible": bootstrap_gate_eligible,
        "attribution": attribution or {},
        "policy": asdict(policy) if policy else None,
        "verdict": verdict,
        "errors": errors,
        "warnings": warnings,
        "reasons": reasons,
    }
    manifest_path.write_text(
        json.dumps(manifest, default=str, indent=2, allow_nan=False) + "\n"
    )
    report_path.write_text(
        "# Baseline validation\n\n"
        f"Verdict: `{verdict}`\n\n"
        + ("\n".join(f"- {reason}" for reason in reasons) or "- No blocking findings.")
        + "\n"
    )
    return ValidationRun(verdict, tuple(reasons), manifest_path, report_path, checks, folds)


def _new_run_dir(args: argparse.Namespace) -> Path:
    base = Path(args.runs_dir) / args.run_id
    candidate = base
    suffix = 1
    while candidate.exists():
        candidate = base.with_name(f"{base.name}-{suffix:03d}")
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def run_validation(args: argparse.Namespace, executor: Executor = subprocess.run) -> ValidationRun:
    run_dir = _new_run_dir(args)
    try:
        policy_path = Path(args.policy)
        policy = ValidationPolicy.from_path(policy_path)
        config = _effective_config(Path(args.config))
        identity = collect_identity(
            Path(args.config),
            Path(args.strategy_file),
            Path(args.datadir),
            policy_path,
            args.strategy,
            Path(args.strategy_path),
        )
        errors = _identity_reasons(
            identity, _load_approved_identity(getattr(args, "approved_identity", None))
        )
        if tuple(config.get("exchange", {}).get("pair_whitelist", ())) != policy.accepted_pairs:
            errors.append("config basket does not match accepted policy basket")
        start = pd.Timestamp(args.start, tz="UTC")
        end = pd.Timestamp(args.end, tz="UTC")
        if start >= end:
            errors.append("validation window is invalid")
        coverage, coverage_errors, warnings = inspect_snapshot(
            Path(args.datadir), policy.accepted_pairs, start, end
        )
        errors.extend(coverage_errors)
        if errors:
            return _write_result(
                run_dir,
                identity=identity,
                checks=Checks(False, False, False),
                policy=policy,
                data_coverage=coverage,
                errors=errors,
                warnings=warnings,
            )

        execution_args = argparse.Namespace(**vars(args))
        common_interval = coverage.get("common_interval", {})
        common_start = pd.Timestamp(common_interval["start"]).ceil("D")
        common_end = pd.Timestamp(common_interval["end_exclusive"]).floor("D")
        execution_start = max(start, common_start)
        execution_end = min(end, common_end)
        if execution_start >= execution_end:
            errors.append("common OHLCV history contains no complete UTC validation day")
            return _write_result(
                run_dir,
                identity=identity,
                checks=Checks(False, False, False),
                policy=policy,
                data_coverage=coverage,
                errors=errors,
                warnings=warnings,
            )
        execution_args.start = execution_start.isoformat()
        execution_args.end = execution_end.isoformat()

        checks, correctness, correctness_errors = run_correctness_checks(
            execution_args, executor, run_dir
        )
        errors.extend(correctness_errors)
        folds, metrics, trades, artifacts, fold_findings = run_oos_folds(
            execution_args, executor, policy, run_dir
        )
        for finding in fold_findings:
            if "requires " in finding and "OOS folds" in finding:
                warnings.append(finding)
            else:
                errors.append(finding)

        attribution, attribution_ok = _attribution(trades)
        checks = Checks(checks.lookahead, checks.recursive, attribution_ok)
        total_trades = sum(metric.trades for metric in metrics)
        if total_trades < policy.min_oos_trades:
            warnings.append(
                f"requires {policy.min_oos_trades} aggregate OOS trades, found {total_trades}"
            )
        if attribution.get("single_source") and not trades.empty:
            warnings.append("OOS profit attribution has a single pair or entry-tag source")

        bootstrap: BootstrapSummary | None = None
        bootstrap_eligible = (
            total_trades >= policy.min_oos_trades
            and len(metrics) >= policy.required_folds
        )
        if not trades.empty:
            try:
                bootstrap = bootstrap_equity_paths(trades, policy)
            except Exception as error:
                errors.append(f"bootstrap evaluation failed: {error}")
        if any(metric.max_drawdown > policy.max_drawdown for metric in metrics):
            errors.append("OOS drawdown exceeds policy")
        if metrics and sum(metric.net_profit for metric in metrics) < 0:
            errors.append("aggregate stressed OOS profit is negative")
        if bootstrap_eligible and bootstrap and bootstrap.p95_max_drawdown > policy.max_drawdown:
            errors.append("bootstrap p95 drawdown exceeds policy")

        return _write_result(
            run_dir,
            identity=identity,
            checks=checks,
            folds=folds,
            fold_metrics=metrics,
            bootstrap=bootstrap,
            policy=policy,
            attribution=attribution,
            correctness_evidence=correctness,
            data_coverage=coverage,
            backtest_artifacts=artifacts,
            errors=errors,
            warnings=warnings,
        )
    except Exception as error:
        return _write_result(
            run_dir,
            identity=None,
            checks=Checks(False, False, False),
            errors=[f"validation runner failed closed: {type(error).__name__}: {error}"],
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--strategy-file", type=Path, required=True)
    parser.add_argument("--datadir", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--strategy-path", type=Path, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument(
        "--runs-dir", type=Path, default=Path(".research/smc_fvg_pinbar/runs")
    )
    parser.add_argument(
        "--run-id", default=datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    )
    parser.add_argument("--approved-identity", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    result = run_validation(parse_args())
    print(f"{result.verdict}: {result.manifest_path}")
    return 0 if result.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
