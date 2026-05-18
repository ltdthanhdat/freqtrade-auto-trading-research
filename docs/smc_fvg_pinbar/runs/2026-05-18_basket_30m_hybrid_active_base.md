# Run - `30m` hybrid with active `1h` base

## Case

- baseline accepted cũ:
  - `SMC_FVG_Confirmation_Freqtrade`
  - timeframe `1h`
  - `95` trades
  - `70.5%`
  - `1.08/day`
- variant:
  - `SMC_FVG_Context30m_Freqtrade`
  - timeframe `30m`
  - informative context `1h`
  - `max_open_trades = 3`

## Verify

- full window `20260218-20260518`
  - `117` trades
  - `70.94%`
  - `1.33/day`
  - `424.35%` net profit
  - `2.593` profit factor
  - `8.17%` max drawdown
  - artifact:
    - `backtest-result-2026-05-18_03-45-55.zip`
- sub-window `20260218-20260418`
  - `71` trades
  - `71.83%`
  - `1.22/day`
  - `200.13%` net profit
  - `4.29` profit factor
  - `16.69%` max drawdown
  - artifact:
    - `backtest-result-2026-05-18_03-46-09.zip`
- sub-window `20260301-20260430`
  - `81` trades
  - `79.01%`
  - `1.35/day`
  - `413.89%` net profit
  - `4.075` profit factor
  - `8.46%` max drawdown
  - artifact:
    - `backtest-result-2026-05-18_03-46-25.zip`
- sub-window `20260401-20260518`
  - `68` trades
  - `75.0%`
  - `1.48/day`
  - `208.16%` net profit
  - `2.631` profit factor
  - `8.17%` max drawdown
  - artifact:
    - `backtest-result-2026-05-18_03-46-38.zip`

## Interpretation

- active `1h` base đã giải được lỗi timing của hybrid cũ:
  - không còn mất trade baseline chỉ vì bar `30m` đầu bị block
- extra edge đến từ:
  - `30m displacement short`
  - nhưng chỉ khi `1h` vẫn đang bearish theo `EMA20`
- cadence tăng rõ từ `1.08/day` lên `1.33/day`
- `win_rate` không những không giảm mà còn tăng nhẹ ở full window

## Final verify

- variant pass trên cả `4` window đã test
- batch verify cuối chạy bằng đúng `config/config.futures.json` hiện tại, không cần `-i` hay `--max-open-trades` override
- metrics user yêu cầu đều pass:
  - cadence `1.2 -> 1.5/day`
  - `win_rate` không giảm
- linked experiment:
  - `E011`
