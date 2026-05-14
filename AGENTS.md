# AGENTS.md

Guidelines riêng cho nhánh `freqtrade-template`.

## Scope

Repo con này là nhánh execution / migration của `SMC_FVG_PinBar` sang `Freqtrade`.

Mục tiêu ưu tiên:

1. giữ strategy gần Jesse đủ để compare
2. validate parity bằng backtest có thể lặp lại
3. chỉ sau đó mới dry-run / live

## Think before editing

- Không giả định parity đã đúng chỉ vì baseline khớp.
- Phải phân biệt:
  - lệch do bug port
  - lệch do assumption backtest engine
  - lệch do futures metadata của Freqtrade
- Nếu không rõ lệch nằm ở đâu, dừng và ghi hypothesis trước.

## Simplicity first

- Không thêm indicator / filter mới nếu user chưa yêu cầu.
- Không optimize sớm.
- Không chuyển nhiều biến cùng lúc trong một vòng parity hoặc tuning.
- Không viết thêm infra live phức tạp khi dry-run còn chưa validate xong.

## Surgical changes

- Write scope mặc định:
  - `src/strategies/SMC_FVG_PinBar_Freqtrade.py`
  - `config/config.futures.json`
  - `scripts/prepare_smc_fvg_pinbar_data.py`
  - `scripts/compare_smc_fvg_pinbar_with_jesse.py`
  - `docs/`
- Không sửa strategy Jesse ở repo root trừ khi user yêu cầu.
- Không sửa docs research Jesse cũ chỉ để đổi wording.

## Goal-driven execution

Mỗi task nên map thành goal rõ:

- `port strategy`:
  - verify:
    - strategy load được trong Freqtrade
    - backtest baseline chạy được
- `improve parity`:
  - verify:
    - compare script chạy được
    - diff giảm trên đúng case mục tiêu
- `prepare live`:
  - verify:
    - config chạy được ở dry-run
    - pair / futures mode hợp lệ

## Current source of truth

Đọc theo thứ tự:

1. `docs/state/smc_fvg_pinbar_freqtrade_state.md`
2. `docs/notes/smc_fvg_pinbar_freqtrade_notes.md`
3. `docs/research/smc_fvg_pinbar_freqtrade_migration_validation.md`
4. `docs/plans/smc_fvg_pinbar_freqtrade_tuning_plan.md`

## Research / tuning discipline

- Mỗi vòng chỉ đổi `1` hypothesis.
- Luôn so với case gốc trước:
  - `BTC-USDT` baseline
  - rồi mới tới recent basket
- Nếu kết quả làm baseline xấu đi rõ, mặc định discard.
- Khi kết thúc một loop có ý nghĩa:
  - update `docs/state/`
  - update `docs/research/`
  - nếu cần, update `docs/notes/`

## Response style

- Trả lời ngắn.
- Nêu rõ:
  - hypothesis
  - verify
  - keep hoặc discard
