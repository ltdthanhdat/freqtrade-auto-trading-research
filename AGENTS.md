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

1. `docs/smc_fvg_pinbar/state.md`
2. `docs/smc_fvg_pinbar/decisions.md`
3. `docs/smc_fvg_pinbar/roadmap.md`
4. `docs/smc_fvg_pinbar/README.md`

## Docs flow

- Không ghi kết quả chi tiết vào `roadmap.md`.
- Luồng chuẩn:
  - `hypothesis` -> `experiment` -> `run` -> `decision` -> `state`
- Vai trò:
  - `state.md`
    - current truth của strategy
  - `decisions.md`
    - quyết định keep/discard và nguồn gốc
  - `roadmap.md`
    - phase hiện tại, thứ tự việc, open hypotheses
  - `hypotheses/`
    - từng giả thuyết riêng
  - `experiments/`
    - design của bài test
  - `runs/`
    - raw result của từng lần chạy
  - `notes/`
    - debug note và blocker vận hành
  - `reference/`
    - cách chạy và setup

## Response style

- Trả lời ngắn.
- Với tuning strategy, experiment, backtest conclusion, hoặc update docs flow:
  - nêu rõ `hypothesis`
  - `verify`
  - `keep` hoặc `discard`
- Với việc vận hành:
  - config
  - API key
  - seed data
  - dry-run / live / demo
  - lỗi runtime
  - hướng dẫn chạy
  - trả lời bình thường, ngắn, trực tiếp
  - không cần ép format `hypothesis / keep-discard`
