# E011 - Test hybrid `30m` với active `1h` base

## Hypothesis

- `H012`

## Scope

- strategy mới:
  - `src/strategies/SMC_FVG_Context30m_Freqtrade.py`
- config runtime:
  - timeframe `30m`
  - `max_open_trades = 3`
- logic:
  - giữ `1h` signal active trên cả hai nến `30m` trong cùng giờ
  - giữ stop/tag theo `1h` cho phần baseline
  - chỉ cộng thêm `30m displacement short` khi:
    - `1h close < EMA20`
    - `1h EMA20 slope < 0`

## Verify

- cùng dataset futures full range
- compare trên các window:
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

- xác nhận near-miss của `H011` đến từ vấn đề signal timing chứ không phải thesis hybrid sai hoàn toàn

## Conclusion

- `keep`
- variant này là candidate đầu tiên đạt đồng thời:
  - cadence target
  - `win_rate` không giảm
  - verify qua nhiều window
