# E009 - Test simple add-on branches trên nhiều timerange

## Hypothesis

- `H010`

## Scope

- giữ nguyên basket accepted `6` pairs
- giữ nguyên timeframe `1h`
- giữ nguyên sizing / stop / roi logic
- chỉ thêm đúng `1` branch mới mỗi lần:
  - `reclaim`
  - `engulfing + EMA20 bias`

## Verify

- cùng dataset futures full range
- compare trên các window:
  - `20260218-20260518`
  - `20260218-20260418`
  - `20260301-20260430`
  - `20260401-20260518`
- check:
  - `trade/day`
  - `win_rate`
  - `profit_factor`
  - `max_drawdown_pct`

## Goal

- xác nhận thêm branch mới có tốt hơn nới threshold cũ hay không

## Conclusion

- `discard`
- `reclaim` chạm cadence nhưng kéo `win_rate` xuống `67.8%`
- `engulfing + EMA20` cũng chạm cadence nhưng kéo `win_rate` xuống `67.6%`
- các window sớm hơn xấu hơn đáng kể, nên chưa có bằng chứng branch mới này bền vững
