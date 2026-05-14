# Docs

Nguồn sự thật cho tài liệu của nhánh `Freqtrade`.

## Cấu trúc

- `AGENTS.md`
  - rule ngắn để cập nhật docs đúng chỗ

- `plans/`
  - kế hoạch migration
  - kế hoạch tuning
  - kế hoạch validate

- `state/`
  - kết luận working state hiện tại
  - file đọc nhanh trước khi tiếp tục

- `notes/`
  - debug note
  - khác biệt engine giữa Jesse và Freqtrade
  - blocker còn lại

- `research/`
  - kết quả backtest
  - kết quả compare
  - migration validation

- `reference/`
  - setup note
  - live / dry-run note
  - config note

## File hiện có

- `plans/smc_fvg_pinbar_freqtrade_tuning_plan.md`
  - cách tiếp tục tuning sau khi đã port sang Freqtrade

- `state/smc_fvg_pinbar_freqtrade_state.md`
  - current state
  - current conclusion
  - next step

- `notes/smc_fvg_pinbar_freqtrade_notes.md`
  - migration note
  - các chỗ chưa khớp engine

- `research/smc_fvg_pinbar_freqtrade_migration_validation.md`
  - validate Freqtrade so với Jesse

- `reference/live_trade.md`
  - cách chạy dry-run / live bằng Freqtrade

## Rule ngắn

- plan mới -> `plans/`
- state hiện tại -> `state/`
- debug note -> `notes/`
- kết quả test dài -> `research/`
- setup / live note -> `reference/`
