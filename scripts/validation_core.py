"""Pure policy, fold, and verdict primitives for baseline validation."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd

from research_runtime import paths


@dataclass(frozen=True)
class ValidationPolicy:
    in_sample_days: int
    oos_days: int
    required_folds: int
    min_oos_trades: int
    max_drawdown: float
    stress_fee: float
    slippage_per_side: float
    bootstrap_seed: int
    bootstrap_samples: int
    bootstrap_block: str
    accepted_pairs: tuple[str, ...] = ()
    min_positive_oos_folds: int = 2

    def __post_init__(self):
        for name in ("in_sample_days", "oos_days", "required_folds", "min_oos_trades", "bootstrap_samples"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"invalid policy {name}")
        if (
            not isinstance(self.min_positive_oos_folds, int)
            or isinstance(self.min_positive_oos_folds, bool)
            or not 1 <= self.min_positive_oos_folds <= self.required_folds
        ):
            raise ValueError("invalid policy min_positive_oos_folds")
        for name in ("max_drawdown", "stress_fee", "slippage_per_side"):
            value = getattr(self, name)
            if not math.isfinite(value) or not 0 <= value < 1:
                raise ValueError(f"invalid policy {name}")
        if self.bootstrap_block != "2W":
            raise ValueError("policy requires anchored 2W blocks")

    @classmethod
    def from_path(cls, path: Path) -> "ValidationPolicy":
        values = json.loads(path.read_text())
        basket = values.get("accepted_basket", values.get("accepted_pairs", ()))
        return cls(
            in_sample_days=values["in_sample_days"],
            oos_days=values["oos_days"],
            required_folds=values["required_folds"],
            min_oos_trades=values["min_oos_trades"],
            max_drawdown=values["max_drawdown"],
            stress_fee=values["stress_fee"],
            slippage_per_side=values["slippage_per_side"],
            bootstrap_seed=values["bootstrap_seed"],
            bootstrap_samples=values["bootstrap_samples"],
            bootstrap_block=values["bootstrap_block"],
            accepted_pairs=tuple(basket),
            min_positive_oos_folds=values.get("min_positive_oos_folds", 2),
        )


@dataclass(frozen=True)
class OosFold:
    in_sample_start: pd.Timestamp
    in_sample_end: pd.Timestamp
    oos_start: pd.Timestamp
    oos_end: pd.Timestamp


@dataclass(frozen=True)
class Checks:
    lookahead: bool
    recursive: bool
    attribution: bool


@dataclass(frozen=True)
class FoldMetrics:
    trades: int
    net_profit: float
    max_drawdown: float
    raw_net_profit: float | None = None
    stressed_profit_abs: float | None = None
    complete_plan: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BootstrapSummary:
    p95_max_drawdown: float
    p05_net_profit: float
    p95_losing_streak: float


EXIT_REASON_TAXONOMY = (
    "PROTECTIVE_STOP",
    "PROFIT_TARGET",
    "TIME_EXIT",
    "TRAILING_EXIT",
    "REGIME_EXIT",
    "SIGNAL_EXIT",
    "EMERGENCY_EXIT",
    "LIQUIDATION",
)


def _metric_summary(values: list[float]) -> dict[str, object]:
    if not values:
        return {"count": 0, "mean": None, "p95": None, "min": None, "max": None}
    array = np.asarray(values, dtype=float)
    return {
        "count": len(values),
        "mean": float(array.mean()),
        "p95": float(np.percentile(array, 95)),
        "min": float(array.min()),
        "max": float(array.max()),
    }


def _numeric_values(frame: pd.DataFrame, names: tuple[str, ...]) -> list[float]:
    for name in names:
        if name not in frame.columns:
            continue
        values = pd.to_numeric(frame[name], errors="coerce")
        return [float(value) for value in values if math.isfinite(float(value))]
    return []


def _reason(value: object) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    normalized = str(value).strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "STOPLOSS": "PROTECTIVE_STOP",
        "STOP_LOSS": "PROTECTIVE_STOP",
        "STOP": "PROTECTIVE_STOP",
        "ROI": "PROFIT_TARGET",
        "PROFIT": "PROFIT_TARGET",
        "PROFIT_EXIT": "PROFIT_TARGET",
        "CUSTOM_ROI": "PROFIT_TARGET",
        "TIME": "TIME_EXIT",
        "TIMEOUT": "TIME_EXIT",
        "TIME_EXIT": "TIME_EXIT",
        "TRAILING_STOP_LOSS": "TRAILING_EXIT",
        "TRAILING": "TRAILING_EXIT",
        "TRAILING_EXIT": "TRAILING_EXIT",
        "REGIME": "REGIME_EXIT",
        "REGIME_EXIT": "REGIME_EXIT",
        "SIGNAL": "SIGNAL_EXIT",
        "SIGNAL_EXIT": "SIGNAL_EXIT",
        "EMERGENCY": "EMERGENCY_EXIT",
        "EMERGENCY_EXIT": "EMERGENCY_EXIT",
        "LIQUIDATION": "LIQUIDATION",
    }
    return aliases.get(normalized, normalized if normalized in EXIT_REASON_TAXONOMY else None)


def complete_plan_metrics(
    trades: pd.DataFrame, policy: ValidationPolicy
) -> dict[str, object]:
    """Compute deterministic diagnostics from immutable trade-export fields.

    These metrics are descriptive unless the caller explicitly marks the run as
    identity-bound. Missing ledger fields are represented as zero coverage rather
    than inferred from a convenient but unverifiable proxy.
    """
    count = len(trades)
    reasons = {reason: 0 for reason in EXIT_REASON_TAXONOMY}
    reason_column = next(
        (name for name in ("exit_reason", "sell_reason", "close_reason") if name in trades.columns),
        None,
    )
    recognized = 0
    if reason_column:
        for value in trades[reason_column]:
            reason = _reason(value)
            if reason is not None:
                reasons[reason] += 1
                recognized += 1

    risk_values: list[float] = []
    realized_values: list[float] = []
    risk_column = next(
        (name for name in ("planned_loss", "planned_risk", "initial_risk_abs") if name in trades.columns),
        None,
    )
    realized_column = next(
        (name for name in ("realized_r", "net_realized_r", "r_multiple") if name in trades.columns),
        None,
    )
    if risk_column:
        risk_series = pd.to_numeric(trades[risk_column], errors="coerce")
        for index, risk in risk_series.items():
            if not math.isfinite(float(risk)) or float(risk) <= 0:
                continue
            realized = None
            if realized_column:
                value = pd.to_numeric(pd.Series([trades.loc[index, realized_column]]), errors="coerce").iloc[0]
                if math.isfinite(float(value)):
                    realized = float(value)
            elif "stressed_profit_abs" in trades.columns:
                value = pd.to_numeric(pd.Series([trades.loc[index, "stressed_profit_abs"]]), errors="coerce").iloc[0]
                if math.isfinite(float(value)):
                    realized = float(value) / float(risk)
            if realized is not None:
                risk_values.append(float(risk))
                realized_values.append(realized)

    durations: list[float] = []
    if {"open_date", "close_date"}.issubset(trades.columns):
        opened = pd.to_datetime(trades["open_date"], utc=True, errors="coerce")
        closed = pd.to_datetime(trades["close_date"], utc=True, errors="coerce")
        durations = [
            float((end - start).total_seconds())
            for start, end in zip(opened, closed)
            if not pd.isna(start) and not pd.isna(end) and end >= start
        ]

    fees: list[float] = []
    for name in ("fee_open", "fee_close", "fee", "fees", "funding_fees"):
        if name in trades.columns:
            fees.extend(_numeric_values(trades, (name,)))
    slippage = 0.0
    if "stake_amount" in trades.columns:
        stakes = pd.to_numeric(trades["stake_amount"], errors="coerce")
        slippage = float(stakes[stakes.apply(math.isfinite)].sum()) * 2 * policy.slippage_per_side

    concurrent_planned_risk = None
    if risk_values and {"open_date", "close_date"}.issubset(trades.columns) and risk_column:
        events: list[tuple[pd.Timestamp, int, float]] = []
        for index, risk in zip(trades.index, pd.to_numeric(trades[risk_column], errors="coerce")):
            if not math.isfinite(float(risk)) or float(risk) <= 0:
                continue
            opened = pd.to_datetime(trades.loc[index, "open_date"], utc=True, errors="coerce")
            closed = pd.to_datetime(trades.loc[index, "close_date"], utc=True, errors="coerce")
            if pd.isna(opened) or pd.isna(closed) or closed < opened:
                continue
            events.extend(((opened, 1, float(risk)), (closed, -1, float(risk))))
        active = 0.0
        peak = 0.0
        for _, direction, risk in sorted(events, key=lambda item: (item[0], 0 if item[1] == 1 else 1)):
            active += direction * risk
            peak = max(peak, active)
        concurrent_planned_risk = float(peak) if events else None

    stop_column = next(
        (name for name in ("initial_stop_rate", "planned_stop_rate", "stop_rate") if name in trades.columns),
        None,
    )
    stop_failures = count
    if stop_column and {"open_rate", "is_short"}.issubset(trades.columns):
        stop_failures = 0
        for index, stop in pd.to_numeric(trades[stop_column], errors="coerce").items():
            entry = pd.to_numeric(pd.Series([trades.loc[index, "open_rate"]]), errors="coerce").iloc[0]
            if not math.isfinite(float(stop)) or not math.isfinite(float(entry)) or float(stop) <= 0 or float(entry) <= 0:
                stop_failures += 1
            elif bool(trades.loc[index, "is_short"]):
                stop_failures += int(float(stop) <= float(entry))
            else:
                stop_failures += int(float(stop) >= float(entry))

    explanation_column = next(
        (name for name in ("emergency_explanation", "exit_explanation") if name in trades.columns),
        None,
    )
    unexplained_emergency = 0
    if reason_column:
        for index, value in trades[reason_column].items():
            if _reason(value) == "EMERGENCY_EXIT":
                explanation = trades.loc[index, explanation_column] if explanation_column else None
                unexplained_emergency += int(explanation is None or not str(explanation).strip())

    loss_overruns = [max(0.0, -value - 1.0) for value in realized_values]
    exit_coverage = recognized / count if count else 0.0
    risk_coverage = len(risk_values) / count if count else 0.0
    turnover_values = _numeric_values(trades, ("notional", "turnover"))
    if not turnover_values and "stake_amount" in trades.columns:
        turnover_values = _numeric_values(trades, ("stake_amount",))
    turnover = float(sum(turnover_values))
    time_in_market = {"seconds": float(sum(durations)) if durations else 0.0}
    return {
        "exit_reason_counts": reasons,
        "exit_coverage": float(exit_coverage),
        "risk_ledger": {
            "coverage": float(risk_coverage),
            "rows": len(risk_values),
            "planned_loss": float(sum(risk_values)) if risk_values else None,
            "concurrent_planned_risk": concurrent_planned_risk,
        },
        "net_realized_r": float(sum(realized_values)) if realized_values else None,
        "loss_overrun_p95": float(np.percentile(loss_overruns, 95)) if loss_overruns else None,
        "costs": {
            "fees": float(sum(fees)),
            "slippage": float(slippage),
            "total": float(sum(fees) + slippage),
            "turnover": turnover,
            "cost_burden": float((sum(fees) + slippage) / turnover) if turnover else None,
        },
        "turnover": turnover,
        "time_in_market": time_in_market,
        "holding_duration": {
            **_metric_summary(durations),
            "total_seconds": float(sum(durations)) if durations else 0.0,
        },
        "mae_mfe": {
            "mae": _metric_summary(_numeric_values(trades, ("mae", "max_adverse_excursion"))),
            "mfe": _metric_summary(_numeric_values(trades, ("mfe", "max_favorable_excursion"))),
        },
        "risk_safety": {
            "wrong_side_or_missing_initial_stops": stop_failures,
            "missing_exit_plans": count - recognized,
            "liquidation_events": reasons["LIQUIDATION"],
            "unexplained_emergency_exits": unexplained_emergency,
        },
    }


class ValidationStateStore:
    def __init__(self, path: Path | None = None):
        self.path = path or paths.validation_state_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS current_state (
                    scope TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    metrics TEXT NOT NULL,
                    lock_until TEXT,
                    run_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS state_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope TEXT NOT NULL,
                    state TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    metrics TEXT NOT NULL,
                    lock_until TEXT,
                    run_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def transition(
        self,
        scope: str,
        state: str,
        reason: str,
        metrics: dict,
        lock_until: str | None,
        run_id: str,
    ) -> None:
        with sqlite3.connect(self.path) as connection:
            current = connection.execute(
                "SELECT state FROM current_state WHERE scope = ?", (scope,)
            ).fetchone()
            if state not in {"ACTIVE", "YELLOW", "PAIR_OR_SIDE_LOCKED", "PAUSED"}:
                raise ValueError("invalid validation state")
            if current and current[0] == "PAUSED" and state != "PAUSED" and reason != "review-approved":
                raise ValueError("review approval is required to reopen a paused state")

            timestamp = datetime.now(timezone.utc).isoformat()
            values = (
                scope,
                state,
                reason,
                json.dumps(metrics, sort_keys=True),
                lock_until,
                run_id,
                timestamp,
            )
            connection.execute(
                """
                INSERT INTO state_events
                    (scope, state, reason, metrics, lock_until, run_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            connection.execute(
                """
                INSERT INTO current_state
                    (scope, state, reason, metrics, lock_until, run_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope) DO UPDATE SET
                    state = excluded.state,
                    reason = excluded.reason,
                    metrics = excluded.metrics,
                    lock_until = excluded.lock_until,
                    run_id = excluded.run_id,
                    updated_at = excluded.updated_at
                """,
                values,
            )

    def current(self, scope: str) -> dict[str, object] | None:
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM current_state WHERE scope = ?", (scope,)
            ).fetchone()
            return None if row is None else dict(row)


