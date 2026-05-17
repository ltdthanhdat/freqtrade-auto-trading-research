# E007

## Title

Kiểm tra nhánh `entry mix + basket prune + concurrency` để vượt `70% win_rate` mà vẫn giữ cadence.

## Linked hypothesis

- `H008`

## Experiment design

Trên cùng dataset futures `20260218-20260518`, bắt đầu từ snapshot sau `D005`, test từng vòng tối thiểu:

1. mở concurrency:
   - `max_open_trades = 2`
2. prune basket:
   - bỏ `BTC`
   - bỏ `D`
   - bỏ `BTC + D`
3. đổi entry mix:
   - ưu tiên `displacement -> trend_body -> pin_bar`
   - nới nhẹ tiêu chí `displacement`
   - siết nhẹ `pin_bar`

## Verify

- so kết quả trên cùng window `2026-02-18 04:00:00 -> 2026-05-17 17:00:00`
- chọn biến thể đầu tiên đạt đồng thời:
  - `win_rate > 70%`
  - `1 -> 1.5 trade/day`
  - `max_drawdown_pct` vẫn ở vùng kiểm soát được
