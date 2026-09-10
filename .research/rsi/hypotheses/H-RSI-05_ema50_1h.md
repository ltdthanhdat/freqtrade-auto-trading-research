# H-RSI-05 - 1h regular divergence plus 1h EMA50

## Question

- Can aligning 1h regular divergence with the same-timeframe EMA50 direction produce a robust branch?

## Variable under test

- add a same-timeframe `1h EMA50` direction filter to H-RSI-04

## Fixed controls

- pivot, RSI, stop, pair basket, risk handling, fee, protections, and `1m` detail remain unchanged
- WFO policy: three chronological folds, aggregate minimum `100` OOS trades, max drawdown ceiling `15%`

## Success criteria

- all correctness checks pass
- WFO folds remain profitable or within the declared risk budget
- bootstrap tail risk and source attribution pass the gate

## Linked experiment

- `E-RSI-05`

## Status

- `discarded`

## Final decision

- smoke strength is insufficient when WFO and bootstrap tail risk are included; do not promote
