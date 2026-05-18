# H010

## Title

Thêm `1` branch entry đơn giản mới trên cùng context `1h FVG` có thể nâng cadence lên `1.2 -> 1.5 trade/day` mà vẫn giữ `win_rate` của snapshot accepted.

## Why this exists

- `H009` đã bác hướng:
  - tăng `max_open_trades`
  - nới threshold các branch hiện có
- cần kiểm tra một thesis khác nhưng vẫn tối giản:
  - giữ basket accepted
  - giữ timeframe `1h`
  - thêm đúng `1` branch candle pattern mới

## Success criteria

- trên full window `20260218-20260518`:
  - cadence `1.2 -> 1.5/day`
  - `win_rate >= 70.5%`
- trên các sub-window:
  - `20260218-20260418`
  - `20260301-20260430`
  - `20260401-20260518`
- không có dấu hiệu chỉ pass ở window cuối
- không đụng pair-specific rule

## Falsifiers

- branch mới đạt cadence nhưng full-window `win_rate` giảm rõ
- hoặc window sớm nhất giảm mạnh hơn full-window
- hoặc phải thêm nhiều filter phụ mới cứu được branch
