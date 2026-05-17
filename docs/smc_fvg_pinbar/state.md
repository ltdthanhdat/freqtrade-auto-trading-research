# SMC_FVG_PinBar Current State

Ngày cập nhật: 2026-05-17

## Current truth

- strategy:
  - `src/strategies/SMC_FVG_PinBar_Freqtrade.py`
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
- sizing intent:
  - risk `2%`
  - cap `25% capital`
- target / stop handling:
  - dùng callback của strategy

## Current phase

- phase:
  - `freeze strategy cho dry-run`
- objective gần nhất:
  - giữ flow seed + backtest + config ổn định trước khi tune tiếp

## Latest accepted snapshot

- source decision:
  - `D001`
  - `D003`
- source experiments:
  - `E001`
  - `E002`
- summary:
  - `BTC/USDT:USDT` là nguồn edge chính trong snapshot hiện tại
  - basket hiện tại chạy được nhưng chưa chứng minh edge rộng hơn `BTC`

## Next step

1. chạy `dry-run` với config futures hiện tại
2. nếu cần execution thật, dùng config demo futures đã verify
3. log signal thật theo pair
