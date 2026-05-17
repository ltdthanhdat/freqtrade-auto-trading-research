# H005 - Leverage-aware risk handling có đưa basket baseline gần target hơn không

## Question

- nếu stake sizing và target ROI cùng scale theo `leverage`, basket full-window có gần target hơn baseline cũ không?

## Why this matters

- baseline cũ có win rate cao nhưng drawdown vượt trần và expectancy mỏng
- nếu sizing sai theo leverage thì tuning signal phía trên sẽ bị nhiễu

## Success criteria

- trên cùng window `2026-02-18 -> 2026-05-18` và cùng basket `9` pairs:
  - `net_profit_pct` tốt hơn rõ ràng
  - `profit_factor` không xấu đi
  - `max_drawdown_pct` tiến gần hoặc đi vào target `<= 12%`
  - trade cadence vẫn đủ lớn để dùng tiếp cho tuning

## Status

- `closed`
