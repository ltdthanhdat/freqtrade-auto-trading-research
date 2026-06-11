# H006 - Removing `STG/USDT:USDT` to bring the basket closer to target

## Question

- If `STG/USDT:USDT` is removed from the default basket, do the basket-level win rate and drawdown get closer to target?

## Why this matters

- `STG` is the worst-performing pair by `%` in the new clean baseline.
- This is the smallest change in the basket pruning phase, adding no new logic.

## Success criteria

- on the same window `2026-02-18 -> 2026-05-18`:
  - `win_rate` increases
  - `max_drawdown_pct` does not worsen
  - `net_profit_pct` remains positive
  - `trades_count >= 45`

## Status

- `closed`
