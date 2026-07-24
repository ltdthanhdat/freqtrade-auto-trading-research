# SMC_FVG_PinBar Decisions

## D001 - Keep FVG threshold `0.45 / 0.55`
- `2026-05-14` | keep | H001 | E001, E002
- keep `FVG_RETRACE_RATIO = 0.45`, `FVG_CONFIRM_RATIO = 0.55`
- reason: better results than baseline `0.35 / 0.65`, no added complexity
- impact: freeze threshold for dry-run

## D002 - Freeze tuning, switch to dry-run
- `2026-05-14` | keep | H002 | E003
- stop blind tuning, prioritize execution validation via dry-run
- reason: data flow and execution must stabilize before further optimization
- impact: roadmap shifts to freeze strategy for dry-run

## D003 - Keep explicit Binance demo futures URL override
- `2026-05-17` | keep | — | run: `2026-05-17_binance_demo_freqtrade_validation.md`
- keep separate demo config, explicit override of `exchange.ccxt_config.urls.api.fapi*`
- reason: `enableDemoTrading = true` alone is not sufficient; explicit URL override required for Freqtrade + CCXT 4.5.38
- impact: provides a path to verify execution on demo before live rollout

## D004 - Keep leverage-aware risk handling
- `2026-05-18` | keep | H005 | E004
- keep `custom_stake_amount` divided by `leverage`, `smc_target_roi = risk_ratio * trade.leverage`
- reason: drawdown reduced `23.18% → 12.92%`, profit_factor increased `1.22 → 1.75`, net profit increased `23.84% → 140.19%`
- impact: baseline is clean enough for the basket pruning phase

## D005 - Keep prune `STG/USDT:USDT`
- `2026-05-18` | keep | H006 | E005
- remove STG from default basket
- reason: win_rate `61.1% → 62.9%`, profit_factor `1.75 → 1.97`, drawdown `12.92% → 10.74%`, trades still `89`
- impact: near target; remaining negative pairs concentrated in BTC and D

## D006 - Discard prune/filter-only path for target `>70%`
- `2026-05-18` | discard | H007 | E006
- do not pursue light prune/filter approach for objective `>70% win_rate`
- reason: `89` trades / `56` wins; all filtering methods fail to raise to the required `62/63` wins
- impact: if continuing to tune, must change thesis; next direction should create or replace entry logic

## D007 - Keep `max_open_trades = 2` + prune BTC/D + displacement-first entry mix
- `2026-05-18` | keep | H008 | E007
- keep `max_open_trades = 2`, remove BTC and D, maintain priority `displacement → trend_body → pin_bar`
- reason: achieved `95` trades / `70.5%` / `1.08/day` / `287.21%` profit / `2.56` PF / `9.78%` DD
- impact: snapshot exceeds target `>70%`, basket has `6` pairs remaining

## D008 - Discard minimal cadence-only tuning
- `2026-05-18` | discard | H009 | E008
- do not keep: `max_open_trades = 3/4` only raises `1.08 → 1.09/day`; loosening displacement gives `102` trades but WR `67.7%`
- reason: no evidence of sustainable edge across sub-windows
- impact: accepted snapshot remains D007; should not continue tweaking thresholds

## D009 - Discard simple add-on branches
- `2026-05-18` | discard | H010 | E009
- do not keep: reclaim `67.8%`, reclaim+EMA20 `67.9%`, engulfing+EMA20 `67.6%`
- reason: earliest windows all clearly underperform baseline
- impact: accepted snapshot remains D007; if continuing, should change thesis to a smaller execution timeframe

## D010 - Discard `30m execution + 1h context`
- `2026-05-18` | discard | H011 | E010
- do not keep: raw `30m` ~`49%` WR, best hybrid near-miss `104` trades / `70.19%` / `1.18/day`
- reason: does not simultaneously meet cadence `1.2 → 1.5/day` and `win_rate >= 70.5%`
- impact: accepted snapshot remains D007; if continuing, must accept a larger thesis or loosen requirements

## D011 - Keep hybrid `30m` with active `1h` base
- `2026-05-18` | keep | H012 | E011
- use `SMC_FVG_Context30m_Freqtrade`, timeframe `30m`, `max_open_trades = 3`, `1h` signal active on both `30m` candles + `30m displacement short` when `1h` bearish
- reason: `117` trades / `70.94%` / `1.33/day` / `424.35%` profit / `2.593` PF / `8.17%` DD, sub-window `1.22 → 1.48/day` / `71.83% → 79.01%`
- impact: accepted snapshot changes to hybrid 30m; cadence objective passes; next phase returns to execution validation

## D012 - Keep strategy, do not discard on current decay evidence; fix basket drift; add monitoring
- `2026-07-23` | keep | — | run: `2026-07-23_demo_live_divergence_and_decay_investigation.md`
- do not discard `SMC_FVG_Context30m_Freqtrade`; last-month underperformance (`63` trades / `46.0%` win / `-22.5%`) is a real statistical outlier (block-bootstrap `p≈0.9%`) but correlates with an unfavorable market-direction regime (`r=+0.548`), not with pure calendar-time decay (residual `r≈-0.07`) -- inconclusive for permanent alpha decay
- reason: reproduced `D011` snapshot exactly on its original window (`115` trades / `72.2%` / `+509.84%`); confirmed `config.binance.demo.json` re-adds `BTC/D/STG` pruned by `D005`/`D007` (9-pair basket vs accepted 6), which is the real driver of demo/live position divergence, not wallet size or the (dead) `stake_amount` field
- impact: reconcile `config.binance.demo.json`/`config.binance.live.json` pair whitelist with the accepted 6-pair basket; use `scripts/monitor_decay.py` against real live/demo trade history going forward instead of ad-hoc re-backtesting on suspicion; re-evaluate decay verdict after 4-8 more weeks of real trades
