"""Pure policy, fold, and verdict primitives for baseline validation."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd


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

    def __post_init__(self):
        for name in ("in_sample_days", "oos_days", "required_folds", "min_oos_trades", "bootstrap_samples"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"invalid policy {name}")
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


@dataclass(frozen=True)
class BootstrapSummary:
    p95_max_drawdown: float
    p05_net_profit: float
    p95_losing_streak: float


class ValidationStateStore:
    def __init__(self, path: Path):
        self.path = path
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
    if p95_dd is None:
        return "FAIL"
    if not checks.attribution:
        return "WARN"
    return "PASS"
