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
  - raise cadence to `1.2 -> 1.5/day`
  - without lowering `win_rate` below the accepted snapshot

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
  - cadence is sufficient
  - quality is completely broken
- artifacts:
  - `backtest-result-2026-05-18_03-16-09.zip`
  - `backtest-result-2026-05-18_03-16-21.zip`
  - `backtest-result-2026-05-18_03-16-34.zip`
  - `backtest-result-2026-05-18_03-16-44.zip`

## Hybrid attempts

- `30m` gated by exact accepted `1h signal`
  - full window:
    - `15` trades
    - `73.33%`
    - `0.17/day`
  - interpretation:
    - high quality but cadence is almost entirely lost
  - artifact:
    - `backtest-result-2026-05-18_03-23-16.zip`
- `30m` + accepted `1h` base entries + extra `30m displacement short` when:
  - `1h close < EMA20`
  - `1h EMA20 slope < 0`
  - `max_open_trades = 2`
  - full window:
    - `106` trades
    - `69.81%`
    - `1.20/day`
  - interpretation:
    - cadence hits the lower bound
    - `win_rate` still below baseline
  - artifact:
    - `backtest-result-2026-05-18_03-24-54.zip`
- same hybrid above with `max_open_trades = 3`
  - full window:
    - `104` trades
    - `70.19%`
    - `1.18/day`
  - interpretation:
    - this is the best near-miss of this round
    - `win_rate` is closer to baseline
    - but cadence still falls below `1.2/day`
  - artifact:
    - `backtest-result-2026-05-18_03-29-25.zip`
- `30m displacement short` when:
  - `1h active bearish FVG`
  - `1h bear candle`
  - `max_open_trades = 3`
  - full window:
    - `112` trades
    - `69.64%`
    - `1.27/day`
  - interpretation:
    - cadence passes
    - `win_rate` fails
  - artifact:
    - `backtest-result-2026-05-18_03-33-44.zip`

## Interpretation

- switching to `30m` execution does solve the cadence problem
- but every time cadence hits the target, `win_rate` drops below baseline
- the best hybrid so far is still only a near-miss:
  - `104` trades
  - `1.18/day`
  - `70.19%`
- therefore this thesis does not have sufficient evidence to promote to current truth

## Final verify

- strategy experiment has been removed from the tree after the run failed
- current truth unchanged:
  - still holds `D007`
- linked experiment:
  - `E010`
