# E010 - Test `30m` Execution with `1h` Context

## Hypothesis

- `H011`

## Scope

- keep accepted basket of `6` pairs
- keep current risk / stop / roi logic
- test sequentially:
  1. raw `30m` baseline
  2. `30m` gated by accepted `1h signal`
  3. `30m` extra `displacement short` under bearish `1h` context
  4. try higher concurrency for hybrid

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

- confirm whether the thesis `smaller execution timeframe while retaining 1h context` genuinely creates a new edge or only increases noise

## Conclusion

- `discard`
- raw `30m` gives excessive cadence but `win_rate` drops to around `49%`
- best hybrid variant only achieves a near-miss:
  - `104` trades
  - `1.18/day`
  - `70.19%`
- more aggressive variant reaches `1.27/day` but `win_rate` is only `69.64%`
- no path simultaneously hits cadence while maintaining `win_rate`
