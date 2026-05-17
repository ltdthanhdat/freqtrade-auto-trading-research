# E004 - Compare leverage-aware risk handling trên clean baseline

## Hypothesis

- `H005`

## Scope

- không đổi basket
- không đổi threshold entry
- không đổi timeframe
- chỉ compare:
  - strategy ở `HEAD` cũ
  - strategy hiện tại với:
    - `custom_stake_amount` chia thêm cho `leverage`
    - `smc_target_roi` nhân với `trade.leverage`
    - `custom_roi` trả ROI theo leverage-aware risk

## Verify

- cùng timerange `20260218-20260518`
- cùng config futures
- cùng dataset futures vừa seed lại full range

## Goal

- xác nhận thay đổi leverage-aware có phải là improvement đáng giữ trước khi prune basket

## Conclusion

- `keep`
- baseline mới không đạt `win_rate >= 65%`, nhưng profile tổng thể gần target hơn rõ:
  - drawdown giảm mạnh
  - profit factor tăng
  - profit dương lớn hơn nhiều
- bước kế tiếp nên là `basket pruning`, không quay lại sizing cũ
