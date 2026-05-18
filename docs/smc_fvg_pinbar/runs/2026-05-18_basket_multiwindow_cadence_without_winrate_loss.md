# Run - Multi-window cadence without win-rate loss

## Case

- baseline accepted:
  - `D007`
  - basket `6` pairs
  - `max_open_trades = 2`
- objective:
  - nâng cadence lên `1.2 -> 1.5 trade/day`
  - không làm `win_rate` thấp hơn snapshot accepted
- windows:
  - `20260218-20260518`
  - `20260218-20260418`
  - `20260301-20260430`
  - `20260401-20260518`

## Baseline verify

- full window:
  - `95` trades
  - `70.5%` win rate
  - `1.08/day`
- sub-window:
  - `58` trades / `69.0%` / `1.00/day`
  - `65` trades / `80.0%` / `1.08/day`
  - `56` trades / `76.8%` / `1.22/day`
- artifacts:
  - `backtest-result-2026-05-18_02-44-31.zip`
  - `backtest-result-2026-05-18_02-44-47.zip`
  - `backtest-result-2026-05-18_02-44-59.zip`
  - `backtest-result-2026-05-18_02-45-12.zip`

## Variant results

- tăng `max_open_trades = 3`
  - full window:
    - `96` trades
    - `70.8%`
    - `1.09/day`
  - sub-window sớm nhất:
    - `59` trades
    - `69.5%`
    - `1.02/day`
  - kết luận:
    - tăng quá ít, không chạm cadence target
  - artifact full-window:
    - `backtest-result-2026-05-18_02-45-31.zip`
- tăng `max_open_trades = 4`
  - kết quả khớp `max_open_trades = 3`
  - không có thêm edge mới
  - artifact full-window:
    - `backtest-result-2026-05-18_02-46-22.zip`
- nới `displacement` xuống vùng `body_ratio = 0.45`, `close_extreme_ratio = 0.35`
  - full window:
    - `102` trades
    - `67.7%`
    - `1.16/day`
  - sub-window sớm nhất:
    - `62` trades
    - `66.1%`
    - `1.07/day`
  - kết luận:
    - cadence tăng nhưng `win_rate` giảm rõ
  - artifact full-window:
    - `backtest-result-2026-05-18_02-51-55.zip`
- nới riêng `pin_bar short` với `body_ratio = 0.40`
  - full window:
    - `102` trades
    - `69.6%`
    - `1.16/day`
  - sub-window sớm nhất:
    - `61` trades
    - `70.5%`
    - `1.05/day`
  - kết luận:
    - chưa chạm cadence target
    - full-window `win_rate` vẫn thấp hơn baseline
  - artifact full-window:
    - `backtest-result-2026-05-18_02-56-48.zip`
- nới riêng `pin_bar short` với `body_ratio = 0.40`, `wick_to_body = 2.0`
  - full window:
    - `105` trades
    - `68.6%`
    - `1.19/day`
  - sub-window sớm nhất:
    - `62` trades
    - `71.0%`
    - `1.07/day`
  - kết luận:
    - đã gần chạm cadence target
    - nhưng full-window `win_rate` giảm quá rõ
  - artifact full-window:
    - `backtest-result-2026-05-18_02-58-06.zip`

## Interpretation

- window cuối `20260401-20260518` tự nhiên đã ở vùng `1.22/day`, nên tune theo window này rất dễ overfit
- điểm nghẽn thực sự nằm ở các window sớm hơn:
  - `20260218-20260418`
  - `20260301-20260430`
- các lever tối thiểu có thể:
  - tăng cadence lên vùng `1.16 -> 1.19/day`
  - hoặc giữ `win_rate`
- nhưng chưa có biến thể nào làm được cả hai cùng lúc ở basket level

## Final verify

- strategy tree đã revert về snapshot accepted sau khi các variant fail
- current truth không đổi:
  - giữ `D007` làm baseline accepted
- linked experiment:
  - `E008`
