# Bot Trade

Crypto Trading Bot using Freqtrade library.

## Current focus

Repo này hiện là nhánh execution/migration cho `SMC_FVG_PinBar` sau khi rời khỏi Jesse live path.

- strategy port:
  - `src/strategies/SMC_FVG_PinBar_Freqtrade.py`
- futures config:
  - `config/config.futures.json`
- docs:
  - `docs/README.md`

## Quick Start

```bash
# 1. Setup
uv sync

# 2. Create futures config
cp config/config.futures.json user_data/config.futures.local.json

# 3. Run dry-run bot
uv run freqtrade trade \
  --config user_data/config.futures.local.json \
  --strategy SMC_FVG_PinBar_Freqtrade \
  --strategy-path src/strategies
```

## SMC_FVG_PinBar

Chuẩn bị data và compare với Jesse:

```bash
uv run python scripts/prepare_smc_fvg_pinbar_data.py --scope btc-baseline
uv run python scripts/prepare_smc_fvg_pinbar_data.py --scope recent-selected
uv run python scripts/compare_smc_fvg_pinbar_with_jesse.py
```

Xem kết quả:

- `user_data/compare/smc_fvg_pinbar_freqtrade_vs_jesse.md`
- `docs/research/smc_fvg_pinbar_freqtrade_migration_validation.md`

Basket futures hiện tại:

- `BTC/USDT:USDT`
- `PLAY/USDT:USDT`
- `BIO/USDT:USDT`
- `SPACE/USDT:USDT`
- `PENDLE/USDT:USDT`
- `BR/USDT:USDT`
- `D/USDT:USDT`
- `YGG/USDT:USDT`
- `STG/USDT:USDT`

## Project Structure

```
bot-trade/
├── config/              # Configuration files
├── src/
│   └── strategies/      # Trading strategies
├── user_data/           # Runtime data (logs, results, market data)
└── tests/               # Tests
```
