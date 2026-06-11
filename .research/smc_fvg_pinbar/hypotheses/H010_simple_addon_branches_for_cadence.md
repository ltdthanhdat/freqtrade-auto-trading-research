# H010

## Title

Adding `1` simple new entry branch on the same `1h FVG` context can raise cadence to `1.2 -> 1.5 trade/day` while keeping the accepted snapshot's `win_rate`.

## Why this exists

- `H009` eliminated the direction of:
  - increasing `max_open_trades`
  - loosening thresholds on existing branches
- need to test a different thesis while still being minimal:
  - keep the accepted basket
  - keep the `1h` timeframe
  - add exactly `1` new candle pattern branch

## Success criteria

- on full window `20260218-20260518`:
  - cadence `1.2 -> 1.5/day`
  - `win_rate >= 70.5%`
- on sub-windows:
  - `20260218-20260418`
  - `20260301-20260430`
  - `20260401-20260518`
- no signs of only passing on the last window
- no pair-specific rules used

## Falsifiers

- new branch achieves cadence but full-window `win_rate` drops noticeably
- or the earliest window drops more than the full window
- or multiple additional filters are needed to salvage the branch
