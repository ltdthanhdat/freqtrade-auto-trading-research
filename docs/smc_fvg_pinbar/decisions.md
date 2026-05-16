# SMC_FVG_PinBar Decisions

## D001 - Keep FVG threshold `0.45 / 0.55`

- ngày:
  - `2026-05-14`
- status:
  - `keep`
- hypothesis:
  - `H001`
- supporting experiments:
  - `E001`
  - `E002`
- supporting runs:
  - `2026-05-14_btc_20260213_20260514_fvg_thresholds.md`
  - `2026-05-14_basket_20260213_20260514_fvg_thresholds.md`
- decision:
  - giữ `FVG_RETRACE_RATIO = 0.45`
  - giữ `FVG_CONFIRM_RATIO = 0.55`
- reason:
  - kết quả tốt hơn baseline `0.35 / 0.65`
  - không làm flow hiện tại phức tạp hơn
- state impact:
  - freeze threshold này cho phase `dry-run`

## D002 - Freeze tuning, chuyển sang dry-run

- ngày:
  - `2026-05-14`
- status:
  - `keep`
- hypothesis:
  - `H002`
- supporting experiments:
  - `E003`
- supporting runs:
  - none
- decision:
  - dừng tuning mù
  - ưu tiên execution validation bằng `dry-run`
- reason:
  - flow data và execution phải ổn định trước khi tối ưu thêm
- state impact:
  - roadmap hiện tại chuyển sang `freeze strategy cho dry-run`
