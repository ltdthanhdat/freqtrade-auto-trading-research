# Freqtrade Live Trade Note

## Mục tiêu

Chạy `dry-run` trước, rồi mới `live`.

## Flow tối thiểu

1. Cài dependencies:

```bash
uv sync
```

2. Tạo config local:

```bash
cp config/config.futures.json user_data/config.futures.local.json
```

3. Điền API key trong file local nếu muốn chạy thật.

4. Dry-run trước:

```bash
uv run freqtrade trade \
  --config user_data/config.futures.local.json \
  --strategy SMC_FVG_PinBar_Freqtrade \
  --strategy-path src/strategies
```

## Khuyến nghị hiện tại

- không bật live thật ngay
- basket mặc định:
  - `BTC/USDT:USDT`
  - `PLAY/USDT:USDT`
  - `BIO/USDT:USDT`
  - `SPACE/USDT:USDT`
  - `PENDLE/USDT:USDT`
  - `BR/USDT:USDT`
  - `D/USDT:USDT`
  - `YGG/USDT:USDT`
  - `STG/USDT:USDT`
- timeframe:
  - `1h`
- risk rollout:
  - vẫn giữ `max_open_trades = 1` để dry-run portfolio theo kiểu rất bảo thủ
  - nghĩa là bot quét cả `9` pair nhưng chỉ giữ tối đa `1` vị thế cùng lúc

Sau khi dry-run ổn mới cân nhắc nới `max_open_trades`.

## Lưu ý

- Freqtrade không cần license riêng kiểu Jesse live plugin.
- Nhưng vẫn cần:
  - exchange API key
  - config futures đúng
  - pair tồn tại và có metadata đầy đủ
