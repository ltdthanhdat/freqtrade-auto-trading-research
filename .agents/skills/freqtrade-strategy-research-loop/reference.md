# Freqtrade Reference — Scripts, Dry-run, Live, Blockers

Seed Freqtrade data:

```bash
uv run python scripts/seed_freqtrade_data.py --preset smc-basket --days 90
```

List strategies:

```bash
uv run freqtrade list-strategies --strategy-path src/strategies
```

Backtest:

```bash
uv run freqtrade backtesting \
  --config config/config.futures.json \
  --strategy SMC_FVG_Context30m_Freqtrade \
  --strategy-path src/strategies
```

## Dry-run and live

Config layout: `config/config.futures.json` (base) + `config/config.binance.demo.json` or `config/config.binance.live.json`.

Fill `.env`:

```bash
FREQTRADE__EXCHANGE__KEY=...
FREQTRADE__EXCHANGE__SECRET=...
FREQTRADE_TELEGRAM_ENABLED=false
FREQTRADE_TELEGRAM_TOKEN=
FREQTRADE_TELEGRAM_CHAT_ID=
```

Dry-run:

```bash
set -a; source .env; set +a
uv run python -m freqtrade trade \
  --config config/config.futures.json \
  --config config/config.binance.demo.json \
  --strategy SMC_FVG_Context30m_Freqtrade \
  --strategy-path src/strategies
```

Live (switch `.env` keys to live credentials first):

```bash
set -a; source .env; set +a
uv run python -m freqtrade trade \
  --config config/config.futures.json \
  --config config/config.binance.live.json \
  --strategy SMC_FVG_Context30m_Freqtrade \
  --strategy-path src/strategies
```

Docker Compose:

```bash
docker compose up -d freqtrade-demo
docker compose up -d freqtrade-live
docker compose stop freqtrade-demo
docker compose stop freqtrade-live
```

Compose DB and logs: `user_data/tradesv3.demo.sqlite` / `user_data/tradesv3.live.sqlite`, `user_data/logs/freqtrade-demo.log` / `user_data/logs/freqtrade-live.log`.

Binance demo futures: `enableDemoTrading` alone is not enough with Freqtrade + CCXT 4.5.38. Must explicitly override `exchange.ccxt_config.urls.api.fapi*` and `exchange.ccxt_async_config.urls.api.fapi*` to `demo-fapi.binance.com`.

## Blockers

- Futures pairs: use `BTC/USDT:USDT`, not `BTC-USDT`.
- Timeframe seed: always include `30m` and `1h`.
- If metadata download fails for a pair: remove it from the preset. Do not use external data as a workaround.
