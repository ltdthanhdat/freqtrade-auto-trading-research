# E-RSI-03 - Screen hidden divergence on 30m

## Hypothesis

- `H-RSI-03`

## Scope

- candidate: `.research/rsi/candidates/RSI_HiddenDivergence30m_Freqtrade.py`
- changed variable: regular divergence → hidden divergence
- timerange: `20260524-20260623`
- basket, pivot confirmation, stop, fee, protections, and `1m` detail unchanged

## Result

- trades: `328`
- net profit: `-59.62%`
- max drawdown: `62.39%`
- final balance: `403.809 USDT`
- long: `-57.80%`; short: `-1.82%`

## Conclusion

- `discard`
- close the hidden-divergence branch for this sample; no WFO

## Linked run

- `.research/rsi/runs/2026-09-10_rsi_divergence_screening.md#h-rsi-03--hidden-rsi-divergence`
