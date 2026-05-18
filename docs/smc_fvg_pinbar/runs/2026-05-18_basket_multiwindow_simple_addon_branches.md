# Run - Multi-window simple add-on branches

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
- artifacts:
  - `backtest-result-2026-05-18_02-44-31.zip`
  - `backtest-result-2026-05-18_02-44-47.zip`
  - `backtest-result-2026-05-18_02-44-59.zip`
  - `backtest-result-2026-05-18_02-45-12.zip`

## Variant results

- thêm branch `reclaim`
  - full window:
    - `115` trades
    - `67.8%`
    - `1.31/day`
  - sub-window sớm nhất:
    - `68` trades
    - `64.7%`
    - `1.17/day`
  - interpretation:
    - cadence đã vào target
    - nhưng `win_rate` giảm quá rõ ở full-window và window sớm
  - artifacts:
    - `backtest-result-2026-05-18_03-06-27.zip`
    - `backtest-result-2026-05-18_03-06-36.zip`
- thêm branch `reclaim` + `EMA20` bias
  - full window:
    - `106` trades
    - `67.9%`
    - `1.20/day`
  - sub-window sớm nhất:
    - `64` trades
    - `65.6%`
    - `1.10/day`
  - interpretation:
    - filter cứu được một phần cadence overshoot
    - nhưng chưa cứu được `win_rate`
  - artifacts:
    - `backtest-result-2026-05-18_03-08-31.zip`
    - `backtest-result-2026-05-18_03-08-46.zip`
- thêm branch `engulfing` + `EMA20` bias
  - full window:
    - `108` trades
    - `67.6%`
    - `1.23/day`
  - sub-window sớm nhất:
    - `66` trades
    - `63.6%`
    - `1.14/day`
  - interpretation:
    - cadence vào target
    - nhưng `win_rate` giảm còn xấu hơn `reclaim + EMA20`
  - artifacts:
    - `backtest-result-2026-05-18_03-11-48.zip`
    - `backtest-result-2026-05-18_03-11-58.zip`

## Interpretation

- branch mới kiểu `1-candle add-on` đúng là giải quyết được thiếu cadence
- nhưng phần trade thêm vào chưa đủ chất lượng để giữ `win_rate`
- pattern fail giống nhau ở các branch:
  - window cuối nhìn ổn hơn
  - window sớm nhất xấu hơn rõ
- vì vậy tiếp tục search quanh các branch đơn nến sẽ rất dễ overfit

## Final verify

- strategy tree đã revert sạch về snapshot accepted
- current truth không đổi:
  - vẫn giữ `D007`
- linked experiment:
  - `E009`
