# SMC_FVG_PinBar Freqtrade Current State

Ngày cập nhật: 2026-05-14

## Current strategy state

- strategy:
  - [SMC_FVG_PinBar_Freqtrade.py](/home/thanhdatle/workspace/jesse-trading-strategies/freqtrade-template/src/strategies/SMC_FVG_PinBar_Freqtrade.py:1)
- timeframe mặc định:
  - `1h`
- market mode:
  - `futures`
  - `cross`
  - `can_short = True`

## What is settled

- strategy chạy độc lập trên Freqtrade
- FVG threshold đang chốt:
  - `FVG_RETRACE_RATIO = 0.45`
  - `FVG_CONFIRM_RATIO = 0.55`
- data seed path:
  - [seed_freqtrade_data.py](/home/thanhdatle/workspace/jesse-trading-strategies/freqtrade-template/scripts/seed_freqtrade_data.py:1)
- config futures:
  - [config.futures.json](/home/thanhdatle/workspace/jesse-trading-strategies/freqtrade-template/config/config.futures.json:1)

## Validation snapshot

- current validation focus:
  - strategy load được trong Freqtrade
  - data seed được bằng format chuẩn `feather`
  - dry-run / backtest dùng cùng một nguồn data nội bộ của Freqtrade
- latest backtest snapshot:
  - `BTC/USDT:USDT`
    - timerange: `20260213-20260514`
    - `trades_count = 18`
    - `net_profit_pct = 1.20%`
    - `max_drawdown_pct = 0.67%`
    - `win_rate = 61.1%`
  - basket hiện tại
    - timerange: `20260213-20260514`
    - `trades_count = 19`
    - `net_profit_pct = 1.02%`
    - `max_drawdown_pct = 0.67%`
    - `win_rate = 57.9%`

## Current interpretation

- repo không còn phụ thuộc flow data hay compare từ engine khác
- source market data chuẩn là data do Freqtrade tự download
- strategy hiện tại đủ ổn để freeze cho phase `dry-run`
- edge hiện tại chủ yếu đến từ `BTC`

## Open questions

- pair nào cần giữ trong basket mặc định
- có nên giữ alt basket hiện tại hay thu hẹp về basket tập trung hơn
- có cần preset riêng cho `live` để quản trị rủi ro tốt hơn không

## Next recommended step

1. Dùng config hiện tại để `dry-run`
2. Theo dõi signal thật theo pair
3. Chỉ tune tiếp sau khi có log execution

## Related files

- `docs/notes/smc_fvg_pinbar_freqtrade_notes.md`
- `docs/plans/smc_fvg_pinbar_freqtrade_tuning_plan.md`
