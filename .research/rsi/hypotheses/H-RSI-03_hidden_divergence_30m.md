# H-RSI-03 - Hidden RSI divergence on 30m

## Question

- Can hidden bullish/bearish divergence follow the prevailing trend more robustly than regular reversal divergence?

## Variable under test

- replace regular divergence with hidden divergence:
  - higher price low with lower RSI low
  - lower price high with higher RSI high

## Fixed controls

- execution timeframe: `30m`
- pair basket, smoke window, `1m` detail, fee, protections, pivot confirmation, and stop logic remain unchanged

## Success criteria

- positive net profit and max drawdown at or below `15%`
- causal pivot confirmation remains intact

## Linked experiment

- `E-RSI-03`

## Status

- `discarded`

## Final decision

- close the hidden-divergence branch for this sample
