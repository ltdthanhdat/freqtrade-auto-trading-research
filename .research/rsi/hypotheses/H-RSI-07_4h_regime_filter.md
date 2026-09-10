# H-RSI-07 - 4h bearish EMA50 regime filter

## Question

- Can requiring `4h close < 4h EMA50` suppress short entries taken during higher-timeframe strength?

## Variable under test

- add one higher-timeframe bearish regime filter to H-RSI-06

## Fixed controls

- short-only 1h divergence, pivot, RSI, stop, risk handling, pair universe, fee, protections, and `1m` detail remain unchanged
- smoke window: `20260524-20260623`

## Success criteria

- first OOS-sized screen stays at or below `15%` max drawdown
- no new pair-specific or parameter-tuning rules are required

## Linked experiment

- `E-RSI-07`

## Status

- `discarded`

## Final decision

- the first screen breaches the drawdown ceiling; stop before full WFO
