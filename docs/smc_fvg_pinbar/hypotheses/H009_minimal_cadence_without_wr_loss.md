# H009

## Title

Minimal tuning hiện tại có thể nâng cadence lên `1.2 -> 1.5 trade/day` trên nhiều timerange mà không kéo `win_rate` xuống dưới snapshot accepted.

## Why this exists

- snapshot accepted sau `D007` đang ở:
  - `95` trades
  - `70.5%` win rate
  - `1.08 trade/day`
- objective mới là tăng cadence mà không overfit:
  - giữ basket hiện tại
  - giữ signal family hiện tại
  - verify trên nhiều window thay vì chỉ `1` full range

## Success criteria

- trên full window `20260218-20260518`:
  - cadence trong khoảng `1.2 -> 1.5 trade/day`
  - `win_rate >= 70.5%`
- trên các sub-window:
  - `20260218-20260418`
  - `20260301-20260430`
  - `20260401-20260518`
- không xuất hiện xu hướng giảm `win_rate` rõ rệt so với baseline cùng window
- không thêm signal family mới

## Falsifiers

- mọi biến thể chỉ tăng cadence lên quanh `1.1x/day`
- hoặc chạm cadence cao hơn nhưng `win_rate` tụt dưới snapshot accepted
- hoặc chỉ pass ở window cuối nhưng fail trên các window sớm hơn
