# SMC_FVG_PinBar Freqtrade Tuning Plan

Trạng thái:

- active
- migration phase xong bản đầu
- phase hiện tại: `parity trước, tuning sau`

## Mục tiêu

- dùng Freqtrade làm execution engine mới
- giữ strategy gần Jesse đủ để:
  - compare được
  - dry-run được
  - live được
- không tune mù khi engine parity còn chưa rõ

## Nguyên tắc

1. Mỗi vòng chỉ đổi `1` ý

- không vừa sửa signal
- vừa sửa stop
- vừa sửa sizing

2. Ưu tiên parity trước

Thứ tự:

- baseline `BTC-USDT 1h`
- recent `BTC-USDT 1h`
- recent basket các cặp còn lại

3. Chỉ tune trên Freqtrade sau khi hiểu rõ lệch do engine

Không nhầm giữa:

- bug port
- assumption khác engine
- strategy thực sự cần tune

## Scope được phép sửa

Cho phase hiện tại, chỉ nên đụng:

- `src/strategies/SMC_FVG_PinBar_Freqtrade.py`
- `config/config.futures.json`
- `scripts/prepare_smc_fvg_pinbar_data.py`
- `scripts/compare_smc_fvg_pinbar_with_jesse.py`
- docs trong `freqtrade-template/docs`

Không nên đụng:

- strategy Jesse cũ
- docs research lịch sử ở repo root

## Standard loop

1. Chọn đúng 1 case

- ví dụ:
  - `BTC-USDT` baseline
  - `BTC-USDT` recent
  - `D-USDT` recent

2. Ghi rõ hypothesis

Ví dụ:

- lệch do fill timing
- lệch do stop callback
- lệch do custom roi

3. Sửa tối thiểu

4. Chạy compare lại

5. Ghi:

- trade count
- net profit %
- max drawdown
- win rate

6. Keep / discard rõ ràng

## Metrics

- `trades_count`
- `net_profit_pct`
- `max_drawdown_pct`
- `win_rate`

Metric phụ:

- diff so với Jesse
- error do pair metadata

## Keep / discard rule

Giữ thay đổi nếu:

- trade count gần Jesse hơn
- net profit diff nhỏ hơn
- không phá baseline đang khớp tốt

Loại nếu:

- chỉ làm một case đẹp hơn nhưng phá các case còn lại

## Khi nào mới bật dry-run rộng

Chỉ nên bật dry-run nhiều pair khi:

- baseline ổn
- recent `BTC-USDT` ổn hơn hiện tại
- basket làm việc không còn pair bị blocker metadata

## Current reference

- compare output:
  - `user_data/compare/smc_fvg_pinbar_freqtrade_vs_jesse.md`
- source of truth state:
  - `docs/state/smc_fvg_pinbar_freqtrade_state.md`
