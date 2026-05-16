# SMC_FVG_PinBar Roadmap

Trạng thái:

- active
- phase hiện tại:
  - `freeze strategy cho dry-run`

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
4. dry-run basket hiện tại

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

## Current rule

- mỗi vòng chỉ đổi `1` ý
- ưu tiên flow ổn định trước
- không tune khi nguyên nhân chưa rõ
- không ghi raw result vào file này

## Next execution step

1. giữ nguyên strategy hiện tại
2. seed data bằng flow chuẩn
3. chạy `dry-run` với config futures
4. ghi run log nếu xuất hiện mismatch theo pair hoặc callback
