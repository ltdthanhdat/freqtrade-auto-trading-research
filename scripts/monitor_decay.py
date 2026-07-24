from __future__ import annotations

import argparse
import json
import sqlite3
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_BLOCK_FREQ = "2W"
DEFAULT_ALERT_PERCENTILE = 5.0
DEFAULT_N_BOOT = 20000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare a recent rolling window of trades (from a live/demo sqlite DB, "
            "or from a backtest export) against a block-bootstrap null distribution "
            "built from a longer baseline backtest. Flags when recent performance "
            "falls outside the normal range of variation seen in the baseline."
        )
    )
    parser.add_argument(
        "--baseline",
        required=True,
        help=(
            "Freqtrade backtest result zip (exported with `--export trades`) used "
            "to build the baseline null distribution. Should span the longest "
            "reliable history available, not just a favorable window."
        ),
    )
    parser.add_argument(
        "--db",
        help=(
            "Path to a Freqtrade sqlite trade DB (tradesv3.demo.sqlite / "
            "tradesv3.live.sqlite) to pull the recent rolling window from. "
            "Mutually exclusive with --recent-backtest."
        ),
    )
    parser.add_argument(
        "--recent-backtest",
        help=(
            "Freqtrade backtest result zip to use as the 'recent window' instead "
            "of a live DB (useful for testing against a specific historical "
            "window, e.g. last-month backtests)."
        ),
    )
    parser.add_argument(
        "--window",
        type=int,
        default=63,
        help="Number of most recent closed trades to evaluate (default: 63, ~1 month at this strategy's cadence).",
    )
    parser.add_argument(
        "--block-freq",
        default=DEFAULT_BLOCK_FREQ,
        help="Pandas offset alias for the block size used in block-bootstrap (default: 2W).",
    )
    parser.add_argument(
        "--alert-percentile",
        type=float,
        default=DEFAULT_ALERT_PERCENTILE,
        help="Alert if the recent window's win rate falls at or below this percentile of the baseline null distribution (default: 5).",
    )
    parser.add_argument(
        "--n-boot",
        type=int,
        default=DEFAULT_N_BOOT,
        help="Number of block-bootstrap resamples (default: 20000).",
    )
    parser.add_argument("--seed", type=int, default=7, help="RNG seed for reproducibility.")
    args = parser.parse_args()

    if bool(args.db) == bool(args.recent_backtest):
        parser.error("Specify exactly one of --db or --recent-backtest.")

    return args


def load_backtest_trades(zip_path: str) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.endswith(".json") and "config" not in n]
        if not names:
            raise ValueError(f"No trade-result json found inside {zip_path}")
        data = json.loads(z.read(names[0]))

    strat_key = next(iter(data["strategy"]))
    trades = pd.DataFrame(data["strategy"][strat_key]["trades"])
    if trades.empty:
        raise ValueError(f"No closed trades found in {zip_path}")
    trades["open_date"] = pd.to_datetime(trades["open_date"])
    trades["is_win"] = trades["profit_abs"] > 0
    return trades[["open_date", "pair", "profit_abs", "profit_ratio", "is_win"]]


def load_db_trades(db_path: str) -> pd.DataFrame:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        trades = pd.read_sql_query(
            """
            SELECT open_date, pair, close_profit_abs AS profit_abs, close_profit AS profit_ratio
            FROM trades
            WHERE is_open = 0 AND close_profit IS NOT NULL
            ORDER BY close_date ASC
            """,
            conn,
        )
    finally:
        conn.close()

    if trades.empty:
        raise ValueError(f"No closed trades found in {db_path}")
    trades["open_date"] = pd.to_datetime(trades["open_date"])
    trades["is_win"] = trades["profit_abs"] > 0
    return trades


def build_block_null_distribution(
    baseline: pd.DataFrame,
    window: int,
    block_freq: str,
    n_boot: int,
    seed: int,
) -> np.ndarray:
    baseline = baseline.copy()
    baseline["block"] = baseline["open_date"].dt.tz_localize(None).dt.to_period(block_freq)
    blocks = baseline["block"].unique()
    block_wins = {b: baseline.loc[baseline["block"] == b, "is_win"].values for b in blocks}

    rng = np.random.default_rng(seed)
    win_rates = np.empty(n_boot)
    for i in range(n_boot):
        chosen = rng.choice(blocks, size=len(blocks), replace=True)
        pool = np.concatenate([block_wins[b] for b in chosen])
        sample = pool[:window] if len(pool) >= window else pool
        win_rates[i] = sample.mean()
    return win_rates


def main() -> None:
    args = parse_args()

    baseline = load_backtest_trades(args.baseline)
    recent = load_db_trades(args.db) if args.db else load_backtest_trades(args.recent_backtest)

    recent_window = recent.tail(args.window)
    if len(recent_window) < args.window:
        print(
            f"WARNING: only {len(recent_window)} closed trades available, "
            f"fewer than requested --window {args.window}."
        )

    observed_win_rate = recent_window["is_win"].mean()
    observed_mean_profit = recent_window["profit_ratio"].mean()

    null_dist = build_block_null_distribution(
        baseline, len(recent_window), args.block_freq, args.n_boot, args.seed
    )
    lo, hi = np.percentile(null_dist, [2.5, 97.5])
    alert_threshold = np.percentile(null_dist, args.alert_percentile)
    percentile_rank = (null_dist <= observed_win_rate).mean() * 100

    print(f"Baseline trades   : {len(baseline)} (from {args.baseline})")
    print(f"Recent window     : {len(recent_window)} trades")
    print(f"Recent win rate   : {observed_win_rate:.3%}")
    print(f"Recent avg profit%: {observed_mean_profit:.3%}")
    print(f"Baseline 95% CI   : [{lo:.3%}, {hi:.3%}]  (block-bootstrap, block={args.block_freq})")
    print(f"Alert threshold   : win rate <= {alert_threshold:.3%} (p{args.alert_percentile:.0f} of baseline)")
    print(f"Observed percentile rank vs baseline: {percentile_rank:.1f}th")

    if observed_win_rate <= alert_threshold:
        print(
            f"\nALERT: recent win rate {observed_win_rate:.3%} is at or below the "
            f"p{args.alert_percentile:.0f} threshold ({alert_threshold:.3%}). "
            "This is not typical variance for this strategy's history -- "
            "reduce size / re-investigate before scaling further."
        )
    else:
        print("\nOK: recent performance is within the normal range of historical variation.")


if __name__ == "__main__":
    main()
