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
- data seed path:
  - [seed_freqtrade_data.py](/home/thanhdatle/workspace/jesse-trading-strategies/freqtrade-template/scripts/seed_freqtrade_data.py:1)
- config futures:
  - [config.futures.json](/home/thanhdatle/workspace/jesse-trading-strategies/freqtrade-template/config/config.futures.json:1)

## Validation snapshot

- current validation focus:
  - strategy load được trong Freqtrade
  - data seed được bằng format chuẩn `feather`
  - dry-run / backtest dùng cùng một nguồn data nội bộ của Freqtrade

## Current interpretation

- repo không còn phụ thuộc flow data hay compare từ engine khác
- source market data chuẩn là data do Freqtrade tự download
- bước tiếp theo là verify lại backtest và dry-run trên flow mới

## Open questions

- pair nào cần giữ trong basket mặc định
- số ngày seed mặc định bao nhiêu là đủ cho vòng backtest hiện tại
- có cần tách preset theo `backtest` và `dry-run` không

## Next recommended step

1. Seed lại data bằng script mới
2. Chạy lại backtest thuần Freqtrade
3. Dùng cùng config đó cho dry-run verify

## Related files

- `docs/notes/smc_fvg_pinbar_freqtrade_notes.md`
- `docs/plans/smc_fvg_pinbar_freqtrade_tuning_plan.md`
