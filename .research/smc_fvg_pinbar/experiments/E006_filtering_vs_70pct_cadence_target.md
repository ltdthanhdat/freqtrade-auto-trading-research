# E006

## Title

Test lightweight prune/filter directions for the `>70% win_rate` target with cadence `1 -> 1.5 trade/day`.

## Linked hypothesis

- `H007`

## Experiment design

On the same futures dataset `20260218-20260518` and the strategy snapshot after `D005`, test:

1. prune basket:
   - remove `BTC`
   - remove `BTC + D`
2. lightweight filter / threshold adjustments:
   - change signal priority
   - tighten `pin_bar`
   - tighten `trend_body`
   - remove `long pin_bar`
   - add `EMA20 bias` for `pin_bar / trend_body`
3. check constraints at subset level:
   - `pair`
   - `signal_kind x side`
   - `pair x side x signal`

## Verify

- compare results on the same window `2026-02-18 04:00:00 -> 2026-05-17 17:00:00`
- see which variant simultaneously achieves:
  - `win_rate > 70%`
  - `88 -> 132` trades on this window
