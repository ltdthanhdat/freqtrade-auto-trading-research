# SMC_FVG_PinBar Current State

Last updated: 2026-07-23

## Current truth

- strategy: `src/strategies/SMC_FVG_Context30m_Freqtrade.py`
- timeframe: `30m` (informative context `1h`)
- basket: `6` pairs (PLAY, BIO, SPACE, PENDLE, BR, YGG)
- market: `futures`, `cross`, `can_short = True`
- engine: `Freqtrade`
- data source: `freqtrade download-data` -> `user_data/data`

## Active settings

- FVG threshold:
  - `FVG_RETRACE_RATIO = 0.45`
  - `FVG_CONFIRM_RATIO = 0.55`
- signal mix:
  - base: `1h` signal active across both `30m` candles within the same hour
  - extra: `30m displacement short` when `1h close < EMA20` and `1h EMA20 slope < 0`
- risk handling:
  - `custom_stake_amount` scales by `distance_ratio * leverage`
  - `smc_target_roi` scales by `trade.leverage`
  - risk `5%`, cap `25% capital`
- target / stop: callback strategy
- concurrency: `max_open_trades = 3`

## Latest accepted snapshot

- source: `D011`, `E011`
- window: `2026-02-18 -> 2026-05-17`
- metrics:
  - `117` trades / `70.94%` win rate / `1.33 trade/day`
  - `424.35%` net profit / `2.593` profit factor / `8.17%` max drawdown
- sub-window consistency:
  - cadence `1.22 -> 1.48/day`
  - win rate `71.83% -> 79.01%`
- notes:
  - basket has removed STG, BTC, D
  - weakest remaining pair: BR, no further pruning needed yet

## Current phase

- `accepted cadence-pass snapshot, decay watch active`
- objective: fix known config drift, monitor real trade history for decay, do not tune blind

## Known issue: demo/live basket drift

- `config.binance.demo.json` pair_whitelist still has 9 pairs (adds `BTC/D/STG`, pruned by `D005`/`D007`)
- `config.futures.json` (base) and post-pull `config.binance.live.json` correctly hold the accepted 6-pair basket
- this is the primary cause of demo vs live position divergence -- not wallet size, not the (dead) `stake_amount` field
- see `D012`, run `2026-07-23_demo_live_divergence_and_decay_investigation.md`

## Decay watch

- last-month backtest (`20260623`-`20260723`, 6-pair basket): `63` trades / `46.0%` win / `-22.5%` -- statistically a real outlier (block-bootstrap `p≈0.9%`), not noise
- correlates with market-direction regime (`r=+0.548`), not with pure time decay (residual `r≈-0.07`) -- inconclusive on permanent alpha decay, do not discard strategy yet
- use `scripts/monitor_decay.py` against real live/demo trade DB going forward; re-evaluate after 4-8 more weeks

## Next step

1. reconcile `config.binance.demo.json` whitelist with the accepted 6-pair basket (or explicitly document why it differs)
2. run `scripts/monitor_decay.py` against real live/demo trade history once available
3. only tune the strategy itself when there is a new objective beyond the current cadence and decay watch

## Implementation notes

- Strategy uses Freqtrade's callback model:
  `populate_indicators`, `populate_entry_trend`, `custom_stake_amount`, `order_filled`, `custom_stoploss`, `custom_roi`
- Data seed uses `scripts/seed_freqtrade_data.py` calling `freqtrade download-data`.
  Output: `user_data/data/binance/futures` (active), `user_data/data/snapshots/<name>/futures` (snapshot). Format: `feather`, `futures`.
- Stop and target are not hardcoded via static config:
  `order_filled()` writes stop rate / signal kind / target roi, `custom_stoploss()` maps absolute stop, `custom_roi()` holds target `1R`.
- Sizing: risk `5%`, cap `25% capital`, uses `custom_stake_amount`.
- Working rules:
  - backtest goal: seed enough data for the correct timerange
  - execution goal: use the same config between backtest and dry-run
  - live goal: freeze current threshold first, no tuning without dry-run logs
