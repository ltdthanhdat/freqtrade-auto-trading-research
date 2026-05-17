# H006 - Bỏ `STG/USDT:USDT` có kéo basket gần target hơn không

## Question

- nếu bỏ `STG/USDT:USDT` khỏi default basket, basket-level win rate và drawdown có tiến gần target hơn không?

## Why this matters

- `STG` đang là pair âm nhất theo `%` trong clean baseline mới
- đây là thay đổi nhỏ nhất ở phase basket pruning, không thêm logic mới

## Success criteria

- trên cùng window `2026-02-18 -> 2026-05-18`:
  - `win_rate` tăng
  - `max_drawdown_pct` không xấu hơn
  - `net_profit_pct` vẫn dương
  - `trades_count >= 45`

## Status

- `closed`
