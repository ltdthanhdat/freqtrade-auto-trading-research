# E009 - Test Simple Add-on Branches Across Multiple Timeranges

## Hypothesis

- `H010`

## Scope

- keep the accepted basket of `6` pairs
- keep timeframe `1h`
- keep sizing / stop / roi logic unchanged
- only add exactly `1` new branch at a time:
  - `reclaim`
  - `engulfing + EMA20 bias`

## Verify

- same futures dataset full range
- compare across windows:
  - `20260218-20260518`
  - `20260218-20260418`
  - `20260301-20260430`
  - `20260401-20260518`
- check:
  - `trade/day`
  - `win_rate`
  - `profit_factor`
  - `max_drawdown_pct`

## Goal

- confirm whether adding a new branch is better than relaxing existing thresholds

## Conclusion

- `discard`
- `reclaim` hits cadence but pulls `win_rate` down to `67.8%`
- `engulfing + EMA20` also hits cadence but pulls `win_rate` down to `67.6%`
- earlier windows perform significantly worse, so there is no evidence that these new branches are sustainable
