# AGENTS

Repo này là repo Freqtrade độc lập cho `SMC_FVG_PinBar`.

## Mục tiêu

1. seed data đúng format Freqtrade
2. backtest lặp lại được
3. rồi mới dry-run / live

## Cách làm

- Nghĩ trước khi sửa.
- Nếu có nhiều khả năng, nói rõ assumption.
- Nếu chưa rõ lỗi nằm ở đâu, ghi hypothesis trước.
- Mỗi vòng chỉ đổi `1` ý.

## Rule sửa code

- Sửa tối thiểu.
- Không thêm feature ngoài scope.
- Không refactor lan sang chỗ không liên quan.
- Không optimize sớm.

## Write scope mặc định

- `src/strategies/SMC_FVG_PinBar_Freqtrade.py`
- `config/config.futures.json`
- `scripts/seed_freqtrade_data.py`
- `docs/`

## Verify

- `seed data`
  - data download được
  - output nằm đúng `user_data/data`
- `backtest`
  - strategy load được
  - backtest chạy được
- `dry-run`
  - config futures hợp lệ
  - pair dùng đúng format Freqtrade

## Source of truth

1. `docs/state/smc_fvg_pinbar_freqtrade_state.md`
2. `docs/notes/smc_fvg_pinbar_freqtrade_notes.md`
3. `docs/plans/smc_fvg_pinbar_freqtrade_tuning_plan.md`

## Response style

- Trả lời ngắn.
- Nêu rõ:
  - hypothesis
  - verify
  - keep hoặc discard
