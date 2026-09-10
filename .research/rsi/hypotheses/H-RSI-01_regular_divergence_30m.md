# H-RSI-01 - Standalone regular RSI divergence on 30m

## Question

- Can RSI(14) regular divergence on confirmed 30m pivots provide a standalone reversal signal?

## Variable under test

- regular bullish/bearish RSI divergence
- confirmed pivot parameters: `left=3`, `right=3`
- structural stop: second confirmed price pivot

## Fixed controls

- execution timeframe: `30m`
- informative timeframe: none
- pair basket: fixed 24-pair RSI snapshot
- smoke window: `20260524-20260623`
- detail timeframe: `1m`
- fee: `0.001`
- protections: enabled
- pivot confirmation is causal; a pivot at `p` is evaluated only on `p+3`

## Success criteria

- positive net profit after the configured fee
- max drawdown at or below the fixed `15%` screen ceiling
- no evidence that the signal depends on future candles

## Linked experiment

- `E-RSI-01`

## Status

- `discarded`

## Final decision

- see `H-RSI-01` in [decisions.md](../decisions.md)
