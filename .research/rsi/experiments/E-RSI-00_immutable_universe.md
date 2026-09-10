# E-RSI-00 - Build the immutable RSI universe

## Hypothesis

- `H-RSI-00`

## Scope

- source query time: `2026-09-10T16:16:47Z`
- source universe: 30 active linear `USDT` swaps
- liquidity lookback: first 90 days, `2026-01-24`–`2026-04-24`
- eligibility proxy: median `close * volume >= 20,000,000` USD/day
- required timeframes: `1m`, `30m`, `1h`

## Verify

- snapshot: `user_data/data/snapshots/rsi_divergence_universe_2026q3_wfo`
- coverage: 24/24 retained pairs × 3 timeframes
- no detected gaps in the validation window

## Result

- retained basket: 24 pairs
- excluded before strategy returns: ATOM, INJ, PENDLE, RUNE, SEI, TIA

## Conclusion

- `keep`
- the basket is fixed for this RSI research line and does not replace the six-pair production basket

## Linked run

- `.research/rsi/runs/2026-09-10_rsi_divergence_screening.md#h-rsi-00--universe-audit`
