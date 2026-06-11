# E005 - Prune `STG/USDT:USDT` from the Default Basket

## Hypothesis

- `H006`

## Scope

- keep strategy logic unchanged
- keep timeframe unchanged
- keep risk config unchanged
- only remove `STG/USDT:USDT` from the basket

## Verify

- same timerange `20260218-20260518`
- same futures dataset full range
- compare basket-level metrics before and after pruning

## Goal

- confirm whether a simple pruning step brings the current snapshot closer to the target

## Conclusion

- `keep`
- basket after pruning:
  - reached drawdown target
  - increased `win_rate`, `profit_factor`, `net_profit_pct`
  - still maintained `89` trades, sufficient cadence
- new snapshot still falls short by approximately `2.1` win rate points from the primary target
