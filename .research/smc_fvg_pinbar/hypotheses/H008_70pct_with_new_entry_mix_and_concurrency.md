# H008

## Title

Adjusting the current entry mix and allowing `max_open_trades = 2` can exceed `70% win_rate` while maintaining cadence of `1 -> 1.5 trade/day`.

## Why this exists

- `H007` eliminated the prune / filter-only approach on the `max_open_trades = 1` snapshot.
- need to test whether the new objective can be achieved with minimal changes to:
  - signal priority
  - signal thresholds
  - basket
  - concurrency

## Success criteria

- on the same window `2026-02-18 04:00:00 -> 2026-05-17 17:00:00`
- simultaneously achieve:
  - `win_rate > 70%`
  - cadence in the range of `1 -> 1.5 trade/day`
- no new signal family added
- drawdown does not worsen uncontrollably compared to the previous accepted snapshot

## Falsifiers

- all variants reach `>70%` but cadence drops below `1/day`
- or cadence is met but `win_rate` remains below `70%`
- or new entry logic beyond the minimal tuning scope must be added
