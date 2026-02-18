# Claude Guide

Detailed guide for AI Agent when working with this project.

## Project Structure

```
bot-trade/
├── config/              # Configuration files
│   ├── config.json      # Main config (gitignored)
│   └── config.json.example
├── src/
│   └── strategies/      # Trading strategies
├── user_data/           # Runtime data only
│   ├── data/            # Market data (feather format)
│   ├── backtest_results/
│   ├── plot/
│   └── logs/
└── tests/
```

## Configuration

### Create config

```bash
# Copy from example
cp config/config.json.example config/config.json

# Or create new
uv run freqtrade new-config --config config/config.json
```

### Edit config

Open `config/config.json` and edit:
- **Exchange**: Choose exchange (binance, kraken, etc.)
- **API Keys**: Add key and secret (if trading live)
- **dry_run**: Set `true` to test without real money
- **pair_whitelist**: List of trading pairs

## How to Run

### Download data

**Important**: Need to download data before backtesting!

```bash
# Basic download (30 days)
uv run freqtrade download-data \
    --exchange binance \
    --pairs BTC/USDT ETH/USDT \
    --timeframes 5m 1h \
    --days 60 \
    --config config/config.json

# Download with specific timerange
uv run freqtrade download-data \
    --exchange binance \
    --pairs BTC/USDT \
    --timerange 20240101- \
    --config config/config.json

# View downloaded data
uv run freqtrade list-data --config config/config.json
```

**Storage location:**
- `user_data/data/<exchange>/<PAIR>-<TIMEFRAME>.feather`
- Default format: `feather` (Apache Arrow, fastest)

### Backtesting

```bash
# Backtest with timerange
uv run freqtrade backtesting \
    --config config/config.json \
    --strategy MA50_200_Strategy \
    --timerange 20240101-20241201

# Backtest with existing data
uv run freqtrade backtesting \
    --config config/config.json \
    --strategy MA50_200_Strategy
```

### Run bot

```bash
# Run bot (dry-run)
uv run freqtrade trade \
    --config config/config.json \
    --strategy MA50_200_Strategy

# Or activate environment
source .venv/bin/activate
freqtrade trade --config config/config.json --strategy MA50_200_Strategy
```

### Create new strategy

```bash
# Create from template
uv run freqtrade new-strategy \
    --strategy MyNewStrategy \
    --strategy-path src/strategies

# Strategy will be created at: src/strategies/MyNewStrategy.py
```

### Other commands

```bash
# List strategies
uv run freqtrade list-strategies --strategy-path src/strategies

# List exchanges
uv run freqtrade list-exchanges

# Hyperopt (optimize parameters)
uv run freqtrade hyperopt \
    --config config/config.json \
    --strategy MA50_200_Strategy \
    --hyperopt-loss SharpeHyperOptLoss \
    --epochs 100

# Plot results
uv run freqtrade plot-profit --config config/config.json --strategy MA50_200_Strategy
uv run freqtrade plot-dataframe \
    --config config/config.json \
    --strategy MA50_200_Strategy \
    --pairs BTC/USDT \
    --indicators1 rsi \
    --indicators2 macd macdsignal
```

## Strategy Development

### Create new strategy

1. Create file in `src/strategies/`:

```python
from freqtrade.strategy import IStrategy
import talib.abstract as ta

class MyStrategy(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "5m"
    stoploss = -0.10
    minimal_roi = {"0": 0.04}
    
    def populate_indicators(self, dataframe, metadata):
        dataframe["rsi"] = ta.RSI(dataframe)
        return dataframe
    
    def populate_entry_trend(self, dataframe, metadata):
        dataframe.loc[
            (dataframe["rsi"] < 30),
            "enter_long",
        ] = 1
        return dataframe
    
    def populate_exit_trend(self, dataframe, metadata):
        dataframe.loc[
            (dataframe["rsi"] > 70),
            "exit_long",
        ] = 1
        return dataframe
```

2. Run bot:

```bash
uv run freqtrade trade --config config/config.json --strategy MyStrategy
```

## Testing

When testing, ensure:
- Config file exists: `config/config.json`
- Strategy exists: `src/strategies/MA50_200_Strategy.py`
- Data downloaded (if backtesting): `user_data/data/<exchange>/`

## Important Notes

⚠️ **WARNING**: 
- Always start with `dry_run: true` to test without real money
- Backtest strategy before live trading
- Trading has risks, no profit guarantee
