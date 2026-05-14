# SMC_FVG_PinBar Freqtrade Tuning Plan

Trạng thái:

- active
- phase hiện tại: `freeze strategy cho dry-run, tuning sau`

## Mục tiêu

- dùng Freqtrade làm execution engine
- giữ strategy ổn định để:
  - seed data được
  - backtest được
  - dry-run được
  - live được
- không tune mù khi flow data và execution còn chưa rõ

## Nguyên tắc

1. Mỗi vòng chỉ đổi `1` ý

2. Ưu tiên flow ổn định trước

Thứ tự:

- seed data
- backtest `BTC/USDT:USDT 1h`
- backtest basket hiện tại
- dry-run basket hiện tại

3. Chỉ tune sau khi data và config đã ổn định

## Latest decision

- hypothesis:
  - FVG filter lỏng hơn có thể cho quality tốt hơn baseline
- verify:
  - đã test `0.35 / 0.65`, `0.25 / 0.75`, `0.45 / 0.55`
  - case chính: `BTC/USDT:USDT`, timerange `20260213-20260514`
  - case phụ: basket hiện tại, cùng timerange
- keep:
  - `FVG_RETRACE_RATIO = 0.45`
  - `FVG_CONFIRM_RATIO = 0.55`
- discard:
  - `0.25 / 0.75`
  - tạm discard baseline `0.35 / 0.65`
- conclusion:
  - dừng tuning tại đây
  - chuyển sang `dry-run`

## Scope được phép sửa

Cho phase hiện tại, chỉ nên đụng:

- `src/strategies/SMC_FVG_PinBar_Freqtrade.py`
- `config/config.futures.json`
- `scripts/seed_freqtrade_data.py`
- docs trong `freqtrade-template/docs`

Không nên đụng:

- data cache ngoài repo
- logic không liên quan đến strategy hiện tại

## Standard loop

1. Chọn đúng 1 case

- ví dụ:
  - `BTC/USDT:USDT` 90 ngày
  - `BTC/USDT:USDT` timerange cụ thể
  - 1 pair đang lỗi metadata

2. Ghi rõ hypothesis

Ví dụ:

- lỗi do data chưa đủ
- lỗi do pair metadata
- lệch do stop callback
- lệch do custom roi

3. Sửa tối thiểu

4. Chạy lại backtest

5. Ghi:

- trade count
- net profit %
- max drawdown
- win rate

6. Keep / discard rõ ràng

## Metrics

- `trades_count`
- `net_profit_pct`
- `max_drawdown_pct`
- `win_rate`

Metric phụ:

- độ ổn định của flow seed
- lỗi metadata theo pair

## Keep / discard rule

Giữ thay đổi nếu:

- flow seed đơn giản hơn
- backtest chạy ổn định hơn
- không phá config hiện tại

Loại nếu:

- chỉ sửa một case nhưng làm flow chung phức tạp hơn

## Khi nào mới bật dry-run rộng

Chỉ nên bật dry-run nhiều pair khi:

- seed data ổn
- backtest basket ổn
- basket làm việc không còn pair bị blocker metadata

## Next execution step

1. giữ nguyên strategy hiện tại
2. chạy `dry-run` với config futures
3. log signal thật theo pair
4. chỉ mở lại tuning nếu dry-run cho thấy mismatch hoặc alt basket không có signal

## Current reference

- source of truth state:
  - `docs/state/smc_fvg_pinbar_freqtrade_state.md`
