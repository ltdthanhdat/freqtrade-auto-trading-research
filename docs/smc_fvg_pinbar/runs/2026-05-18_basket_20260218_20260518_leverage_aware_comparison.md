# Run - Basket leverage-aware comparison

## Case

- basket:
  - current default basket `9` pairs
- timeframe:
  - `1h`
- timerange:
  - `20260218-20260518`
- dataset:
  - seed lại full futures range ngày `2026-05-18`

## Variants

- `HEAD` cũ:
  - `trades_count = 127`
  - `win_rate = 78.7%`
  - `net_profit_pct = 23.84%`
  - `profit_factor = 1.22`
  - `max_drawdown_pct = 23.18%`
- leverage-aware hiện tại:
  - `trades_count = 95`
  - `win_rate = 61.1%`
  - `net_profit_pct = 140.19%`
  - `profit_factor = 1.75`
  - `max_drawdown_pct = 12.92%`

## Interpretation

- baseline cũ đạt win rate target nhưng payoff mỏng và drawdown quá xa target
- leverage-aware hiện tại chưa chạm `65%` win rate, nhưng:
  - giữ cadence cao hơn target
  - kéo drawdown về rất gần trần `12%`
  - tăng expectancy và profit factor đủ mạnh để đáng giữ
- pair âm rõ nhất trong snapshot hiện tại:
  - `STG/USDT:USDT = -8.15%`
  - `BTC/USDT:USDT = -3.00%`
  - `D/USDT:USDT = -2.66%`

## Linked experiment

- `E004`
