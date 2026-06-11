# Bot Trade

Crypto trading bot built on Freqtrade.

## Current focus

- strategy: `src/strategies/SMC_FVG_Context30m_Freqtrade.py`
- config: `config/config.futures.json`
- research: `.research/smc_fvg_pinbar/README.md`

## Default strategy

`SMC_FVG_Context30m_Freqtrade` is a hybrid:

- execution timeframe: `30m`
- context timeframe: `1h`
- base logic: uses `1h` signal as primary context, maps it to the two corresponding `30m` candles for entry
- extra short edge: allows `30m displacement short` when `1h close < EMA20` and `1h EMA20 slope < 0`

In short: `1h` determines bias, `30m` executes earlier. This is the current default baseline.

## Research flow

```mermaid
flowchart TD
    A[Read current state] --> B[State 1 hypothesis]
    B --> C[Write experiment]
    C --> D{Validation}

    D --> E[Seed data]
    E --> F[Single-pair backtest]
    F --> G[Basket backtest]
    G --> H[Dry-run]

    H --> I[Log run]
    I --> J{Keep / Discard?}

    J -- keep --> K[Update state.md]
    K --> L[New objective?]
    L -- yes --> B
    L -- no --> M[Use snapshot for dry-run / live]

    J -- discard --> L

    style A fill:#1a1a2e,color:#e0e0e0
    style B fill:#16213e,color:#e0e0e0
    style C fill:#0f3460,color:#e0e0e0
    style D fill:#533483,color:#e0e0e0
    style J fill:#533483,color:#e0e0e0
    style K fill:#1a472a,color:#e0e0e0
    style M fill:#1a472a,color:#e0e0e0
```

## Trace model

```mermaid
flowchart LR
    H[Hypothesis] --> E[Experiment]
    E --> R[Run]
    R --> D[Decision]
    D --> S[State]

    style H fill:#16213e,color:#e0e0e0
    style E fill:#0f3460,color:#e0e0e0
    style R fill:#533483,color:#e0e0e0
    style D fill:#1a472a,color:#e0e0e0
    style S fill:#2d4a22,color:#e0e0e0
```

## Quick Start

```bash
uv sync
uv run python scripts/seed_freqtrade_data.py --preset smc-basket --days 90
set -a
source .env
set +a

make dry-run
```

Compose option:

```bash
docker compose up -d freqtrade-demo
docker compose up -d freqtrade-live
```

## Seed data

The seed script calls `freqtrade download-data` directly.
Active data is saved in the format declared in config:

- `datadir = user_data/data`
- `dataformat_ohlcv = feather`
- `trading_mode = futures`

Layout:

- dataset active: `user_data/data/binance/futures`
- dataset snapshot: `user_data/data/snapshots/<name>/futures`

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
- `make demo`
- `make live`

Examples:

```bash
uv run python scripts/seed_freqtrade_data.py --preset smc-basket --days 90
uv run python scripts/seed_freqtrade_data.py --pairs BTC/USDT:USDT ETH/USDT:USDT --days 30
uv run python scripts/seed_freqtrade_data.py --preset smc-basket --timerange 20250101-20250301
uv run python scripts/seed_freqtrade_data.py --preset smc-basket --dataset snapshots/recent_selected --days 30
```

Default futures basket:

- `PLAY/USDT:USDT`
- `BIO/USDT:USDT`
- `SPACE/USDT:USDT`
- `PENDLE/USDT:USDT`
- `BR/USDT:USDT`
- `YGG/USDT:USDT`
