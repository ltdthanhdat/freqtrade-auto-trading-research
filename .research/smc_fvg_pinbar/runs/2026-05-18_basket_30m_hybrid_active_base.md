# Run - `30m` hybrid with active `1h` base

## Case

- previous baseline accepted:
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

- the active `1h` base resolved the timing issue of the previous hybrid:
  - no longer losing baseline trades just because the first `30m` bar was blocked
- extra edge comes from:
  - `30m displacement short`
  - but only when `1h` is still bearish per `EMA20`
- cadence increased noticeably from `1.08/day` to `1.33/day`
- `win_rate` not only did not decrease but even increased slightly on the full window

## Final verify

- variant passes across all `4` tested windows
- final batch verify ran with exactly the current `config/config.futures.json`, no `-i` or `--max-open-trades` overrides needed
- all user-requested metrics pass:
  - cadence `1.2 -> 1.5/day`
  - `win_rate` did not decrease
- linked experiment:
  - `E011`
