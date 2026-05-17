# E006

## Title

Kiểm tra hướng prune / filter nhẹ cho target `>70% win_rate` với cadence `1 -> 1.5 trade/day`.

## Linked hypothesis

- `H007`

## Experiment design

Trên cùng dataset futures `20260218-20260518` và strategy snapshot sau `D005`, test:

1. prune basket:
   - bỏ `BTC`
   - bỏ `BTC + D`
2. filter / threshold nhẹ:
   - đổi signal priority
   - siết `pin_bar`
   - siết `trend_body`
   - bỏ `long pin_bar`
   - thêm `EMA20 bias` cho `pin_bar / trend_body`
3. kiểm tra constraint ở level subset:
   - `pair`
   - `signal_kind x side`
   - `pair x side x signal`

## Verify

- so kết quả trên cùng window `2026-02-18 04:00:00 -> 2026-05-17 17:00:00`
- xem biến thể nào đạt đồng thời:
  - `win_rate > 70%`
  - `88 -> 132` trades trên window này
