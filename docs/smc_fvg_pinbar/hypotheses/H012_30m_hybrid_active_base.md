# H012

## Title

Giữ signal `1h` active trên cả hai nến `30m` tương ứng, rồi chỉ cộng thêm `30m displacement short` trong bearish context `1h`, có thể nâng cadence lên `1.2 -> 1.5 trade/day` mà không làm `win_rate` giảm.

## Why this exists

- `H011` cho thấy hybrid `30m + 1h` có near-miss tốt:
  - `104` trades
  - `70.19%`
  - `1.18/day`
- debug trade log cho thấy hybrid cũ làm mất `2` trade thắng của baseline `1h`
- nguyên nhân là signal `1h` chỉ bắn ở cạnh đầu, nên nếu bar `30m` đầu bị block vì slot thì trade baseline mất luôn

## Success criteria

- trên full window `20260218-20260518`:
  - cadence `1.2 -> 1.5/day`
  - `win_rate >= 70.5%`
- trên các sub-window:
  - `20260218-20260418`
  - `20260301-20260430`
  - `20260401-20260518`
- không dùng pair-specific rule
- drawdown không xấu hơn snapshot accepted cũ một cách mất kiểm soát

## Falsifiers

- giữ signal active nhưng `win_rate` vẫn thấp hơn baseline
- hoặc cadence pass ở full window nhưng fail ở sub-window sớm nhất
- hoặc cần thêm nhiều rule phụ nữa mới cứu được