def build_oos_folds(
    start: pd.Timestamp, end: pd.Timestamp, policy: ValidationPolicy
) -> list[OosFold]:
    cursor = start + pd.Timedelta(days=policy.in_sample_days)
    folds: list[OosFold] = []
    while cursor + pd.Timedelta(days=policy.oos_days) <= end:
        folds.append(OosFold(start, cursor, cursor, cursor + pd.Timedelta(days=policy.oos_days)))
        cursor += pd.Timedelta(days=policy.oos_days)
    return folds


def time_blocks(dates: pd.Series, frequency: str = "2W") -> pd.Series:
    """Non-overlapping 14-day blocks anchored at 1970-01-05 00:00 UTC."""
    if frequency != "2W":
        raise ValueError("only anchored 2W blocks are supported")
    dates = pd.to_datetime(dates, utc=True, errors="raise")
    if dates.isna().any():
        raise ValueError("missing block date")
    return (dates - pd.Timestamp("1970-01-05", tz="UTC")) // pd.Timedelta(days=14)


def bootstrap_equity_paths(trades: pd.DataFrame, policy: ValidationPolicy) -> BootstrapSummary:
    if trades.empty:
        raise ValueError("bootstrap requires at least one trade")
    if not {"open_date", "profit_ratio"}.issubset(trades.columns):
        raise ValueError("bootstrap requires open_date and profit_ratio")

    grouped = trades.copy()
    date_column = "close_date" if "close_date" in grouped else "open_date"
    grouped[date_column] = pd.to_datetime(grouped[date_column], utc=True, errors="raise")
    grouped = grouped.sort_values(date_column)
    grouped["block"] = time_blocks(grouped[date_column], policy.bootstrap_block)
    # Runner supplies stressed absolute portfolio P&L / initial wallet; monitor's
    # legacy ratio-only exports retain the historical compounded-return model.
    portfolio = "portfolio_return" in grouped
    column = "portfolio_return" if portfolio else "profit_ratio"
    values = pd.to_numeric(grouped[column], errors="raise")
    if not np.isfinite(values).all():
        raise ValueError("non-finite bootstrap returns")
    blocks = grouped["block"].unique()
    returns_by_block = {
        block: grouped.loc[grouped["block"] == block, column].to_numpy(dtype=float)
        for block in blocks
    }

    rng = np.random.default_rng(policy.bootstrap_seed)
    max_drawdowns = np.empty(policy.bootstrap_samples)
    net_profits = np.empty(policy.bootstrap_samples)
    losing_streaks = np.empty(policy.bootstrap_samples)
    stressed_cost = 0 if portfolio else 2 * policy.slippage_per_side
    for index in range(policy.bootstrap_samples):
        chosen = rng.choice(blocks, size=len(blocks), replace=True)
        returns = np.concatenate([returns_by_block[block] for block in chosen]) - stressed_cost
        equity = np.concatenate(([1.0], 1 + np.cumsum(returns) if portfolio else np.cumprod(1 + returns)))
        if not np.isfinite(equity).all():
            raise ValueError("non-finite bootstrap equity")
        max_drawdowns[index] = (1 - equity / np.maximum.accumulate(equity)).max()
        net_profits[index] = equity[-1] - 1
        losses = returns < 0
        boundaries = np.diff(np.concatenate(([False], losses, [False])).astype(int))
        starts = np.flatnonzero(boundaries == 1)
        ends = np.flatnonzero(boundaries == -1)
        losing_streaks[index] = max(ends - starts, default=0)

    return BootstrapSummary(
        p95_max_drawdown=float(np.percentile(max_drawdowns, 95)),
        p05_net_profit=float(np.percentile(net_profits, 5)),
        p95_losing_streak=float(np.percentile(losing_streaks, 95)),
    )


