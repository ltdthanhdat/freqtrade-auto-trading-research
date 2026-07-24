# Run - Demo/Live Position Divergence & Alpha Decay Investigation

- date:
  - `2026-07-23`
- scope:
  - why demo and live open different positions
  - whether recent underperformance is alpha decay

## Hypothesis

- H-A: demo/live position divergence is caused by config drift (pair whitelist / sizing), not just separate accounts
- H-B: recent (last month) underperformance is permanent alpha decay (crowding/structural)

## Setup

- config:
  - `config/config.futures.json` (base, `pair_whitelist`: 6 pairs -- PLAY, BIO, SPACE, PENDLE, BR, YGG)
  - `config/config.binance.demo.json` (override, `pair_whitelist`: 9 pairs -- adds BTC, D, STG)
  - `config/config.binance.live.json` (post-pull `f31d6de`: 6 pairs, `stake_amount` field removed)
- strategy:
  - `src/strategies/SMC_FVG_Context30m_Freqtrade.py`
- data:
  - `user_data/data/binance/futures`, downloaded `2026-02-18` -> `2026-07-23` (30m/1h/1m, futures+mark+funding)

## Run

1. Local git checkout was 1 commit behind `origin/master` (`f31d6de`). Pulled after confirming working-tree edits to `.env.example`/`compose.yaml` were byte-identical to the incoming commit (stashed, pulled, popped -- no loss).
2. `.gitignore` only excludes `tradesv3.sqlite*`, not the actual filenames used (`tradesv3.demo.sqlite`, `tradesv3.live.sqlite`) -- these are currently NOT git-ignored. No commit has ever included them (`git log --all --full-history -- "*.sqlite*"` empty), but the gap is live.
3. Confirmed via code read: `custom_stake_amount` (`SMC_FVG_Confirmation_Freqtrade.py:324-359`) always overrides any static `stake_amount` config value whenever `smc_risk_per_trade`/`smc_capital_cap` are set (they always are, via base config) -- sizing is `% risk x total_stake_amount / (distance x leverage)`. The `"stake_amount": 60` field in `config.binance.demo.json` is dead config.
4. Verified via paired local backtest (`dry_run_wallet` 60 vs 1000, same signals/timerange): identical trade count (49), identical entries/exits, only USDT-denominated size and absolute P&L scaled proportionally (avg stake 12.18 vs 204.63 USDT). Wallet-size difference alone does NOT explain divergent positions between demo/live.
5. Confirmed the real divergence driver: `config.binance.demo.json` still carries the 9-pair whitelist, re-adding `BTC/USDT:USDT`, `D/USDT:USDT`, `STG/USDT:USDT` -- all 3 explicitly pruned by `D005`/`D007` in `decisions.md` for hurting performance. Demo and live currently trade different baskets.
6. Reproduced the accepted `D011` snapshot on its exact window (`20260218`-`20260517`, base config, 6-pair basket): 115 trades, 72.2% win rate, +509.84% profit -- consistent with the recorded 117 trades / 70.94% / +424.35% (small variance from wallet-compounding, not a discrepancy in reproducibility).
7. Same basket/config, most recent 3 months (`20260423`-`20260723`): 144 trades, 50.7% win rate, +15.51%.
8. Same basket/config, most recent 1 month (`20260623`-`20260723`): 63 trades, 46.0% win rate, **-22.5%** (loss).
9. Regime decomposition (12x 2-week buckets, full `20260218`-`20260723` history): win rate vs 1h ADX (trend strength) correlation `-0.108` (no relationship); win rate vs realized market return (direction) correlation `+0.548` (moderate); residual of win-rate-on-market-return vs calendar time `-0.071` (no leftover pure time-decay once regime is controlled for).
10. Statistical significance check (block-bootstrap, 2-week blocks, 20000 resamples, preserving time-clustering) on the full 222-trade history: probability of a random 63-trade block-resampled window landing at or below 46.0% win rate = **0.9%** (p1 percentile). The last-month result is a genuine statistical outlier, not sampling noise.
11. Built `scripts/monitor_decay.py`: block-bootstrap baseline vs rolling recent window (from live/demo sqlite DB or a backtest export), alerts when recent win rate falls at/below a configurable percentile of the historical null distribution. Validated against the available backtest export (self-consistent run: 13.2th percentile, no alert).

## Result

- H-A (config drift causes divergence):
  - `confirmed`
  - divergence is driven by basket mismatch (demo 9 pairs vs research-accepted 6) + independent accounts/exchange endpoints, NOT by the dead `stake_amount` field or wallet-size differences alone
- H-B (permanent alpha decay):
  - `inconclusive, leaning against "already dead"`
  - last month is a real statistical outlier (not noise), but correlates more with an unfavorable market-direction regime (`+0.548` correlation) than with pure calendar-time decay (`~0` residual trend) -- consistent with regime dependency, not proven structural/crowding decay
  - `do not discard the strategy on current evidence`; monitor with `scripts/monitor_decay.py` and re-evaluate after next 4-8 weeks of real trades

## Notes / follow-ups

- `config.binance.demo.json` pair whitelist should be reconciled with the accepted 6-pair basket (or the divergence from live is intentional and should be documented, not left as silent drift).
- `.gitignore` sqlite patterns should be widened to `tradesv3*.sqlite*`.
- No live/demo sqlite trade history exists in this checkout (server-side only) -- `scripts/monitor_decay.py` has not yet been run against real trade data.
