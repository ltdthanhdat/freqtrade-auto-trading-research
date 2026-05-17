# H007

## Title

Simple filtering của basket / side / signal hiện tại có thể đẩy `win_rate > 70%` mà vẫn giữ cadence `1 -> 1.5 trade/day`.

## Why this exists

- snapshot hiện tại sau `D005` đang ở:
  - `89` trades
  - `62.9%` win rate
  - `1.01 trade/day`
- cần xác nhận có thể đi tiếp bằng prune / filter nhẹ hay phải đổi thesis.

## Success criteria

- trên cùng window `2026-02-18 04:00:00 -> 2026-05-17 17:00:00`
- đạt đồng thời:
  - `win_rate > 70%`
  - cadence trong khoảng `1 -> 1.5 trade/day`
- không thêm branch signal mới.

## Falsifiers

- mọi biến thể prune / filter chỉ đạt `>70%` khi trades tụt dưới cadence target
- hoặc không biến thể nào chạm `>70%` trên vùng trades hợp lệ.
