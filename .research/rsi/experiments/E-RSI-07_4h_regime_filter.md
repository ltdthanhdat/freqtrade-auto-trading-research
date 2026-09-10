# E-RSI-07 - Add a 4h bearish EMA50 regime filter

## Hypothesis

- `H-RSI-07`

## Scope

- base: H-RSI-06 short-only branch
- changed variable: require `4h close < 4h EMA50`
- execution/detail: `1h` / `1m`
- timerange: `20260524-20260623`
- basket, pivot, RSI, stop, fee, protections, and risk handling unchanged

## Result

- trades: `32`
- net profit: `+17.11%`
- win rate: `59.4%`
- max drawdown: `15.94%`
- final balance: `1171.064 USDT`

## Conclusion

- `discard`
- the first OOS-sized screen breaches the fixed `15%` drawdown ceiling, so no full WFO was run

## Linked runs

- `.research/rsi/runs/rsi-h007-smoke/`
- `.research/rsi/runs/2026-09-10_rsi_divergence_screening.md#h-rsi-07--short-only-regular-divergence-plus-4h-ema50-regime`
