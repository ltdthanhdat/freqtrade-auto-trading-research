# Debug Notes

## Current operating notes

- Strategy dùng callback model của Freqtrade:
  - `populate_indicators`
  - `populate_entry_trend`
  - `custom_stake_amount`
  - `order_filled`
  - `custom_stoploss`
  - `custom_roi`

- Data seed dùng format gốc của Freqtrade:
  - script:
    - `scripts/seed_freqtrade_data.py`
  - command path:
    - `freqtrade download-data`
  - output:
    - dataset active:
      - `user_data/data/binance/futures`
    - dataset snapshot:
      - `user_data/data/snapshots/<name>/futures`
    - `feather`
    - `futures`

- Stop và target không hardcode bằng static config:
  - `order_filled()` ghi stop rate, signal kind, target roi
  - `custom_stoploss()` map stop tuyệt đối
  - `custom_roi()` giữ target `1R`

- Sizing giữ theo intent của strategy:
  - risk `2%`
  - cap `25% capital`
  - dùng `custom_stake_amount`

## Working rules

- nếu mục tiêu là backtest:
  - seed đủ data cho đúng timerange
- nếu mục tiêu là execution:
  - ưu tiên cùng 1 config giữa backtest và dry-run
- nếu mục tiêu là live:
  - freeze threshold hiện tại trước
  - không tune thêm nếu chưa có log dry-run
