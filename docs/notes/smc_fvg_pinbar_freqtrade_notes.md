# SMC_FVG_PinBar Freqtrade Notes

Ngày cập nhật: 2026-05-14

## Mục tiêu

Lưu debug history và các phát hiện kỹ thuật khi chạy `SMC_FVG_PinBar` trên Freqtrade.

## Các quyết định hiện tại

### 1. Strategy dùng callback model của Freqtrade

- `populate_indicators`
- `populate_entry_trend`
- `custom_stake_amount`
- `order_filled`
- `custom_stoploss`
- `custom_roi`

### 2. Data seed dùng format gốc của Freqtrade

- Không còn convert data từ cache ngoài.
- Script seed chuẩn là:
  - `scripts/seed_freqtrade_data.py`
- Script này gọi:
  - `freqtrade download-data`
- Output theo config hiện tại:
  - `user_data/data`
  - `feather`
  - `futures`

### 3. Stop và target không hardcode bằng static config

Vì stop của strategy phụ thuộc từng FVG, nên đã dùng:

- `order_filled()` để ghi:
  - stop rate
  - signal kind
  - target roi
- `custom_stoploss()` để map stop tuyệt đối
- `custom_roi()` để giữ target `1R`

### 4. Sizing giữ theo intent của strategy

- risk `2%`
- cap `25% capital`
- dùng `custom_stake_amount`

### 5. Kết luận tuning FVG threshold

- Đã test 3 mốc:
  - baseline `0.35 / 0.65`
  - chặt hơn `0.25 / 0.75`
  - lỏng hơn `0.45 / 0.55`
- Case verify chính:
  - `BTC/USDT:USDT`
  - timerange `20260213-20260514`
- Kết quả:
  - `0.35 / 0.65`
    - `trades_count = 15`
    - `net_profit_pct = 0.96%`
    - `max_drawdown_pct = 0.70%`
    - `win_rate = 60.0%`
  - `0.25 / 0.75`
    - `trades_count = 11`
    - `net_profit_pct = 0.86%`
    - `max_drawdown_pct = 0.80%`
    - `win_rate = 63.6%`
  - `0.45 / 0.55`
    - `trades_count = 18`
    - `net_profit_pct = 1.20%`
    - `max_drawdown_pct = 0.67%`
    - `win_rate = 61.1%`
- Keep:
  - `FVG_RETRACE_RATIO = 0.45`
  - `FVG_CONFIRM_RATIO = 0.55`
- Discard:
  - `0.25 / 0.75`
  - tạm discard baseline `0.35 / 0.65`

## Các lưu ý hiện tại

### 1. Pair futures phải đúng format Freqtrade

- ví dụ:
  - `BTC/USDT:USDT`
- không dùng:
  - `BTC-USDT`

### 2. Timeframe seed nên luôn có `1m` và `1h`

- `1h` cho strategy timeframe
- `1m` cho `timeframe-detail`

### 3. Futures metadata có thể là blocker ở một số pair

- nếu download lỗi metadata:
  - bỏ pair đó khỏi preset
  - không workaround bằng nguồn data ngoài

## Script liên quan

- seed data:
  - `scripts/seed_freqtrade_data.py`

## Ghi nhớ cho vòng sau

- nếu mục tiêu là backtest:
  - seed đủ data cho đúng timerange
- nếu mục tiêu là execution:
  - ưu tiên cùng 1 config giữa backtest và dry-run
- nếu mục tiêu là live:
  - freeze threshold hiện tại trước
  - không tune thêm nếu chưa có log dry-run
- basket hiện tại vẫn chủ yếu phát sinh trade từ `BTC`
