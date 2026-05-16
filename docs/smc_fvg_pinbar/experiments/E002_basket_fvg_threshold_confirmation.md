# E002 - Xác nhận threshold trên basket hiện tại

## Hypothesis

- `H001`

## Scope

- basket hiện tại
- timerange:
  - `20260213-20260514`

## Goal

- kiểm tra threshold đã tốt trên `BTC` có vẫn chấp nhận được khi nhìn ở basket level không

## Metrics

- `trades_count`
- `net_profit_pct`
- `max_drawdown_pct`
- `win_rate`

## Linked runs

- `2026-05-14_basket_20260213_20260514_fvg_thresholds.md`

## Conclusion

- basket snapshot vẫn chấp nhận được với threshold `0.45 / 0.55`
- edge tổng chưa vượt xa `BTC`, nhưng đủ để freeze cho phase `dry-run`
