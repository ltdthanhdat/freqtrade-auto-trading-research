# E-RSI-05 - Add same-timeframe EMA50 to 1h divergence

## Hypothesis

- `H-RSI-05`

## Scope

- candidate: `.research/rsi/candidates/RSI_Divergence1h_EMA50Short_Freqtrade.py`
- changed variable: one `1h EMA50` direction filter
- WFO: three chronological folds, aggregate minimum `100` OOS trades
- tail-risk and attribution checks enabled

## Result

- smoke: `39` trades, `+53.11%`, `10.24%` DD
- WFO folds after stress:
  - `39 / +51.98% / 10.37%` DD
  - `49 / -29.31% / 39.83%` DD
  - `38 / +12.18% / 14.63%` DD
- bootstrap p95 max DD: `92.93%`
- bootstrap p05 net profit: `-70.99%`
- attribution: only the bearish tag was profitable; bullish attribution failed

## Conclusion

- `discard`
- the smoke result is regime-dependent and the WFO/bootstrap tail risk is unacceptable for promotion

## Linked runs

- `.research/rsi/runs/rsi-h005-wfo/`
- `.research/rsi/runs/2026-09-10_rsi_divergence_screening.md#h-rsi-05--1h-regular-divergence-plus-1h-ema50`
