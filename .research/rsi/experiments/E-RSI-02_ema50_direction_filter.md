# E-RSI-02 - Add a 1h EMA50 direction filter

## Hypothesis

- `H-RSI-02`

## Scope

- base: H-RSI-01 regular divergence events
- changed variable: one `1h EMA50` direction filter
- timerange: `20260524-20260623`
- basket, fee, protections, and `1m` detail unchanged

## Result

- trades: `104`
- net profit: `-17.00%`
- max drawdown: `35.51%`
- final balance: `829.974 USDT`
- long: `-38.19%`; short: `+21.18%`

## Conclusion

- `discard`
- overtrading fell, but the branch remains negative and above the drawdown ceiling; no WFO

## Linked run

- `.research/rsi/runs/2026-09-10_rsi_divergence_screening.md#h-rsi-02--1h-ema50-direction-filter`
