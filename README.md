# Bot Trade

Crypto Trading Bot using Freqtrade library.

## Quick Start

```bash
# 1. Setup
uv sync

# 2. Create config
cp config/config.json.example config/config.json

# 3. Run bot
uv run freqtrade trade --config config/config.json --strategy MA50_200_Strategy --strategy-path src/strategies
```

## Project Structure

```
bot-trade/
├── config/              # Configuration files
├── src/
│   └── strategies/      # Trading strategies
├── user_data/           # Runtime data (logs, results, market data)
└── tests/               # Tests
```
