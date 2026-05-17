# Bot Trade

Crypto trading bot dùng Freqtrade.

## Current focus

Repo này chạy độc lập trên Freqtrade.

- strategy:
  - `src/strategies/SMC_FVG_Confirmation_Freqtrade.py`
- futures config:
  - `config/config.futures.json`
- docs:
  - `docs/README.md`

## Quick Start

```bash
uv sync
uv run python scripts/seed_freqtrade_data.py --preset smc-basket --days 90
set -a
source .env
set +a

uv run python -m freqtrade trade \
  --config config/config.futures.json \
  --config config/config.binance.demo.json \
  --strategy SMC_FVG_Confirmation_Freqtrade \
  --strategy-path src/strategies
```

## Seed data

Script seed hiện tại gọi trực tiếp `freqtrade download-data`.
Data được lưu đúng format đã khai báo trong config:

- `datadir = user_data/data`
- `dataformat_ohlcv = feather`
- `trading_mode = futures`

Ví dụ:

```bash
uv run python scripts/seed_freqtrade_data.py --preset smc-basket --days 90
uv run python scripts/seed_freqtrade_data.py --pairs BTC/USDT:USDT ETH/USDT:USDT --days 30
uv run python scripts/seed_freqtrade_data.py --preset smc-basket --timerange 20250101-20250301
```

Basket futures mặc định:

- `BTC/USDT:USDT`
- `PLAY/USDT:USDT`
- `BIO/USDT:USDT`
- `SPACE/USDT:USDT`
- `PENDLE/USDT:USDT`
- `BR/USDT:USDT`
- `D/USDT:USDT`
- `YGG/USDT:USDT`
- `STG/USDT:USDT`
