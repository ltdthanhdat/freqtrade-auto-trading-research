# H011

## Title

Execution timeframe `30m` với context `1h` có thể nâng cadence lên `1.2 -> 1.5 trade/day` mà vẫn giữ `win_rate` của snapshot accepted.

## Why this exists

- `H009` và `H010` đã bác:
  - nới threshold
  - thêm branch đơn giản trên cùng timeframe `1h`
- raw `30m` tự thân cho cadence đủ nhưng chất lượng quá kém
- cần kiểm tra hướng hợp lý hơn:
  - execution chi tiết hơn ở `30m`
  - nhưng vẫn giữ context `1h`

## Success criteria

- trên full window `20260218-20260518`:
  - cadence `1.2 -> 1.5/day`
  - `win_rate >= 70.5%`
- trên các sub-window:
  - `20260218-20260418`
  - `20260301-20260430`
  - `20260401-20260518`
- không có pattern degrade rõ ở window sớm nhất

## Falsifiers

- `30m` raw vẫn quá xa target
- hybrid `30m + 1h` chỉ ra near-miss nhưng không giữ được `win_rate`
- hoặc phải thêm nhiều rule phụ / pair-specific rule mới cứu được kết quả
