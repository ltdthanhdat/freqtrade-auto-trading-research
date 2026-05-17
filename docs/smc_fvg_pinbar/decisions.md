# SMC_FVG_PinBar Decisions

## D001 - Keep FVG threshold `0.45 / 0.55`

- ngày:
  - `2026-05-14`
- status:
  - `keep`
- hypothesis:
  - `H001`
- supporting experiments:
  - `E001`
  - `E002`
- supporting runs:
  - `2026-05-14_btc_20260213_20260514_fvg_thresholds.md`
  - `2026-05-14_basket_20260213_20260514_fvg_thresholds.md`
- decision:
  - giữ `FVG_RETRACE_RATIO = 0.45`
  - giữ `FVG_CONFIRM_RATIO = 0.55`
- reason:
  - kết quả tốt hơn baseline `0.35 / 0.65`
  - không làm flow hiện tại phức tạp hơn
- state impact:
  - freeze threshold này cho phase `dry-run`

## D002 - Freeze tuning, chuyển sang dry-run

- ngày:
  - `2026-05-14`
- status:
  - `keep`
- hypothesis:
  - `H002`
- supporting experiments:
  - `E003`
- supporting runs:
  - none
- decision:
  - dừng tuning mù
  - ưu tiên execution validation bằng `dry-run`
- reason:
  - flow data và execution phải ổn định trước khi tối ưu thêm
- state impact:
  - roadmap hiện tại chuyển sang `freeze strategy cho dry-run`

## D003 - Keep explicit Binance demo futures URL override

- ngày:
  - `2026-05-17`
- status:
  - `keep`
- hypothesis:
  - `Binance demo futures key trade được qua Freqtrade nếu config exchange đi đúng demo endpoint`
- supporting experiments:
  - none
- supporting runs:
  - `2026-05-17_binance_demo_freqtrade_validation.md`
- decision:
  - giữ config demo riêng cho `Binance` futures
  - giữ override explicit `exchange.ccxt_config.urls.api.fapi*`
  - giữ override tương tự cho `exchange.ccxt_async_config.urls.api.fapi*`
  - giữ mô hình `base + env override` để switch `demo/live`
- reason:
  - `enableDemoTrading = true` một mình chưa làm path futures của Freqtrade đi sang `demo-fapi.binance.com`
  - khi override explicit URL, auth + create/cancel order + bot startup đều pass
- state impact:
  - có đường verify execution thật trên demo trước khi dry-run/live rollout tiếp

## D004 - Keep leverage-aware risk handling

- ngày:
  - `2026-05-18`
- status:
  - `keep`
- hypothesis:
  - `H005`
- supporting experiments:
  - `E004`
- supporting runs:
  - `2026-05-18_basket_20260218_20260518_leverage_aware_comparison.md`
- decision:
  - giữ logic `custom_stake_amount` chia thêm cho `leverage`
  - giữ `smc_target_roi = risk_ratio * trade.leverage`
  - giữ `custom_roi` trả leverage-aware target
- reason:
  - baseline cũ có `win_rate` cao hơn nhưng `drawdown` quá xa target
  - baseline mới giảm `drawdown` từ `23.18%` xuống `12.92%`
  - `profit_factor` tăng từ `1.22` lên `1.75`
  - `net_profit_pct` tăng từ `23.84%` lên `140.19%`
- state impact:
  - baseline full-window hiện tại đủ sạch để chuyển sang phase `basket pruning`

## D005 - Keep prune `STG/USDT:USDT` khỏi default basket

- ngày:
  - `2026-05-18`
- status:
  - `keep`
- hypothesis:
  - `H006`
- supporting experiments:
  - `E005`
- supporting runs:
  - `2026-05-18_basket_20260218_20260518_prune_stg.md`
- decision:
  - bỏ `STG/USDT:USDT` khỏi `config/config.futures.json`
- reason:
  - `win_rate` tăng từ `61.1%` lên `62.9%`
  - `profit_factor` tăng từ `1.75` lên `1.97`
  - `net_profit_pct` tăng từ `140.19%` lên `164.41%`
  - `max_drawdown_pct` giảm từ `12.92%` xuống `10.74%`
  - trades vẫn còn `89`, cao hơn target cadence
- state impact:
  - snapshot hiện tại đã `near target`
  - pair âm còn lại tập trung ở `BTC` và `D`
