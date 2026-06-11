# E007

## Title

Test the `entry mix + basket prune + concurrency` branch to exceed `70% win_rate` while maintaining cadence.

## Linked hypothesis

- `H008`

## Experiment design

On the same futures dataset `20260218-20260518`, starting from the snapshot after `D005`, test in minimal rounds:

1. increase concurrency:
   - `max_open_trades = 2`
2. prune basket:
   - remove `BTC`
   - remove `D`
   - remove `BTC + D`
3. change entry mix:
   - prioritize `displacement -> trend_body -> pin_bar`
   - slightly relax `displacement` criteria
   - slightly tighten `pin_bar`

## Verify

- compare results on the same window `2026-02-18 04:00:00 -> 2026-05-17 17:00:00`
- select the first variant that simultaneously achieves:
  - `win_rate > 70%`
  - `1 -> 1.5 trade/day`
  - `max_drawdown_pct` remains in an acceptable range
