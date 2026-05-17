# SMC_FVG_PinBar Current State

Ngày cập nhật: 2026-05-18

## Current truth

- strategy:
  - `src/strategies/SMC_FVG_Confirmation_Freqtrade.py`
- default basket:
  - `8` pairs
- execution engine:
  - `Freqtrade`
- timeframe mặc định:
  - `1h`
- market mode:
  - `futures`
  - `cross`
  - `can_short = True`
- data source:
  - dùng data do `freqtrade download-data` seed vào `user_data/data`
- demo execution validation:
  - `Binance` demo futures key đã verify được qua `CCXT` và `Freqtrade`
  - config demo cần override explicit `fapi` demo URLs

## Active settings

- FVG threshold đang giữ:
  - `FVG_RETRACE_RATIO = 0.45`
  - `FVG_CONFIRM_RATIO = 0.55`
- leverage-aware risk handling đang giữ:
  - `custom_stake_amount` scale theo `distance_ratio * leverage`
  - `smc_target_roi` scale theo `trade.leverage`
- sizing intent:
  - risk `5%`
  - cap `25% capital`
- target / stop handling:
  - dùng callback của strategy

## Current phase

- phase:
  - `near target snapshot sau basket pruning`
- objective gần nhất:
  - giữ snapshot hiện tại làm baseline vận hành cho `dry-run`, chỉ tune tiếp nếu cần ép chạm `65%`

## Latest accepted snapshot

- source decision:
  - `D001`
  - `D003`
  - `D004`
  - `D005`
- source experiments:
  - `E001`
  - `E002`
  - `E004`
  - `E005`
- summary:
  - baseline sạch full window `2026-02-18 -> 2026-05-17` hiện tại đạt:
    - `89` trades
    - `62.9%` win rate
    - `164.41%` net profit
    - `1.97` profit factor
    - `10.74%` max drawdown
  - snapshot hiện tại đã `near target`
  - còn thiếu khoảng `2.1` điểm để chạm `win_rate >= 65%`
  - pair âm rõ nhất hiện tại là `BTC` và `D`

## Next step

1. nếu cần thêm `1` vòng tuning, test prune `1` pair âm còn lại ở basket level
2. ưu tiên:
   - `BTC/USDT:USDT`
3. nếu không cần ép chạm `65%`, snapshot hiện tại đã đủ điều kiện `near target`
