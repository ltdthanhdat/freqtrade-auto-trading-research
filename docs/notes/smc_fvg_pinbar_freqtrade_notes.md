# SMC_FVG_PinBar Freqtrade Notes

Ngày cập nhật: 2026-05-14

## Mục tiêu

Lưu debug history và các phát hiện kỹ thuật khi port `SMC_FVG_PinBar` từ Jesse sang Freqtrade.

## Các quyết định migration

### 1. Không bê nguyên strategy Jesse

Strategy Jesse cũ phụ thuộc chặt vào:

- `self.candles`
- `self.buy / self.sell`
- `self.stop_loss / self.take_profit`
- `self.balance`
- `utils.risk_to_qty`

Nên đã port sang callback model của Freqtrade:

- `populate_indicators`
- `populate_entry_trend`
- `custom_stake_amount`
- `order_filled`
- `custom_stoploss`
- `custom_roi`

### 2. Entry signal không còn shift sang candle sau

Sau vòng parity gần nhất:

- bỏ `shift(1)` ở entry signal
- entry timing khớp Jesse hơn rõ rệt, nhất là `BTC-USDT` recent
- vẫn truyền `stop` qua `enter_tag`

### 3. Stop và target không hardcode bằng static config

Vì stop của strategy phụ thuộc từng FVG, nên đã dùng:

- `order_filled()` để ghi:
  - stop rate
  - signal kind
  - target roi
- `custom_stoploss()` để map stop tuyệt đối
- `custom_roi()` để giữ target `1R`

### 4. Sizing được port theo intent, không bảo đảm identical

Intent giữ lại:

- risk `2%`
- cap `25% capital`

Nhưng Freqtrade dùng:

- `custom_stake_amount`

nên kết quả rất gần, không hứa identical 100%.

## Các khác biệt engine đã thấy

### 1. Baseline khớp khá sát

- `BTC-USDT` baseline:
  - Jesse `4 trades`, `0.7393%`
  - Freqtrade `4 trades`, `0.7644%`

### 2. Recent basket lệch hơn

Các cặp lệch mạnh nhất hiện thấy:

- `BTC-USDT` recent
- `D-USDT`
- `STG-USDT`

Khả năng cao do:

- fill assumption
- exit order lifecycle
- Freqtrade futures metadata

### 3. Futures metadata không đầy đủ cho mọi pair

Case này đã bị loại khỏi basket làm việc hiện tại để tránh blocker metadata.

## Script liên quan

- data prep:
  - `scripts/prepare_smc_fvg_pinbar_data.py`
- compare:
  - `scripts/compare_smc_fvg_pinbar_with_jesse.py`

## Ghi nhớ cho vòng sau

- nếu mục tiêu là parity:
  - chỉ test `1h`
  - chỉ test `1 pair` mỗi vòng khi debug
- nếu mục tiêu là execution:
  - chấp nhận một mức lệch nhỏ
  - ưu tiên dry-run behavior trước
