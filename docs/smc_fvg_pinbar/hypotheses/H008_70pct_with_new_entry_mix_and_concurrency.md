# H008

## Title

Điều chỉnh mix entry hiện tại và cho phép `max_open_trades = 2` có thể vượt `70% win_rate` mà vẫn giữ cadence `1 -> 1.5 trade/day`.

## Why this exists

- `H007` đã loại hướng prune / filter-only trên snapshot `max_open_trades = 1`.
- cần kiểm tra liệu có thể đạt objective mới bằng thay đổi tối thiểu ở:
  - độ ưu tiên signal
  - ngưỡng signal
  - basket
  - concurrency

## Success criteria

- trên cùng window `2026-02-18 04:00:00 -> 2026-05-17 17:00:00`
- đạt đồng thời:
  - `win_rate > 70%`
  - cadence trong khoảng `1 -> 1.5 trade/day`
- không thêm family signal mới
- drawdown không xấu hơn snapshot accepted cũ một cách mất kiểm soát

## Falsifiers

- mọi biến thể đạt `>70%` nhưng cadence rơi dưới `1/day`
- hoặc cadence đạt nhưng `win_rate` vẫn dưới `70%`
- hoặc phải thêm logic entry mới ngoài scope tune tối thiểu
