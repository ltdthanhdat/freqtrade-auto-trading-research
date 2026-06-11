# H001 - Looser FVG threshold may yield better results than baseline

## Question

- If the filter is relaxed from baseline `0.35 / 0.65` to `0.45 / 0.55`, does the strategy improve results without making the flow more complex?

## Why this matters

- FVG threshold is a variable that directly affects trade frequency and entry quality.

## Variable under test

- `FVG_RETRACE_RATIO`
- `FVG_CONFIRM_RATIO`

## Fixed controls

- strategy:
  - `SMC_FVG_Confirmation_Freqtrade`
- timeframe:
  - `1h`
- execution engine:
  - `Freqtrade`
- primary timerange:
  - `20260213-20260514`

## Success criteria

- net profit better than or at least not worse than baseline
- max drawdown not noticeably worse
- backtest flow remains simple and reproducible

## Linked experiments

- `E001`
- `E002`

## Status

- `confirmed`

## Final decision

- see `D001`
