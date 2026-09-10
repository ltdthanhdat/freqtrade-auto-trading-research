# RSI divergence research state

Last updated: 2026-09-11

## Current truth

- scope: research-only RSI divergence candidates
- production strategy: `src/strategies/SMC_FVG_Context30m_Freqtrade.py`
- candidate path: `.research/rsi/candidates`
- local risk base: `.research/rsi/candidates/FuturesRiskBase_Freqtrade.py`
- universe: fixed 24-pair liquidity/coverage-filtered snapshot
- deployment: none; RSI is not admitted to the dry-run gate
- research chain: `H-RSI-00..07` → `E-RSI-00..07` → linked run evidence

## Screening evidence

- H-RSI-01 regular 30m: `235` trades, `-72.21%`, `73.89%` DD — discard
- H-RSI-02 30m plus 1h EMA50: `104` trades, `-17.00%`, `35.51%` DD — discard
- H-RSI-03 hidden 30m: `328` trades, `-59.62%`, `62.39%` DD — discard
- H-RSI-04 regular 1h: `106` trades, `+26.29%`, `40.44%` DD — discard
- H-RSI-05 1h plus EMA50: fold two `-29.31%` / `39.83%` DD; bootstrap p95 DD `92.93%` — discard
- H-RSI-06 short-only: fold two `-23.24%` / `30.83%` DD; bootstrap p95 DD `51.96%` — discard
- H-RSI-07 4h EMA50 regime: `32` smoke trades, `+17.11%`, `15.94%` DD — discard

All candidates either failed the smoke ceiling, chronological WFO, trade
minimum, or tail-risk checks. No RSI branch replaces the frozen SMC strategy.

## Next step

Do not tune RSI parameters against this sample. A future RSI thesis must use a
new immutable snapshot, one changed hypothesis, and the full correctness,
WFO, stress, and bootstrap checks before any promotion discussion.
