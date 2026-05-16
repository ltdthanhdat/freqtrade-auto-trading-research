# H001 - FVG threshold lỏng hơn có thể cho kết quả tốt hơn baseline

## Question

- Nếu nới filter từ baseline `0.35 / 0.65` sang `0.45 / 0.55`, strategy có cải thiện kết quả mà không làm flow phức tạp hơn không?

## Why this matters

- FVG threshold là biến ảnh hưởng trực tiếp đến tần suất trade và quality của entry.

## Variable under test

- `FVG_RETRACE_RATIO`
- `FVG_CONFIRM_RATIO`

## Fixed controls

- strategy:
  - `SMC_FVG_PinBar_Freqtrade`
- timeframe:
  - `1h`
- execution engine:
  - `Freqtrade`
- timerange chính:
  - `20260213-20260514`

## Success criteria

- net profit tốt hơn hoặc ít nhất không tệ hơn baseline
- max drawdown không xấu hơn rõ rệt
- flow backtest vẫn đơn giản và lặp lại được

## Linked experiments

- `E001`
- `E002`

## Status

- `confirmed`

## Final decision

- xem `D001`
