# SMC_FVG_PinBar Roadmap

Trạng thái:

- active
- phase hiện tại:
  - `accepted cadence-pass snapshot, ưu tiên execution validation`

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
- `H009`
  - discard minimal cadence-only tuning cho objective `1.2 -> 1.5/day`
- `H010`
  - discard simple add-on branches cho objective cadence mới
- `H011`
  - discard `30m execution + 1h context` cho current constraints
- `H012`
  - keep hybrid `30m` với active `1h` base

## Current rule

- mỗi vòng chỉ đổi `1` ý
- ưu tiên flow ổn định trước
- không tune khi nguyên nhân chưa rõ
- không ghi raw result vào file này

## Next execution step

1. giữ `SMC_FVG_Context30m_Freqtrade` làm baseline accepted
2. seed đủ `30m + 1h` data cho basket hiện tại
3. dùng snapshot accepted hiện tại cho dry-run
4. chỉ tune thêm khi có objective mới ngoài cadence hiện tại
