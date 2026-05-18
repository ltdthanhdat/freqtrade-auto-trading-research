# E008 - Test minimal cadence levers trên nhiều timerange

## Hypothesis

- `H009`

## Scope

- giữ nguyên basket accepted `6` pairs
- giữ nguyên timeframe `1h`
- giữ nguyên signal family hiện tại
- chỉ test các lever tối thiểu:
  - `max_open_trades`
  - nới `displacement`
  - nới riêng `pin_bar short`

## Verify

- cùng dataset futures full range
- compare trên các window:
  - `20260218-20260518`
  - `20260218-20260418`
  - `20260301-20260430`
  - `20260401-20260518`
- baseline so theo:
  - `trade/day`
  - `win_rate`
  - `profit_factor`
  - `max_drawdown_pct`

## Goal

- xác nhận objective cadence mới có đi tiếp được bằng tune tối thiểu hay phải đổi thesis

## Conclusion

- `discard`
- `max_open_trades = 3/4` không đủ kéo full-window lên `1.2/day`
- mọi hướng nới signal đủ mạnh để tăng cadence đều làm `win_rate` full-window giảm dưới snapshot accepted
- objective này cần thesis mới, không nên tiếp tục vặn các threshold hiện tại
