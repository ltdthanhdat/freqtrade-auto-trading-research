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

## D013 - Block dry-run after real WFO failure
- `2026-09-10` | discard for dry-run | H013 | run: `2026-09-10_wfo_validation_fail.md`
- keep the D011 strategy frozen, but do not admit it to dry-run on the current evidence
- reason: correctness checks pass, while all three chronological stressed OOS folds are negative and two breach the 15% drawdown budget; aggregate trades are `95`, below the required `100`
- impact: investigate regime/entry robustness as a new hypothesis; do not tune thresholds or override the manifest in this loop

## D014 - Discard extra-short removal candidate
- `2026-09-10` | discard | H014 | run: `2026-09-10_candidate_screening.md`
- removing the 30m displacement short branch still failed all three OOS folds and worsened the first-fold drawdown
- impact: keep D011 frozen; do not use this candidate for dry-run

## D015 - Discard trend-aligned entry filter
- `2026-09-10` | discard | H015 | run: `2026-09-10_candidate_screening.md`
- requiring 1h price and EMA20 slope alignment reduced trades to `74` and left aggregate stressed OOS profit negative
- impact: no entry-filter promotion

## D016 - Discard side-only trend filter
- `2026-09-10` | discard | H016 | run: `2026-09-10_candidate_screening.md`
- removing the slope requirement produced identical validation results to H015, so the extra condition had no signal effect in this sample
- impact: no entry-filter promotion

## D017 - Keep rolling diagnostic as failure evidence
- `2026-09-10` | keep evidence / block dry-run | H017 | run: `2026-09-10_candidate_screening.md`
- current rolling data produced three negative OOS folds and two drawdown breaches (`78` trades total); a supplementary below-minimum bootstrap gave p95 DD `68.55%` and p05 profit `-66.10%`; correctness checks passed, so the block is performance robustness rather than lookahead evidence
- impact: dry-run remains blocked; do not override the fixed WFO verdict or tune the policy to fit this sample

## D018 - Discard half-R target candidate
- `2026-09-10` | discard | H018 | run: `2026-09-10_candidate_screening.md`
- halving the target ROI improved fold win-rate but left all three stressed OOS folds negative, with two drawdown breaches and `99` trades
- impact: keep the baseline and target policy frozen; do not sweep more ROI values against this failed sample

## D019 - Discard no-cooldown candidate
- `2026-09-10` | discard | H019 | run: `2026-09-10_candidate_screening.md`
- removing the one-candle cooldown left `99` trades and worsened stressed OOS returns, especially the first fold (`-33.41%`, DD `33.41%`)
- impact: retain the cooldown protection; missing trade count is not the primary failure cause

## D020 - Discard symmetric displacement candidate
- `2026-09-10` | discard | H020 | run: `2026-09-10_candidate_screening.md`
- adding the bullish 30m displacement counterpart generated no new signals; all fixed-WFO metrics matched D011
- impact: do not promote the branch; signal scarcity/asymmetry is not the root cause

## D021 - Discard pure 1h FVG baseline
- `2026-09-10` | discard | H021 | run: `2026-09-10_candidate_screening.md`
- pure 1h execution produced more trades but materially worse OOS returns/DD and failed bootstrap p95 DD
- impact: do not replace the hybrid with the old FVG baseline; a new entry/model thesis is required

## D022 - Discard breakout-retest candidate
- `2026-09-10` | discard | H022 | run: `2026-09-10_candidate_screening.md`
- first OOS fold smoke already lost `63.70%` under stress with `73.35%` drawdown; full lookahead was stopped after excessive repeated-signal runtime
- impact: keep the frozen FVG baseline blocked; do not parameter-sweep this model

## D023 - Discard Bollinger pullback candidate
- `2026-09-10` | discard | H023 | run: `2026-09-10_candidate_screening.md`
- alternative Bollinger pullback entry passed correctness but produced only `37` OOS trades and negative stressed profit with two DD breaches
- impact: do not replace the baseline; no dry-run admission or parameter sweep

## D024 - Discard exploratory eight-pair basket
- `2026-09-10` | discard | H024 | run: `2026-09-10_candidate_screening.md`
- BTC/STG plus the accepted six-pair basket lost `30.55%` under stress with `30.55%` drawdown on the first OOS fold; Binance has no current D market
- impact: keep the accepted six-pair basket frozen; do not re-add pruned pairs from demo config

## D025 - Discard short-only candidate
- `2026-09-10` | discard | H025 | run: `2026-09-10_candidate_screening.md`
- removing all long entries made the first fold slightly positive but full WFO failed in fold two, remained below `100` trades, and had negative aggregate stressed profit
- impact: retain both-side baseline logic as an evidence snapshot only; no dry-run admission

## D026 - Discard BTC-regime filter
- `2026-09-10` | discard | H026 | run: `2026-09-10_candidate_screening.md`
- BTC 1h EMA50 alignment still lost `7.25%` under stress with `20.41%` drawdown on the first fold
- impact: no global-regime filter promotion

## D027 - Discard no-displacement candidate
- `2026-09-10` | discard | H027 | run: `2026-09-10_candidate_screening.md`
- removing displacement confirmations lost `15.78%` under stress with `18.20%` drawdown on the first fold
- impact: no signal-family pruning or parameter sweep from this failed sample

## D028 - Persist Monte Carlo diagnostics below the trade gate
- `2026-09-10` | keep | validation runner | tests: `46 passed`
- every non-empty OOS export now receives a block-bootstrap summary; p95 drawdown remains a gate only when the policy has all required folds and at least `min_oos_trades`
- impact: small-sample candidates expose adverse Monte Carlo evidence without weakening the fail-closed PASS gate

## D029 - Reconfirm fixed WFO failure after runner update
- `2026-09-10` | keep evidence / block dry-run | H013 rerun | manifest: `20260910T154811581578Z`
- correctness remains clean, but all three stressed folds are negative, p95 bootstrap DD is `92.42%`, p05 bootstrap profit is `-86.04%`, and attribution lacks two positive sources
- impact: the Monte Carlo reporting change adds evidence only; it does not change the frozen FAIL verdict or admit dry-run

## D030 - Discard RSI divergence short-only branch
- `2026-09-10` | discard | H-RSI-06 | run: `2026-09-10_rsi_divergence_screening.md`
- the 1h regular-divergence plus EMA50 short-only candidate failed the second chronological fold (`-23.24%`, `30.83%` DD), remained below `100` aggregate trades, and had adverse bootstrap diagnostics
- impact: do not promote the short-only RSI branch or tune its risk/ROI parameters

## D031 - Discard 4h regime filter for RSI divergence
- `2026-09-10` | discard | H-RSI-07 | run: `2026-09-10_rsi_divergence_screening.md`
- adding `4h close < 4h EMA50` to H-RSI-06 produced `32` smoke trades, `+17.11%` raw profit, and `15.94%` drawdown; it is weaker than H-RSI-06 and breaches the fixed `15%` screen ceiling
- impact: stop the RSI-divergence branch for this sample; production strategy/config and dry-run gate remain unchanged
