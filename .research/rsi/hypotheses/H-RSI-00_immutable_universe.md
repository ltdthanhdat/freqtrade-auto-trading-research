# H-RSI-00 - Immutable RSI research universe

## Question

- Can a point-in-time liquidity and data-coverage filter define a fixed RSI basket before any OOS return is observed?

## Why this matters

- A fixed basket prevents pair selection from leaking strategy performance into later validation.

## Variable under test

- Candidate universe eligibility:
  - active linear `USDT` swaps
  - first-90-day median `close * volume` proxy at least `20,000,000` USD/day
  - complete `1m`, `30m`, and `1h` history from `2026-01-24`

## Success criteria

- eligibility is decided before strategy returns are observed
- every retained pair has complete data for all required timeframes
- the resulting snapshot is immutable and reproducible

## Linked experiment

- `E-RSI-00`

## Status

- `confirmed` for the screening sample

## Final decision

- keep the 24-pair basket for the RSI screening sample; do not replace the six-pair production basket
