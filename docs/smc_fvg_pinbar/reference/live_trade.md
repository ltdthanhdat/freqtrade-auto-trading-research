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

3. Seed data trước:

```bash
uv run python scripts/seed_freqtrade_data.py --preset smc-basket --days 90
```

4. Điền API key trong file local nếu muốn chạy thật.

5. Dry-run trước:

```bash
uv run freqtrade trade \
  --config user_data/config.futures.local.json \
  --strategy SMC_FVG_PinBar_Freqtrade \
  --strategy-path src/strategies
```

## Binance Demo Futures

Với `Binance` futures trong stack `Freqtrade + CCXT 4.5.38`, chỉ bật
`enableDemoTrading` là chưa đủ.

Cần thêm 2 ý:

1. dùng config demo riêng:

```bash
config/config.futures.demo.local.json
```

2. điền key vào `.env`:

```bash
FREQTRADE__EXCHANGE__KEY=...
FREQTRADE__EXCHANGE__SECRET=...
```

Config demo này đang override `exchange.ccxt_config.urls.api.fapi*` và
`exchange.ccxt_async_config.urls.api.fapi*` sang:

- `https://demo-fapi.binance.com/fapi/v1`
- `https://demo-fapi.binance.com/fapi/v2`
- `https://demo-fapi.binance.com/fapi/v3`

Chạy bot:

```bash
set -a
source .env
set +a

uv run python -m freqtrade trade \
  --config config/config.futures.demo.local.json \
  --strategy SMC_FVG_PinBar_Freqtrade \
  --strategy-path src/strategies
```

## Khuyến nghị hiện tại

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
  - vẫn giữ `max_open_trades = 1` để dry-run portfolio theo kiểu bảo thủ

## Lưu ý

- Data seed dùng trực tiếp `freqtrade download-data`.
- Vẫn cần:
  - exchange API key nếu muốn live
  - config futures đúng
  - pair tồn tại và có metadata đầy đủ
