# SMC_FVG_PinBar Roadmap

Trạng thái:

- active
- phase hiện tại:
  - `accepted >70% snapshot, ưu tiên execution validation`

## Goal

- dùng Freqtrade làm execution engine ổn định
- đảm bảo:
  - seed data được
  - backtest lặp lại được
  - dry-run được
  - rồi mới live

## Execution order

1. seed data
2. backtest `BTC/USDT:USDT 1h`
3. backtest basket hiện tại
4. dry-run với snapshot accepted hiện tại
5. chỉ tune thêm khi có objective mới

## Open hypotheses

- `H004`
  - cần xác nhận có cần preset risk riêng cho `live`

## Recently resolved hypotheses

- `H001`
  - keep threshold `0.45 / 0.55`
- `H002`
  - freeze tuning, chuyển sang `dry-run`
- `H005`
  - keep leverage-aware risk handling
- `H006`
  - keep prune `STG/USDT:USDT`
- `H007`
  - discard prune / filter-only path cho objective `>70%`
- `H008`
  - keep nhánh `entry mix + basket prune + concurrency`

## Current rule

- mỗi vòng chỉ đổi `1` ý
- ưu tiên flow ổn định trước
- không tune khi nguyên nhân chưa rõ
- không ghi raw result vào file này

## Next execution step

1. giữ nguyên strategy hiện tại làm baseline accepted
2. giữ dataset full range `20260218-20260518`
3. dùng snapshot accepted hiện tại cho dry-run
4. nếu tiếp tục tune, mở objective mới trước khi mở hypothesis
