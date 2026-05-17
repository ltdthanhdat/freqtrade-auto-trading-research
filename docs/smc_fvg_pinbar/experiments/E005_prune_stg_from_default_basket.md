# E005 - Prune `STG/USDT:USDT` khỏi default basket

## Hypothesis

- `H006`

## Scope

- giữ nguyên strategy logic
- giữ nguyên timeframe
- giữ nguyên risk config
- chỉ bỏ `STG/USDT:USDT` khỏi basket

## Verify

- cùng timerange `20260218-20260518`
- cùng dataset futures full range
- compare basket-level metrics trước và sau khi prune

## Goal

- xác nhận một bước prune đơn giản có đưa snapshot hiện tại gần target hơn không

## Conclusion

- `keep`
- basket sau prune:
  - chạm target drawdown
  - tăng `win_rate`, `profit_factor`, `net_profit_pct`
  - vẫn giữ `89` trades, đủ cadence
- snapshot mới còn thiếu khoảng `2.1` điểm win rate so với target chính
