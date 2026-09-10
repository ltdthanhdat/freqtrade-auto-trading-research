# SMC_FVG_PinBar Current State

Last updated: 2026-09-10

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

- `validation gate failed; OOS robustness investigation`
- objective: keep dry-run blocked after the real WFO failure; investigate the regime/entry failure before any strategy change

## Latest validation evidence

- snapshot: `accepted_6pair_2026q3_wfo`
- window: `2026-01-24 -> 2026-08-22`
- correctness: lookahead passed (`20` signals, no bias); recursive analysis conclusive
- OOS: `95` trades across three folds, stressed returns `-31.66% / -14.80% / -7.64%`, drawdown `31.66% / 19.28% / 14.17%`
- verdict: `FAIL`; rerun after the validation-runner change is retained at `.research/smc_fvg_pinbar/runs/20260910T154811581578Z/manifest.json`
- rerun evidence: `95` trades, stressed returns `-31.66% / -14.80% / -7.64%`, p95 bootstrap DD `92.42%`, p05 bootstrap profit `-86.04%`, `bootstrap_gate_eligible=false`; attribution also fails the two-positive-source check
- action: no dry-run; no threshold or basket tuning in the same loop

### Supplementary screening (2026-09-10)

- H014/H015/H016 candidate entry filters all failed real WFO validation; none changed the frozen strategy
- H018 half-R exit candidate improved win-rate but still failed all performance gates; it was not promoted
- H019 no-cooldown candidate worsened OOS returns; retain the one-candle protection
- H020 symmetric displacement candidate produced no new signals and matched baseline; no entry branch was promoted
- H021 pure 1h FVG baseline was materially worse despite more trades; the underlying FVG model is not OOS-robust
- H022 breakout-retest candidate failed the first OOS fold smoke (`-63.70%`, DD `73.35%`) and was not promoted
- H023 Bollinger pullback passed correctness but failed OOS robustness (`37` trades, negative stressed aggregate); it was not promoted
- H024 exploratory eight-pair basket failed the first fold (`57` trades, stressed `-30.55%`, DD `30.55%`); `D/USDT:USDT` is unavailable on Binance
- H025 short-only passed the first-fold smoke but failed full WFO (`62` trades; stressed `+0.19% / -8.97% / +4.92%`; aggregate negative)
- H026 BTC 1h EMA50 regime filter failed the first fold (`-7.25%` stressed, `20.41%` DD)
- H027 no-displacement entry family failed the first fold (`-15.78%` stressed, `18.20%` DD)
- H017 rolling current-window diagnostic (`2026-02-12 -> 2026-09-10`) also failed: `78` OOS trades, stressed returns `-21.97% / -7.66% / -6.74%`, drawdowns `23.28% / 17.58% / 10.83%`
- supplementary bootstrap below the policy trade minimum is also adverse: rolling p95 DD `68.55%` / p05 profit `-66.10%`; fixed WFO p95 DD `92.42%` / p05 profit `-86.04%` (now persisted automatically)
- lookahead and recursive checks passed; therefore the block is a robustness/performance finding, not a detected lookahead defect
- `make validate-pass` rejected the H017 manifest as expected; no dry-run process was started
- validation runner now persists block-bootstrap diagnostics below the trade minimum while keeping the p95 DD gate disabled until the sample is eligible (`bootstrap_gate_eligible`)

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

1. require a separately specified strategy thesis before any new candidate; do not keep probing filters or thresholds against this failed sample
2. if a future candidate is evaluated, rerun the full frozen correctness + WFO + stress + bootstrap gate on an immutable snapshot
3. start dry-run only after a future run reaches `PASS`; the retained `FAIL` manifests cannot be overridden

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
