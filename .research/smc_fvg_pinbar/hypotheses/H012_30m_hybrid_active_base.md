# H012

## Title

Keeping the `1h` signal active across both corresponding `30m` bars, then only adding a `30m displacement short` in a bearish `1h` context, can raise cadence to `1.2 -> 1.5 trade/day` without reducing `win_rate`.

## Why this exists

- `H011` showed the hybrid `30m + 1h` has a good near-miss:
  - `104` trades
  - `70.19%`
  - `1.18/day`
- the trade log debug showed the old hybrid lost `2` winning trades from the `1h` baseline
- the root cause is that the `1h` signal only fires at the leading edge, so if the first `30m` bar is blocked due to a slot constraint, the baseline trade is also lost

## Success criteria

- on full window `20260218-20260518`:
  - cadence `1.2 -> 1.5/day`
  - `win_rate >= 70.5%`
- on sub-windows:
  - `20260218-20260418`
  - `20260301-20260430`
  - `20260401-20260518`
- no pair-specific rules used
- drawdown does not worsen uncontrollably compared to the previous accepted snapshot

## Falsifiers

- signal kept active but `win_rate` still falls below baseline
- or cadence passes on full window but fails on the earliest sub-window
- or many additional auxiliary rules are needed to salvage the result
