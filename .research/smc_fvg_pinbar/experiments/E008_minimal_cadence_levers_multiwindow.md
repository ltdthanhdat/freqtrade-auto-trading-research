# E008 - Test Minimal Cadence Levers Across Multiple Timeranges

## Hypothesis

- `H009`

## Scope

- keep the accepted basket of `6` pairs
- keep timeframe `1h`
- keep the current signal family
- only test minimal levers:
  - `max_open_trades`
  - relax `displacement`
  - separately relax `pin_bar short`

## Verify

- same futures dataset full range
- compare across windows:
  - `20260218-20260518`
  - `20260218-20260418`
  - `20260301-20260430`
  - `20260401-20260518`
- baseline comparison based on:
  - `trade/day`
  - `win_rate`
  - `profit_factor`
  - `max_drawdown_pct`

## Goal

- confirm whether the new cadence objective can be progressed through minimal tuning or requires a thesis change

## Conclusion

- `discard`
- `max_open_trades = 3/4` is insufficient to bring the full window up to `1.2/day`
- every signal relaxation direction strong enough to increase cadence causes the full-window `win_rate` to drop below the accepted snapshot
- this objective requires a new thesis; continuing to adjust current thresholds is not warranted
