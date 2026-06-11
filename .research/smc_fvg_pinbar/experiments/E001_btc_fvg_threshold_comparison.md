# E001 - FVG Threshold Comparison on BTC

## Hypothesis

- `H001`

## Scope

- pair:
  - `BTC/USDT:USDT`
- timeframe:
  - `1h`
- timerange:
  - `20260213-20260514`

## Compared variants

- baseline:
  - `0.35 / 0.65`
- tighter:
  - `0.25 / 0.75`
- looser:
  - `0.45 / 0.55`

## Metrics

- `trades_count`
- `net_profit_pct`
- `max_drawdown_pct`
- `win_rate`

## Linked runs

- `2026-05-14_btc_20260213_20260514_fvg_thresholds.md`

## Conclusion

- variant `0.45 / 0.55` performed best in this test set
- sufficient evidence to support `D001`
