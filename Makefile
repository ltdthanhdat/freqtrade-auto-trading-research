# trading-bot: freqtrade backtest, plot, trade (use config + strategy path)

PYTHON   := uv run python
FREQ     := $(PYTHON) -m freqtrade
CONFIG   ?= config/config.futures.json
LOCAL_CONFIG ?= user_data/config.futures.local.json
SPATH    := src/strategies
STRATEGY ?= SMC_FVG_PinBar_Freqtrade
DAYS     ?= 60
TIMERANGE ?=

PAIR     ?= BTC/USDT:USDT

.PHONY: help install sync config-local seed seed-data data list-data backtest backtest-pinbar plot plot-pinbar plot-df plot-df-pinbar trade dry-run live list-strategies clean

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z0-9_-]+:.*## / {printf "%-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install dependencies with uv
	uv sync

sync: install

config-local: ## Create local config if missing
	mkdir -p user_data
	test -f $(LOCAL_CONFIG) || cp $(CONFIG) $(LOCAL_CONFIG)

# Download OHLCV via the repo seed script (DAYS=60, override: make data DAYS=90)
data: seed ## Seed data with the default basket

seed: install ## Seed data with DAYS=<n>
	$(PYTHON) scripts/seed_freqtrade_data.py --config $(CONFIG) --preset smc-basket --days $(DAYS)

seed-data: seed ## Alias of seed

# List downloaded data
list-data: ## List downloaded market data
	$(FREQ) list-data --config $(CONFIG)

# Backtest current strategy
backtest: install ## Run backtest with optional TIMERANGE=<start-end>
	$(FREQ) backtesting --config $(CONFIG) --strategy $(STRATEGY) --strategy-path $(SPATH) $(if $(TIMERANGE),--timerange $(TIMERANGE),)

backtest-pinbar: ## Backtest SMC_FVG_PinBar_Freqtrade
	$(MAKE) backtest STRATEGY=SMC_FVG_PinBar_Freqtrade

# Plot profit from latest backtest result; strategy must match the backtest
plot: install ## Plot profit for the latest backtest
	$(FREQ) plot-profit --config $(CONFIG) --strategy $(STRATEGY) --strategy-path $(SPATH)

plot-pinbar: ## Plot profit for SMC_FVG_PinBar_Freqtrade
	$(MAKE) plot STRATEGY=SMC_FVG_PinBar_Freqtrade

# Candle chart with entry/exit markers (from latest backtest)
plot-df: install ## Plot candles and entries for PAIR=<pair>
	$(FREQ) plot-dataframe --config $(CONFIG) --strategy $(STRATEGY) --strategy-path $(SPATH) --pairs $(PAIR)

plot-df-pinbar: ## Plot candles for SMC_FVG_PinBar_Freqtrade
	$(MAKE) plot-df STRATEGY=SMC_FVG_PinBar_Freqtrade

# Run bot (dry-run by default in config)
trade: install ## Run the bot with CONFIG
	$(FREQ) trade --config $(CONFIG) --strategy $(STRATEGY) --strategy-path $(SPATH)

dry-run: install config-local ## Run dry-run with LOCAL_CONFIG
	$(FREQ) trade --config $(LOCAL_CONFIG) --strategy $(STRATEGY) --strategy-path $(SPATH)

live: install config-local ## Run live or dry-run depending on LOCAL_CONFIG
	$(FREQ) trade --config $(LOCAL_CONFIG) --strategy $(STRATEGY) --strategy-path $(SPATH)

list-strategies: ## List available strategies
	$(FREQ) list-strategies --strategy-path $(SPATH)

clean: ## Remove Python cache directories
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