def evaluate_verdict(
    checks: Checks,
    folds: list[FoldMetrics],
    p95_dd: float | None,
    policy: ValidationPolicy,
) -> str:
    if not checks.lookahead or not checks.recursive:
        return "FAIL"
    if any(not all(math.isfinite(v) for v in (f.trades, f.net_profit, f.max_drawdown))
           or f.trades < 0 or f.max_drawdown < 0 for f in folds):
        return "FAIL"
    if p95_dd is not None and (not math.isfinite(p95_dd) or p95_dd < 0):
        return "FAIL"
    if any(fold.max_drawdown > policy.max_drawdown for fold in folds):
        return "FAIL"
    if p95_dd is not None and p95_dd > policy.max_drawdown:
        return "FAIL"
    if folds and sum(fold.net_profit for fold in folds) < 0:
        return "FAIL"
    if len(folds) < policy.required_folds or sum(fold.trades for fold in folds) < policy.min_oos_trades:
        return "WARN"
    if folds and sum(fold.net_profit for fold in folds) == 0:
        return "FAIL"
    if sum(fold.net_profit > 0 for fold in folds) < policy.min_positive_oos_folds:
        return "FAIL"
    if p95_dd is None:
        return "FAIL"
    if not checks.attribution:
        return "WARN"
    return "PASS"
