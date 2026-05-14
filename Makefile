# trading-bot: freqtrade backtest, plot, trade (use config + strategy path)

PYTHON   := uv run python
FREQ     := $(PYTHON) -m freqtrade
CONFIG   := config/config.futures.json
SPATH    := src/strategies
STRATEGY ?= SMC_FVG_PinBar_Freqtrade
DAYS     ?= 60
TIMERANGE ?=

PAIR     ?= BTC/USDT:USDT

.PHONY: install sync seed-data data list-data backtest backtest-ma backtest-pinbar plot plot-ma plot-pinbar plot-df plot-df-pinbar trade list-strategies clean

install:
	uv sync

sync: install

# Download OHLCV via the repo seed script (DAYS=60, override: make data DAYS=90)
data: install
	$(PYTHON) scripts/seed_freqtrade_data.py --preset smc-basket --days $(DAYS)

seed-data: install
	$(PYTHON) scripts/seed_freqtrade_data.py --preset smc-basket --days $(DAYS)

# List downloaded data
list-data:
	$(FREQ) list-data --config $(CONFIG)

# Backtest current strategy
backtest: install
	$(FREQ) backtesting --config $(CONFIG) --strategy $(STRATEGY) --strategy-path $(SPATH) $(if $(TIMERANGE),--timerange $(TIMERANGE),)

backtest-ma:
	$(MAKE) backtest STRATEGY=MA50_200_Strategy

backtest-pinbar:
	$(MAKE) backtest STRATEGY=SMC_FVG_PinBar_Freqtrade

# Plot profit from latest backtest result; strategy must match the backtest
plot: install
	$(FREQ) plot-profit --config $(CONFIG) --strategy $(STRATEGY) --strategy-path $(SPATH)

plot-ma:
	$(MAKE) plot STRATEGY=MA50_200_Strategy

plot-pinbar:
	$(MAKE) plot STRATEGY=SMC_FVG_PinBar_Freqtrade

# Candle chart with entry/exit markers (from latest backtest)
plot-df: install
	$(FREQ) plot-dataframe --config $(CONFIG) --strategy $(STRATEGY) --strategy-path $(SPATH) --pairs $(PAIR)

plot-df-pinbar:
	$(MAKE) plot-df STRATEGY=SMC_FVG_PinBar_Freqtrade

# Run bot (dry-run by default in config)
trade: install
	$(FREQ) trade --config $(CONFIG) --strategy $(STRATEGY) --strategy-path $(SPATH)

list-strategies:
	$(FREQ) list-strategies --strategy-path $(SPATH)

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
