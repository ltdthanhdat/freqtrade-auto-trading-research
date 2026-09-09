"""Pure policy, fold, and verdict primitives for baseline validation."""

from dataclasses import dataclass
import json
from pathlib import Path

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


def build_oos_folds(
    start: pd.Timestamp, end: pd.Timestamp, policy: ValidationPolicy
) -> list[OosFold]:
    cursor = start + pd.Timedelta(days=policy.in_sample_days)
    folds: list[OosFold] = []
    while cursor + pd.Timedelta(days=policy.oos_days) <= end:
        folds.append(OosFold(start, cursor, cursor, cursor + pd.Timedelta(days=policy.oos_days)))
        cursor += pd.Timedelta(days=policy.oos_days)
    return folds


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
