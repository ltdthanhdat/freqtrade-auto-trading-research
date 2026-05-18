# Bot Trade

Crypto trading bot dùng Freqtrade.

## Current focus

Repo này chạy độc lập trên Freqtrade.

- strategy:
  - `src/strategies/SMC_FVG_Context30m_Freqtrade.py`
- futures config:
  - `config/config.futures.json`
- docs:
  - `docs/smc_fvg_pinbar/README.md`

## Default strategy

`SMC_FVG_Context30m_Freqtrade` là bản hybrid:

- execution timeframe:
  - `30m`
- context timeframe:
  - `1h`
- base logic:
  - giữ signal `1h` làm context chính
  - map signal `1h` xuống hai nến `30m` tương ứng để vào lệnh
- extra short edge:
  - cho phép thêm `30m displacement short`
  - chỉ khi `1h close < EMA20`
  - và `1h EMA20 slope < 0`

Nói ngắn:

- `1h` quyết định bias chính
- `30m` dùng để execution sớm hơn
- đây là baseline mặc định hiện tại của repo

## Quick Start

```bash
uv sync
uv run python scripts/seed_freqtrade_data.py --preset smc-basket --days 90
set -a
source .env
set +a

make dry-run
```

## Seed data

Script seed hiện tại gọi trực tiếp `freqtrade download-data`.
Data active mặc định được lưu đúng format đã khai báo trong config:

- `datadir = user_data/data`
- `dataformat_ohlcv = feather`
- `trading_mode = futures`

Layout:

- dataset active:
  - `user_data/data/binance/futures`
- dataset snapshot:
  - `user_data/data/snapshots/<name>/futures`

Make targets:

- `make seed DAYS=90`
- `make seed-range TIMERANGE=20260218-20260518`
- `make seed-snapshot DATASET=recent_selected DAYS=30`
- `make list-data`
- `make list-snapshot DATASET=recent_selected`
- `make backtest TIMERANGE=20260218-20260518`
- `make backtest-snapshot DATASET=recent_selected TIMERANGE=20260218-20260518`
- `make plot`
- `make plot-df PAIR=BTC/USDT:USDT`
- `make dry-run`
- `make live`

Ví dụ:

```bash
uv run python scripts/seed_freqtrade_data.py --preset smc-basket --days 90
uv run python scripts/seed_freqtrade_data.py --pairs BTC/USDT:USDT ETH/USDT:USDT --days 30
uv run python scripts/seed_freqtrade_data.py --preset smc-basket --timerange 20250101-20250301
uv run python scripts/seed_freqtrade_data.py --preset smc-basket --dataset snapshots/recent_selected --days 30
```

Basket futures mặc định:

- `PLAY/USDT:USDT`
- `BIO/USDT:USDT`
- `SPACE/USDT:USDT`
- `PENDLE/USDT:USDT`
- `BR/USDT:USDT`
- `YGG/USDT:USDT`
