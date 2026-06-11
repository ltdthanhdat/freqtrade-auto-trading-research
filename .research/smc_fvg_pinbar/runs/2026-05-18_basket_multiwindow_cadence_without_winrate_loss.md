# Run - Multi-window cadence without win-rate loss

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

- increased `max_open_trades = 3`
  - full window:
    - `96` trades
    - `70.8%`
    - `1.09/day`
  - earliest sub-window:
    - `59` trades
    - `69.5%`
    - `1.02/day`
  - conclusion:
    - increase too small, does not hit cadence target
  - full-window artifact:
    - `backtest-result-2026-05-18_02-45-31.zip`
- increased `max_open_trades = 4`
  - results match `max_open_trades = 3`
  - no new edge found
  - full-window artifact:
    - `backtest-result-2026-05-18_02-46-22.zip`
- relaxed `displacement` to `body_ratio = 0.45`, `close_extreme_ratio = 0.35`
  - full window:
    - `102` trades
    - `67.7%`
    - `1.16/day`
  - earliest sub-window:
    - `62` trades
    - `66.1%`
    - `1.07/day`
  - conclusion:
    - cadence increases but `win_rate` drops noticeably
  - full-window artifact:
    - `backtest-result-2026-05-18_02-51-55.zip`
- relaxed only `pin_bar short` with `body_ratio = 0.40`
  - full window:
    - `102` trades
    - `69.6%`
    - `1.16/day`
  - earliest sub-window:
    - `61` trades
    - `70.5%`
    - `1.05/day`
  - conclusion:
    - has not hit cadence target
    - full-window `win_rate` still below baseline
  - full-window artifact:
    - `backtest-result-2026-05-18_02-56-48.zip`
- relaxed only `pin_bar short` with `body_ratio = 0.40`, `wick_to_body = 2.0`
  - full window:
    - `105` trades
    - `68.6%`
    - `1.19/day`
  - earliest sub-window:
    - `62` trades
    - `71.0%`
    - `1.07/day`
  - conclusion:
    - nearly hits cadence target
    - but full-window `win_rate` drops too noticeably
  - full-window artifact:
    - `backtest-result-2026-05-18_02-58-06.zip`

## Interpretation

- the last window `20260401-20260518` is naturally already in the `1.22/day` range, so tuning based on this window easily leads to overfitting
- the real bottleneck lies in the earlier windows:
  - `20260218-20260418`
  - `20260301-20260430`
- the minimal levers available can:
  - raise cadence to the `1.16 -> 1.19/day` range
  - or maintain `win_rate`
- but no variant achieves both simultaneously at the basket level

## Final verify

- strategy tree reverted to the accepted snapshot after all variants failed
- current truth unchanged:
  - holds `D007` as accepted baseline
- linked experiment:
  - `E008`
