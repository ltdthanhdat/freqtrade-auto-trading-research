# SMC_FVG_PinBar Current State

Ngày cập nhật: 2026-05-18

## Current truth

- strategy:
  - `src/strategies/SMC_FVG_Context30m_Freqtrade.py`
- default basket:
  - `6` pairs
- execution engine:
  - `Freqtrade`
- timeframe mặc định:
  - `30m`
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
- signal mix đang giữ:
  - base context:
    - accepted `1h` signal giữ active trên cả hai nến `30m` tương ứng
  - extra execution edge:
    - `30m displacement short`
    - khi `1h close < EMA20`
    - và `1h EMA20 slope < 0`
- leverage-aware risk handling đang giữ:
  - `custom_stake_amount` scale theo `distance_ratio * leverage`
  - `smc_target_roi` scale theo `trade.leverage`
- sizing intent:
  - risk `5%`
  - cap `25% capital`
- target / stop handling:
  - dùng callback của strategy
- concurrency:
  - `max_open_trades = 3`

## Current phase

- phase:
  - `accepted cadence-pass snapshot`
- objective gần nhất:
  - giữ hybrid `30m` snapshot mới này làm baseline vận hành
  - ưu tiên execution validation thay vì tune thêm

## Latest accepted snapshot

- source decision:
  - `D001`
  - `D003`
  - `D004`
  - `D005`
  - `D006`
  - `D007`
  - `D008`
  - `D009`
  - `D010`
  - `D011`
- source experiments:
  - `E001`
  - `E002`
  - `E004`
  - `E005`
  - `E007`
  - `E008`
  - `E009`
  - `E010`
  - `E011`
- summary:
  - snapshot sạch full window `2026-02-18 -> 2026-05-17` hiện tại đạt:
    - `117` trades
    - `70.94%` win rate
    - `424.35%` net profit
    - `2.593` profit factor
    - `8.17%` max drawdown
    - `1.33 trade/day`
  - objective cadence mới đã pass:
    - cadence trong vùng `1.2 -> 1.5/day`
    - `win_rate` không giảm
    - verify qua `4` window
  - basket mặc định hiện tại đã bỏ `STG`, `BTC`, `D`
  - pair yếu nhất còn lại là `BR`, nhưng chưa có lý do cần prune thêm

## Next step

1. nếu giữ mục tiêu vận hành:
   - dùng snapshot hiện tại cho `dry-run`
2. nếu cần tune thêm:
   - chỉ mở hypothesis mới nếu có objective khác cadence hiện tại
