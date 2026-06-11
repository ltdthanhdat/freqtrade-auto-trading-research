# H005 - Does leverage-aware risk handling bring the basket baseline closer to target

## Question

- If stake sizing and target ROI both scale with `leverage`, does the full-window basket get closer to target than the old baseline?

## Why this matters

- The old baseline has a high win rate but drawdown exceeds the ceiling and expectancy is thin.
- If sizing is wrong relative to leverage, signal tuning above will be distorted.

## Success criteria

- on the same window `2026-02-18 -> 2026-05-18` and same basket of `9` pairs:
  - `net_profit_pct` is noticeably better
  - `profit_factor` does not worsen
  - `max_drawdown_pct` approaches or enters the target of `<= 12%`
  - trade cadence remains large enough for continued tuning

## Status

- `closed`
