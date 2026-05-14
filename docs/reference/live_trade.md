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
- ưu tiên:
  - `BTC/USDT:USDT`
  - `1h`
  - `max_open_trades = 1`

Sau khi parity ổn hơn mới mở rộng basket.

## Lưu ý

- Freqtrade không cần license riêng kiểu Jesse live plugin.
- Nhưng vẫn cần:
  - exchange API key
  - config futures đúng
  - pair tồn tại và có metadata đầy đủ
