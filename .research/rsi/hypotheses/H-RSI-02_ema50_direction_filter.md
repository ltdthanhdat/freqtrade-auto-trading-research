# H-RSI-02 - 1h EMA50 direction filter

## Question

- Can suppressing regular-divergence entries against the 1h EMA50 direction remove the standalone 30m branch's losses?

## Variable under test

- add one `1h EMA50` direction filter to the H-RSI-01 events

## Fixed controls

- RSI, pivot, stop, execution timeframe, pair basket, fee, protections, and `1m` detail remain unchanged from H-RSI-01
- smoke window: `20260524-20260623`

## Success criteria

- improve net profit without exceeding `15%` max drawdown
- preserve causal signal timing

## Linked experiment

- `E-RSI-02`

## Status

- `discarded`

## Final decision

- do not continue parameter tuning on this branch
