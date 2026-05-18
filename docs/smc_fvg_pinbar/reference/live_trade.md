# Freqtrade Live Trade Note

## Mục tiêu

Chạy `dry-run` trước, rồi mới `live`.

## Flow tối thiểu

1. Cài dependencies:

```bash
uv sync
```

2. Chuẩn bị config base + env override:

```bash
config/config.futures.json
config/config.binance.demo.json
config/config.binance.live.json
```

3. Seed data trước:

```bash
uv run python scripts/seed_freqtrade_data.py --preset smc-basket --days 90
```

4. Điền API key vào `.env`.

5. Dry-run trước:

```bash
set -a
source .env
set +a

uv run python -m freqtrade trade \
  --config config/config.futures.json \
  --config config/config.binance.demo.json \
  --strategy SMC_FVG_Context30m_Freqtrade \
  --strategy-path src/strategies
```

## Docker Compose

Nếu muốn giữ `demo` và `live` thành 2 service riêng, dùng `compose.yaml`.

Điền thêm vào `.env`:

```bash
FREQTRADE_DEMO_KEY=...
FREQTRADE_DEMO_SECRET=...
FREQTRADE_LIVE_KEY=...
FREQTRADE_LIVE_SECRET=...
FREQTRADE_TELEGRAM_ENABLED=false
FREQTRADE_TELEGRAM_TOKEN=
FREQTRADE_TELEGRAM_CHAT_ID=
```

Nếu muốn bot gửi Telegram, đổi:

```bash
FREQTRADE_TELEGRAM_ENABLED=true
FREQTRADE_TELEGRAM_TOKEN=<bot-token>
FREQTRADE_TELEGRAM_CHAT_ID=<chat-id>
```

Seed data trước:

```bash
uv run python scripts/seed_freqtrade_data.py --preset smc-basket --days 90
```

Chạy `demo`:

```bash
docker compose up -d freqtrade-demo
docker compose logs -f freqtrade-demo
```

Chạy `live`:

```bash
docker compose up -d freqtrade-live
docker compose logs -f freqtrade-live
```

Chạy cả hai cùng lúc:

```bash
docker compose up -d freqtrade-demo freqtrade-live
```

Dừng:

```bash
docker compose stop freqtrade-demo
docker compose stop freqtrade-live
```

Compose đang tách riêng:

- DB demo: `user_data/tradesv3.demo.sqlite`
- DB live: `user_data/tradesv3.live.sqlite`
- log demo: `user_data/logs/freqtrade-demo.log`
- log live: `user_data/logs/freqtrade-live.log`

## Binance Demo Futures

Với `Binance` futures trong stack `Freqtrade + CCXT 4.5.38`, chỉ bật
`enableDemoTrading` là chưa đủ.

Cần thêm 2 ý:

1. dùng config override theo môi trường:

```bash
config/config.binance.demo.json
config/config.binance.live.json
```

2. điền key vào `.env`:

```bash
FREQTRADE__EXCHANGE__KEY=...
FREQTRADE__EXCHANGE__SECRET=...
```

Config `demo` đang override `exchange.ccxt_config.urls.api.fapi*` và
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
  --config config/config.futures.json \
  --config config/config.binance.demo.json \
  --strategy SMC_FVG_Context30m_Freqtrade \
  --strategy-path src/strategies
```

Chuyển sang `Binance` thật:

```bash
set -a
source .env
set +a

uv run python -m freqtrade trade \
  --config config/config.futures.json \
  --config config/config.binance.live.json \
  --strategy SMC_FVG_Context30m_Freqtrade \
  --strategy-path src/strategies
```

Nghĩa là khi switch môi trường:

- đổi `.env` sang key/secret đúng môi trường
- đổi file override cuối cùng:
  - `config/config.binance.demo.json`
  - hoặc `config/config.binance.live.json`

Không cần sửa tay file base.

## Khuyến nghị hiện tại

- basket mặc định:
  - `PLAY/USDT:USDT`
  - `BIO/USDT:USDT`
  - `SPACE/USDT:USDT`
  - `PENDLE/USDT:USDT`
  - `BR/USDT:USDT`
  - `YGG/USDT:USDT`
- timeframe:
  - `30m`
- risk rollout:
  - giữ `max_open_trades = 3`

## Lưu ý

- Data seed dùng trực tiếp `freqtrade download-data`.
- Data active mặc định nằm ở `user_data/data/binance/futures`.
- Vẫn cần:
  - exchange API key nếu muốn live
  - config futures đúng
  - pair tồn tại và có metadata đầy đủ
