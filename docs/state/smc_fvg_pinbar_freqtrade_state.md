# SMC_FVG_PinBar Freqtrade Current State

Ngày cập nhật: 2026-05-14

## Current strategy state

- strategy port hiện tại:
  - [SMC_FVG_PinBar_Freqtrade.py](/home/thanhdatle/workspace/jesse-trading-strategies/freqtrade-template/src/strategies/SMC_FVG_PinBar_Freqtrade.py:1)
- timeframe working mặc định:
  - `1h`
- mode mục tiêu:
  - `dry-run` trước
  - sau đó mới `live`
- market mode:
  - `futures`
  - `cross`
  - `can_short = True`

## What is settled

- Freqtrade support:
  - `dry-run`
  - `live trade`
  - `futures`
  - `short`
- strategy đã được port sang Freqtrade theo intent gần Jesse nhất:
  - active FVG state
  - `pin_bar OR trend_body OR displacement`
  - overlap FVG
  - stop theo FVG boundary
  - target `1R`
  - sizing kiểu:
    - risk `2%`
    - cap `25% capital`
- data prep path đã có:
  - [prepare_smc_fvg_pinbar_data.py](/home/thanhdatle/workspace/jesse-trading-strategies/freqtrade-template/scripts/prepare_smc_fvg_pinbar_data.py:1)
- compare harness Jesse vs Freqtrade đã có:
  - [compare_smc_fvg_pinbar_with_jesse.py](/home/thanhdatle/workspace/jesse-trading-strategies/freqtrade-template/scripts/compare_smc_fvg_pinbar_with_jesse.py:1)

## Validation snapshot

- baseline `BTC-USDT 1h`, `2024-01-01 -> 2024-03-01`:
  - Jesse:
    - `4 trades`
    - `0.73935024987001%`
    - `win_rate = 0.75`
  - Freqtrade:
    - `4 trades`
    - `0.7643972648%`
    - `win_rate = 1.0`
  - kết luận:
    - baseline khớp khá sát ở trade count và total profit

- recent selected basket:
  - đã compare `9` symbol trong basket làm việc hiện tại
  - `BASED-USDT` đã bị loại khỏi basket vì blocker metadata
  - trên `9` case chạy được:
    - avg abs profit diff khoảng `0.40` điểm %
    - avg trade count diff khoảng `0.5`

- recent `BTC-USDT 1h` sau patch parity:
  - Jesse:
    - `10 trades`
    - `0.7134234949907934%`
  - Freqtrade:
    - `10 trades`
    - `0.8435860044%`
  - kết luận:
    - trade count khớp
    - open timestamp khớp
    - PnL từng lệnh chỉ còn lệch nhẹ do fill / ROI handling của engine

## Current interpretation

- migration sang Freqtrade là khả thi
- chưa `drop-in identical` tuyệt đối
- nhưng đã đủ gần để coi Freqtrade là nhánh làm việc chính
- chênh lệch chủ yếu đến từ:
  - giả định fill/backtest khác engine
  - callback lifecycle khác Jesse

- patch quan trọng đã chốt:
  - bỏ `shift(1)` ở `ft_long_entry_signal`, `ft_short_entry_signal` và stop/tag entry tương ứng
  - đây là baseline parity mới

## Open questions

- có giảm thêm được lệch recent basket không
- có nên ưu tiên parity với Jesse hay chấp nhận Freqtrade là execution engine mới
- có nên giữ futures backtest cho mọi pair, hay chuyển một số cặp sang dry-run verify trước

## Next recommended step

1. Chấp nhận patch `no-shift` làm baseline mới
2. Nếu cần parity chặt hơn nữa, soi các cặp còn lệch:
   - `BIO-USDT`
   - `BR-USDT`
   - `D-USDT`
3. Có thể bắt đầu chuyển trọng tâm sang dry-run workflow của Freqtrade

## Related files

- `docs/research/smc_fvg_pinbar_freqtrade_migration_validation.md`
- `docs/notes/smc_fvg_pinbar_freqtrade_notes.md`
- `docs/plans/smc_fvg_pinbar_freqtrade_tuning_plan.md`
