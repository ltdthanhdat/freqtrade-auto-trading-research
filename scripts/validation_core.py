"""Pure policy, fold, and verdict primitives for baseline validation."""

from dataclasses import dataclass
import json
from pathlib import Path

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


@dataclass(frozen=True)
class BootstrapSummary:
    p95_max_drawdown: float
    p05_net_profit: float
    p95_losing_streak: float


def build_oos_folds(
    start: pd.Timestamp, end: pd.Timestamp, policy: ValidationPolicy
) -> list[OosFold]:
    cursor = start + pd.Timedelta(days=policy.in_sample_days)
    folds: list[OosFold] = []
    while cursor + pd.Timedelta(days=policy.oos_days) <= end:
        folds.append(OosFold(start, cursor, cursor, cursor + pd.Timedelta(days=policy.oos_days)))
        cursor += pd.Timedelta(days=policy.oos_days)
    return folds


def bootstrap_equity_paths(trades: pd.DataFrame, policy: ValidationPolicy) -> BootstrapSummary:
    if trades.empty:
        raise ValueError("bootstrap requires at least one trade")
    if not {"open_date", "profit_ratio"}.issubset(trades.columns):
        raise ValueError("bootstrap requires open_date and profit_ratio")

    grouped = trades.copy()
    open_dates = pd.to_datetime(grouped["open_date"])
    if getattr(open_dates.dt, "tz", None) is not None:
        open_dates = open_dates.dt.tz_localize(None)
    grouped["block"] = open_dates.dt.to_period(policy.bootstrap_block)
    blocks = grouped["block"].unique()
    returns_by_block = {
        block: grouped.loc[grouped["block"] == block, "profit_ratio"].to_numpy(dtype=float)
        for block in blocks
    }

    rng = np.random.default_rng(policy.bootstrap_seed)
    max_drawdowns = np.empty(policy.bootstrap_samples)
    net_profits = np.empty(policy.bootstrap_samples)
    losing_streaks = np.empty(policy.bootstrap_samples)
    stressed_cost = 2 * policy.slippage_per_side
    for index in range(policy.bootstrap_samples):
        chosen = rng.choice(blocks, size=len(blocks), replace=True)
        returns = np.concatenate([returns_by_block[block] for block in chosen]) - stressed_cost
        equity = np.concatenate(([1.0], np.cumprod(1 + returns)))
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
    p95_dd: float,
    policy: ValidationPolicy,
) -> str:
    if not all((checks.lookahead, checks.recursive, checks.attribution)):
        return "FAIL"
    if any(fold.max_drawdown > policy.max_drawdown for fold in folds):
        return "FAIL"
    if p95_dd > policy.max_drawdown:
        return "FAIL"
    if sum(fold.net_profit for fold in folds) <= 0:
        return "FAIL"
    if len(folds) < policy.required_folds or sum(fold.trades for fold in folds) < policy.min_oos_trades:
        return "WARN"
    return "PASS"
