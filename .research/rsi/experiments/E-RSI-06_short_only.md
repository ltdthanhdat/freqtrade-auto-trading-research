# E-RSI-06 - Disable long entries

## Hypothesis

- `H-RSI-06`

## Scope

- base: H-RSI-05
- changed variable: disable long entries; retain the short signal and risk handling
- WFO: three chronological folds, aggregate minimum `100` OOS trades

## Result

- smoke: `33` short trades, `+25.12%`, `11.55%` DD, `63.6%` win rate
- WFO folds after stress:
  - `33 / +24.19% / 11.72%` DD
  - `34 / -23.24% / 30.83%` DD
  - `30 / +15.60% / 9.55%` DD
- aggregate trades: `97` (below the `100`-trade minimum)
- bootstrap p95 max DD: `51.96%`
- bootstrap p05 net profit: `-40.03%`
- attribution: one bearish short tag only; two-source requirement failed

## Conclusion

- `discard`
- removing longs does not resolve the adverse middle fold or tail risk

## Linked runs

- `.research/rsi/runs/rsi-h006-wfo/`
- `.research/rsi/runs/2026-09-10_rsi_divergence_screening.md#h-rsi-06--1h-regular-divergence-plus-ema50-short-only`
