# H007

## Title

Simple filtering of the current basket / side / signal can push `win_rate > 70%` while maintaining cadence of `1 -> 1.5 trade/day`.

## Why this exists

- the current snapshot after `D005` is at:
  - `89` trades
  - `62.9%` win rate
  - `1.01 trade/day`
- need to confirm whether we can proceed with light pruning / filtering or must change thesis.

## Success criteria

- on the same window `2026-02-18 04:00:00 -> 2026-05-17 17:00:00`
- simultaneously achieve:
  - `win_rate > 70%`
  - cadence in the range of `1 -> 1.5 trade/day`
- no new signal branches added.

## Falsifiers

- all pruning / filtering variants only reach `>70%` when trades drop below the cadence target
- or no variant reaches `>70%` across the valid trade region.
