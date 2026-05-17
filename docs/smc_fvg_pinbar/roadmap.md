# SMC_FVG_PinBar Roadmap

Trạng thái:

- active
- phase hiện tại:
  - `near target snapshot sau basket pruning`

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
4. prune `1` pair xấu nhất rồi re-backtest full basket
5. dry-run chỉ sau khi basket snapshot đủ gần target

## Open hypotheses

- `H003`
  - cần xác nhận basket mặc định có nên giữ rộng hay thu hẹp về `BTC`-led basket
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

## Current rule

- mỗi vòng chỉ đổi `1` ý
- ưu tiên flow ổn định trước
- không tune khi nguyên nhân chưa rõ
- không ghi raw result vào file này

## Next execution step

1. giữ nguyên strategy hiện tại
2. giữ dataset full range `20260218-20260518`
3. nếu cần thêm `1` vòng, thử bỏ `BTC/USDT:USDT` và re-backtest full basket
4. nếu không cần ép chạm `65%`, giữ snapshot hiện tại cho phase dry-run
