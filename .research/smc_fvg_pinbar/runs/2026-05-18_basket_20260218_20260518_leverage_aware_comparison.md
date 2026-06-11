# Run - Basket leverage-aware comparison

## Case

- basket:
  - current default basket `9` pairs
- timeframe:
  - `1h`
- timerange:
  - `20260218-20260518`
- dataset:
  - reseeded full futures range on `2026-05-18`

## Variants

- old `HEAD`:
  - `trades_count = 127`
  - `win_rate = 78.7%`
  - `net_profit_pct = 23.84%`
  - `profit_factor = 1.22`
  - `max_drawdown_pct = 23.18%`
- current leverage-aware:
  - `trades_count = 95`
  - `win_rate = 61.1%`
  - `net_profit_pct = 140.19%`
  - `profit_factor = 1.75`
  - `max_drawdown_pct = 12.92%`

## Interpretation

- the old baseline met the win rate target but had thin payoff and drawdown far from target
- the current leverage-aware version has not reached `65%` win rate, but:
  - maintains a higher cadence than the target
  - brings drawdown very close to the `12%` ceiling
  - increases expectancy and profit factor strongly enough to justify keeping it
- most negative pairs in the current snapshot:
  - `STG/USDT:USDT = -8.15%`
  - `BTC/USDT:USDT = -3.00%`
  - `D/USDT:USDT = -2.66%`

## Linked experiment

- `E004`
