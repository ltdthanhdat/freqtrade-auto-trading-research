# E010 - Test `30m` execution với context `1h`

## Hypothesis

- `H011`

## Scope

- giữ basket accepted `6` pairs
- giữ logic risk / stop / roi hiện tại
- test tuần tự:
  1. raw `30m` baseline
  2. `30m` gated bởi accepted `1h signal`
  3. `30m` extra `displacement short` dưới bearish `1h` context
  4. thử concurrency cao hơn cho hybrid

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

- xác nhận thesis `execution timeframe nhỏ hơn nhưng giữ context 1h` có thật sự tạo edge mới hay chỉ tăng nhiễu

## Conclusion

- `discard`
- raw `30m` cho cadence dư nhưng `win_rate` rơi về khoảng `49%`
- hybrid tốt nhất chỉ đạt near-miss:
  - `104` trades
  - `1.18/day`
  - `70.19%`
- biến thể mạnh tay hơn chạm `1.27/day` nhưng `win_rate` chỉ còn `69.64%`
- chưa có path nào vừa chạm cadence vừa giữ `win_rate`
