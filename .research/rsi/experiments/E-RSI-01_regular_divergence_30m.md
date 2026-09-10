# E-RSI-01 - Screen standalone regular divergence on 30m

## Hypothesis

- `H-RSI-01`

## Scope

- candidate: `.research/rsi/candidates/RSI_Divergence30m_Freqtrade.py`
- basket: fixed 24-pair RSI snapshot
- timerange: `20260524-20260623`
- execution/detail: `30m` / `1m`
- protections: enabled
- fee: `0.001`

## Verify

- confirm pivot delay and future-prefix invariance in unit tests
- run the first OOS-sized smoke window

## Result

- trades: `235`
- net profit: `-72.21%`
- max drawdown: `73.89%`
- final balance: `277.858 USDT`
- long: `-62.62%`; short: `-9.59%`

## Conclusion

- `discard`
- do not spend the three-fold gate on this unfiltered signal; retain the causal helper as the base for the next experiment

## Linked run

- `.research/rsi/runs/2026-09-10_rsi_divergence_screening.md#h-rsi-01--regular-rsi-divergence`
