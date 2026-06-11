# Run - Multi-window simple add-on branches

## Case

- baseline accepted:
  - `D007`
  - basket `6` pairs
  - `max_open_trades = 2`
- objective:
  - raise cadence to `1.2 -> 1.5 trade/day`
  - without lowering `win_rate` below the accepted snapshot
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

- added `reclaim` branch
  - full window:
    - `115` trades
    - `67.8%`
    - `1.31/day`
  - earliest sub-window:
    - `68` trades
    - `64.7%`
    - `1.17/day`
  - interpretation:
    - cadence has entered target range
    - but `win_rate` drops too noticeably at full-window and the earliest window
  - artifacts:
    - `backtest-result-2026-05-18_03-06-27.zip`
    - `backtest-result-2026-05-18_03-06-36.zip`
- added `reclaim` + `EMA20` bias branch
  - full window:
    - `106` trades
    - `67.9%`
    - `1.20/day`
  - earliest sub-window:
    - `64` trades
    - `65.6%`
    - `1.10/day`
  - interpretation:
    - filter partially rescues cadence overshoot
    - but does not rescue `win_rate`
  - artifacts:
    - `backtest-result-2026-05-18_03-08-31.zip`
    - `backtest-result-2026-05-18_03-08-46.zip`
- added `engulfing` + `EMA20` bias branch
  - full window:
    - `108` trades
    - `67.6%`
    - `1.23/day`
  - earliest sub-window:
    - `66` trades
    - `63.6%`
    - `1.14/day`
  - interpretation:
    - cadence enters target range
    - but `win_rate` drops even worse than `reclaim + EMA20`
  - artifacts:
    - `backtest-result-2026-05-18_03-11-48.zip`
    - `backtest-result-2026-05-18_03-11-58.zip`

## Interpretation

- new single-candle add-on branches do solve the cadence shortage
- but the additional trades are not high enough quality to maintain `win_rate`
- the failure pattern is the same across branches:
  - the last window looks better
  - the earliest window is noticeably worse
- therefore continuing to search around single-candle branches would very easily lead to overfitting

## Final verify

- strategy tree reverted cleanly to the accepted snapshot
- current truth unchanged:
  - still holds `D007`
- linked experiment:
  - `E009`
