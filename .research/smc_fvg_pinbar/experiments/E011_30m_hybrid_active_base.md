# E011 - Test Hybrid `30m` with Active `1h` Base

## Hypothesis

- `H012`

## Scope

- new strategy:
  - `src/strategies/SMC_FVG_Context30m_Freqtrade.py`
- runtime config:
  - timeframe `30m`
  - `max_open_trades = 3`
- logic:
  - keep `1h` signal active across both `30m` candles within the same hour
  - keep stop/tag based on `1h` for the baseline portion
  - only add `30m displacement short` when:
    - `1h close < EMA20`
    - `1h EMA20 slope < 0`

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

- confirm whether the near-miss from `H011` is due to a signal timing issue rather than a fundamentally flawed hybrid thesis

## Conclusion

- `keep`
- this variant is the first candidate to simultaneously achieve:
  - cadence target
  - `win_rate` maintained without degradation
  - verified across multiple windows
