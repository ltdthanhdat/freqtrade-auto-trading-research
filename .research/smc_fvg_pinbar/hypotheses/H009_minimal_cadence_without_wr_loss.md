# H009

## Title

The current minimal tuning can raise cadence to `1.2 -> 1.5 trade/day` across multiple timeranges without pulling `win_rate` below the accepted snapshot.

## Why this exists

- the accepted snapshot after `D007` is at:
  - `95` trades
  - `70.5%` win rate
  - `1.08 trade/day`
- the new objective is to increase cadence without overfitting:
  - keep the current basket
  - keep the current signal family
  - verify across multiple windows instead of just `1` full range

## Success criteria

- on full window `20260218-20260518`:
  - cadence in the range of `1.2 -> 1.5 trade/day`
  - `win_rate >= 70.5%`
- on sub-windows:
  - `20260218-20260418`
  - `20260301-20260430`
  - `20260401-20260518`
- no clear downward trend in `win_rate` compared to the baseline on the same window
- no new signal family added

## Falsifiers

- all variants only raise cadence to around `1.1x/day`
- or cadence reaches the target but `win_rate` drops below the accepted snapshot
- or only passes on the last window but fails on earlier windows
