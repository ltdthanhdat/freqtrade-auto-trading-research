# H-RSI-04 - Regular RSI divergence on 1h

## Question

- Does moving the same regular-divergence logic from 30m to 1h reduce noise enough to improve robustness?

## Variable under test

- execution timeframe changes from `30m` to `1h`

## Fixed controls

- divergence, RSI, pivot, stop, basket, smoke window, `1m` detail, fee, and protections remain unchanged

## Success criteria

- positive net profit with max drawdown at or below `15%`
- no single trade dominates the result

## Linked experiment

- `E-RSI-04`

## Status

- `discarded`

## Final decision

- do not advance to WFO when the first screen breaches the drawdown ceiling
