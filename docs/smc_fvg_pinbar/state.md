# SMC_FVG_PinBar Current State

Ngày cập nhật: 2026-05-18

## Current truth

- strategy:
  - `src/strategies/SMC_FVG_Confirmation_Freqtrade.py`
- default basket:
  - `6` pairs
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
- signal mix đang giữ:
  - priority `displacement -> trend_body -> pin_bar`
  - `displacement body_ratio >= 0.55`
  - `displacement close_extreme_ratio = 0.25`
  - `PIN_BAR_WICK_TO_BODY = 2.5`
- leverage-aware risk handling đang giữ:
  - `custom_stake_amount` scale theo `distance_ratio * leverage`
  - `smc_target_roi` scale theo `trade.leverage`
- sizing intent:
  - risk `5%`
  - cap `25% capital`
- target / stop handling:
  - dùng callback của strategy
- concurrency:
  - `max_open_trades = 2`

## Current phase

- phase:
  - `accepted >70% snapshot`
- objective gần nhất:
  - giữ snapshot mới này làm baseline vận hành
  - ưu tiên execution validation thay vì tune thêm

## Latest accepted snapshot

- source decision:
  - `D001`
  - `D003`
  - `D004`
  - `D005`
  - `D006`
  - `D007`
- source experiments:
  - `E001`
  - `E002`
  - `E004`
  - `E005`
  - `E007`
- summary:
  - snapshot sạch full window `2026-02-18 -> 2026-05-17` hiện tại đạt:
    - `95` trades
    - `70.5%` win rate
    - `287.21%` net profit
    - `2.56` profit factor
    - `9.78%` max drawdown
    - `1.08 trade/day`
  - objective `>70%` đã pass trên cùng dataset
  - basket mặc định hiện tại đã bỏ `STG`, `BTC`, `D`
  - pair yếu nhất còn lại là `BR`, nhưng chưa có lý do cần prune thêm

## Next step

1. nếu giữ mục tiêu vận hành:
   - dùng snapshot hiện tại cho `dry-run`
2. nếu cần tune thêm:
   - chỉ mở hypothesis mới khi có objective khác `>70%`
