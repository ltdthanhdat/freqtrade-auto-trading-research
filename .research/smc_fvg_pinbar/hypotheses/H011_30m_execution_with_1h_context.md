# H011

## Title

`30m` execution timeframe with `1h` context can raise cadence to `1.2 -> 1.5 trade/day` while keeping the accepted snapshot's `win_rate`.

## Why this exists

- `H009` and `H010` eliminated:
  - loosening thresholds
  - adding a simple branch on the same `1h` timeframe
- raw `30m` alone provides enough cadence but quality is far too poor
- need to test a more reasonable direction:
  - finer-grained execution at `30m`
  - but still keeping the `1h` context

## Success criteria

- on full window `20260218-20260518`:
  - cadence `1.2 -> 1.5/day`
  - `win_rate >= 70.5%`
- on sub-windows:
  - `20260218-20260418`
  - `20260301-20260430`
  - `20260401-20260518`
- no clear degradation pattern on the earliest window

## Falsifiers

- raw `30m` is still too far from the target
- hybrid `30m + 1h` shows a near-miss but cannot maintain `win_rate`
- or many auxiliary / pair-specific rules must be added to salvage the results
