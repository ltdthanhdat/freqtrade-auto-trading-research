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

## D006 - Discard prune / filter-only path cho target `>70%`

- ngày:
  - `2026-05-18`
- status:
  - `discard`
- hypothesis:
  - `H007`
- supporting experiments:
  - `E006`
- supporting runs:
  - `2026-05-18_basket_20260218_20260517_filtering_vs_70pct_target.md`
- decision:
  - không theo hướng prune / filter nhẹ nữa cho objective `>70% win_rate`
- reason:
  - trên window `2026-02-18 04:00:00 -> 2026-05-17 17:00:00`, cadence target `1 -> 1.5/day` tương đương `88 -> 132` trades
  - baseline hiện tại chỉ có `89` trades và `56` wins
  - mọi cách chỉ lọc bớt trade hiện có đều không thể nâng lên `62/63` wins cần thiết để vượt `70%`
  - các test prune / threshold / bias thực tế cũng không cho variant nào đạt target
- state impact:
  - nếu tiếp tục tune cho objective mới thì phải đổi thesis
  - hướng tiếp theo nên là tạo / thay thế entry logic thay vì chỉ filter basket hiện tại

## D007 - Keep `max_open_trades = 2` + prune `BTC/D` + displacement-first entry mix

- ngày:
  - `2026-05-18`
- status:
  - `keep`
- hypothesis:
  - `H008`
- supporting experiments:
  - `E007`
- supporting runs:
  - `2026-05-18_basket_20260218_20260518_70pct_breakthrough.md`
- decision:
  - giữ `max_open_trades = 2`
  - bỏ `BTC/USDT:USDT`
  - bỏ `D/USDT:USDT`
  - giữ signal priority `displacement -> trend_body -> pin_bar`
  - giữ `displacement body_ratio >= 0.55`
  - giữ `displacement close_extreme_ratio = 0.25`
  - giữ `PIN_BAR_WICK_TO_BODY = 2.5`
- reason:
  - trên full window đạt đồng thời:
    - `95` trades
    - `70.5%` win rate
    - `1.08/day`
    - `287.21%` net profit
    - `2.56` profit factor
    - `9.78%` max drawdown
  - đây là biến thể đầu tiên vượt hẳn objective mới mà không cần thêm family signal mới
- state impact:
  - snapshot accepted hiện tại đã vượt target `>70%`
  - basket mặc định giảm còn `6` pairs
  - phase tiếp theo nên chuyển về validation vận hành thay vì tune tiếp

## D008 - Discard minimal cadence-only tuning cho objective `1.2 -> 1.5/day`

- ngày:
  - `2026-05-18`
- status:
  - `discard`
- hypothesis:
  - `H009`
- supporting experiments:
  - `E008`
- supporting runs:
  - `2026-05-18_basket_multiwindow_cadence_without_winrate_loss.md`
- decision:
  - không keep các lever tối thiểu:
    - `max_open_trades = 3/4`
    - nới `displacement`
    - nới riêng `pin_bar short`
- reason:
  - `max_open_trades = 3/4` chỉ nâng full-window từ `1.08/day` lên `1.09/day`
  - nới `displacement` lên `102` trades và `1.16/day` nhưng `win_rate` giảm còn `67.7%`
  - nới riêng `pin_bar short` mạnh nhất lên `105` trades và `1.19/day` nhưng `win_rate` giảm còn `68.6%`
  - các window sớm hơn vẫn chỉ ở vùng `1.05 -> 1.17/day`, nên không có bằng chứng edge bền vững
- state impact:
  - current accepted snapshot vẫn là `D007`
  - nếu tiếp tục objective cadence mới thì phải đổi thesis
  - không nên tiếp tục vặn threshold hiện tại

## D009 - Discard simple add-on branches cho objective cadence mới

- ngày:
  - `2026-05-18`
- status:
  - `discard`
- hypothesis:
  - `H010`
- supporting experiments:
  - `E009`
- supporting runs:
  - `2026-05-18_basket_multiwindow_simple_addon_branches.md`
- decision:
  - không keep các branch add-on:
    - `reclaim`
    - `reclaim + EMA20`
    - `engulfing + EMA20`
- reason:
  - `reclaim` đạt `1.31/day` nhưng `win_rate` chỉ còn `67.8%`
  - `reclaim + EMA20` còn `67.9%`
  - `engulfing + EMA20` còn `67.6%`
  - các window sớm nhất đều kém hơn baseline rõ rệt
- state impact:
  - current accepted snapshot vẫn là `D007`
  - objective cadence mới chưa có path sạch trong phạm vi:
    - concurrency
    - threshold loosening
    - simple add-on branches
  - nếu tiếp tục, thesis tiếp theo nên là execution timeframe nhỏ hơn nhưng giữ context `1h`

## D010 - Discard `30m execution + 1h context` cho current constraints

- ngày:
  - `2026-05-18`
- status:
  - `discard`
- hypothesis:
  - `H011`
- supporting experiments:
  - `E010`
- supporting runs:
  - `2026-05-18_basket_30m_execution_with_1h_context.md`
- decision:
  - không keep hướng:
    - raw `30m`
    - exact `1h signal` gate
    - `30m displacement short` dưới `1h EMA20` bearish context
    - `30m displacement short` dưới `1h active bearish FVG + bear candle`
- reason:
  - raw `30m` chỉ cho khoảng `49%` win rate
  - hybrid tốt nhất chỉ đạt near-miss:
    - `104` trades
    - `1.18/day`
    - `70.19%`
  - biến thể chạm cadence rõ hơn:
    - `112` trades
    - `1.27/day`
    - nhưng `69.64%`
  - vì vậy vẫn chưa thỏa đồng thời:
    - cadence `1.2 -> 1.5/day`
    - `win_rate >= 70.5%`
- state impact:
  - current accepted snapshot vẫn là `D007`
  - objective cadence mới chưa có path sạch trong phạm vi:
    - threshold loosening
    - simple add-on branches
    - `30m execution + 1h context`
  - nếu tiếp tục, phải chấp nhận một thesis lớn hơn hoặc nới requirement

## D011 - Keep hybrid `30m` strategy với active `1h` base

- ngày:
  - `2026-05-18`
- status:
  - `keep`
- hypothesis:
  - `H012`
- supporting experiments:
  - `E011`
- supporting runs:
  - `2026-05-18_basket_30m_hybrid_active_base.md`
- decision:
  - dùng `src/strategies/SMC_FVG_Context30m_Freqtrade.py`
  - giữ timeframe `30m`
  - giữ informative context `1h`
  - giữ `max_open_trades = 3`
  - giữ baseline `1h` signal active trên cả hai nến `30m` tương ứng
  - giữ extra:
    - `30m displacement short`
    - khi `1h close < EMA20`
    - và `1h EMA20 slope < 0`
- reason:
  - full window đạt đồng thời:
    - `117` trades
    - `70.94%`
    - `1.33/day`
    - `424.35%` net profit
    - `2.593` profit factor
    - `8.17%` max drawdown
  - các sub-window cũng đều giữ:
    - cadence `1.22 -> 1.48/day`
    - `win_rate 71.83% -> 79.01%`
- state impact:
  - current accepted snapshot đổi từ `D007` sang hybrid `30m`
  - objective cadence mới đã pass mà không cần pair-specific rule
  - phase tiếp theo quay lại execution validation với strategy mới
