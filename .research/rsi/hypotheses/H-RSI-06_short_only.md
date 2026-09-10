# H-RSI-06 - Short-only regular divergence plus EMA50

## Question

- Does the bearish side carry the edge after disabling long entries from H-RSI-05?

## Variable under test

- disable long entries; keep the short signal, stop, and risk handling unchanged

## Fixed controls

- execution timeframe: `1h`
- EMA50 filter, pivot, RSI, pair basket, fee, protections, and `1m` detail remain unchanged
- WFO policy remains three chronological folds with a `100` aggregate OOS-trade minimum

## Success criteria

- adverse middle-fold behavior is resolved
- aggregate trade count reaches the gate minimum
- bootstrap tail risk and attribution checks pass

## Linked experiment

- `E-RSI-06`

## Status

- `discarded`

## Final decision

- removing longs does not resolve the robustness and tail-risk failures
