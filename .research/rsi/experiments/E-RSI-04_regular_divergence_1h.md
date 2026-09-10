# E-RSI-04 - Move regular divergence execution to 1h

## Hypothesis

- `H-RSI-04`

## Scope

- changed variable: execution timeframe `30m` → `1h`
- regular divergence logic, basket, stop, fee, protections, and `1m` detail unchanged
- timerange: `20260524-20260623`

## Result

- trades: `106`
- net profit: `+26.29%`
- max drawdown: `40.44%`
- one trade lost `-86.74%`

## Conclusion

- `discard`
- positive raw return does not pass the fixed drawdown screen; do not advance to WFO

## Linked run

- `.research/rsi/runs/2026-09-10_rsi_divergence_screening.md#h-rsi-04--regular-divergence-on-1h`
