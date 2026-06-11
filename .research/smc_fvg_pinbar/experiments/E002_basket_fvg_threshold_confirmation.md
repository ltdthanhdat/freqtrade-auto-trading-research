# E002 - Threshold Confirmation on Current Basket

## Hypothesis

- `H001`

## Scope

- current basket
- timerange:
  - `20260213-20260514`

## Goal

- check whether the threshold that performed well on `BTC` remains acceptable at the basket level

## Metrics

- `trades_count`
- `net_profit_pct`
- `max_drawdown_pct`
- `win_rate`

## Linked runs

- `2026-05-14_basket_20260213_20260514_fvg_thresholds.md`

## Conclusion

- basket snapshot remains acceptable with threshold `0.45 / 0.55`
- overall edge does not significantly exceed `BTC`, but sufficient to freeze for the `dry-run` phase
