# Run - `30m` execution with `1h` context

## Case

- baseline accepted:
  - `D007`
  - basket `6` pairs
  - timeframe `1h`
  - `95` trades
  - `70.5%`
  - `1.08/day`
- objective:
  - nâng cadence lên `1.2 -> 1.5/day`
  - không làm `win_rate` thấp hơn snapshot accepted

## Raw `30m` baseline

- full window:
  - `149` trades
  - `48.99%`
  - `1.69/day`
  - `profit_factor = 0.829`
  - `max_drawdown_pct = 36.99%`
- sub-window:
  - `1.55/day`, `48.89%`
  - `1.77/day`, `50.0%`
  - `1.70/day`, `47.44%`
- interpretation:
  - cadence đủ
  - quality hỏng hoàn toàn
- artifacts:
  - `backtest-result-2026-05-18_03-16-09.zip`
  - `backtest-result-2026-05-18_03-16-21.zip`
  - `backtest-result-2026-05-18_03-16-34.zip`
  - `backtest-result-2026-05-18_03-16-44.zip`

## Hybrid attempts

- `30m` gated bởi exact accepted `1h signal`
  - full window:
    - `15` trades
    - `73.33%`
    - `0.17/day`
  - interpretation:
    - quality cao nhưng cadence gần như mất hẳn
  - artifact:
    - `backtest-result-2026-05-18_03-23-16.zip`
- `30m` + accepted `1h` base entries + extra `30m displacement short` khi:
  - `1h close < EMA20`
  - `1h EMA20 slope < 0`
  - `max_open_trades = 2`
  - full window:
    - `106` trades
    - `69.81%`
    - `1.20/day`
  - interpretation:
    - cadence chạm ngưỡng dưới
    - `win_rate` vẫn thấp hơn baseline
  - artifact:
    - `backtest-result-2026-05-18_03-24-54.zip`
- cùng hybrid trên với `max_open_trades = 3`
  - full window:
    - `104` trades
    - `70.19%`
    - `1.18/day`
  - interpretation:
    - đây là near-miss tốt nhất của round này
    - `win_rate` gần baseline hơn
    - nhưng cadence vẫn dưới `1.2/day`
  - artifact:
    - `backtest-result-2026-05-18_03-29-25.zip`
- `30m displacement short` khi:
  - `1h active bearish FVG`
  - `1h bear candle`
  - `max_open_trades = 3`
  - full window:
    - `112` trades
    - `69.64%`
    - `1.27/day`
  - interpretation:
    - cadence pass
    - `win_rate` fail
  - artifact:
    - `backtest-result-2026-05-18_03-33-44.zip`

## Interpretation

- chuyển sang `30m` execution đúng là giải quyết được bài toán cadence
- nhưng mỗi lần cadence chạm target thì `win_rate` lại tụt dưới baseline
- hybrid tốt nhất hiện tại vẫn chỉ là near-miss:
  - `104` trades
  - `1.18/day`
  - `70.19%`
- do đó thesis này chưa đủ bằng chứng để promote thành current truth

## Final verify

- strategy experiment đã được bỏ khỏi tree sau khi run fail
- current truth không đổi:
  - vẫn giữ `D007`
- linked experiment:
  - `E010`
