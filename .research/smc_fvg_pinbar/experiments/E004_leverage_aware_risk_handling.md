# E004 - Compare Leverage-Aware Risk Handling on a Clean Baseline

## Hypothesis

- `H005`

## Scope

- no basket changes
- no entry threshold changes
- no timeframe changes
- only compare:
  - strategy at the old `HEAD`
  - current strategy with:
    - `custom_stake_amount` additionally divided by `leverage`
    - `smc_target_roi` multiplied by `trade.leverage`
    - `custom_roi` returning leverage-aware risk-adjusted ROI

## Verify

- same timerange `20260218-20260518`
- same futures config
- same futures dataset freshly seeded over the full range

## Goal

- confirm whether the leverage-aware change is an improvement worth keeping before pruning the basket

## Conclusion

- `keep`
- new baseline does not reach `win_rate >= 65%`, but the overall profile is clearly closer to the target:
  - drawdown decreased significantly
  - profit factor increased
  - positive profit increased substantially
- the next step should be `basket pruning`, not reverting to the old sizing
