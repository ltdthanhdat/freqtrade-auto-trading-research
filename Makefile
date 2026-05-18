# trading-bot: freqtrade backtest, plot, trade (use config + strategy path)

PYTHON   := uv run python
FREQ     := $(PYTHON) -m freqtrade
CONFIG   ?= config/config.futures.json
SPATH    := src/strategies
STRATEGY ?= SMC_FVG_Context30m_Freqtrade
DAYS     ?= 60
TIMERANGE ?=
DATASET  ?= recent_selected

PAIR     ?= BTC/USDT:USDT
SNAPSHOT_DATADIR := user_data/data/snapshots/$(DATASET)

.PHONY: help install seed seed-range seed-snapshot list-data list-snapshot backtest backtest-snapshot plot plot-df dry-run demo live compose-demo compose-live list-strategies clean clean-backtest-results

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z0-9_-]+:.*## / {printf "%-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install dependencies with uv
	uv sync

seed: install ## Seed active data with DAYS=<n>
	$(PYTHON) scripts/seed_freqtrade_data.py --config $(CONFIG) --preset smc-basket --days $(DAYS)

seed-range: install ## Seed active data with TIMERANGE=<start-end>
	$(PYTHON) scripts/seed_freqtrade_data.py --config $(CONFIG) --preset smc-basket --timerange $(TIMERANGE)

seed-snapshot: install ## Seed snapshot data with DATASET=<name> DAYS=<n>
	$(PYTHON) scripts/seed_freqtrade_data.py --config $(CONFIG) --dataset snapshots/$(DATASET) --preset smc-basket --days $(DAYS)

# List downloaded data
list-data: ## List downloaded market data
	$(FREQ) list-data --config $(CONFIG)

list-snapshot: ## List snapshot data with DATASET=<name>
	$(FREQ) list-data --config $(CONFIG) --datadir $(SNAPSHOT_DATADIR)

# Backtest current strategy
backtest: install ## Run backtest with optional TIMERANGE=<start-end>
	$(FREQ) backtesting --config $(CONFIG) --strategy $(STRATEGY) --strategy-path $(SPATH) $(if $(TIMERANGE),--timerange $(TIMERANGE),)

backtest-snapshot: install ## Run backtest on snapshot data with DATASET=<name> TIMERANGE=<start-end>
	$(FREQ) backtesting --config $(CONFIG) --datadir $(SNAPSHOT_DATADIR) --strategy $(STRATEGY) --strategy-path $(SPATH) $(if $(TIMERANGE),--timerange $(TIMERANGE),)

# Plot profit from latest backtest result; strategy must match the backtest
plot: install ## Plot profit for the latest backtest
	$(FREQ) plot-profit --config $(CONFIG) --strategy $(STRATEGY) --strategy-path $(SPATH)

# Candle chart with entry/exit markers (from latest backtest)
plot-df: install ## Plot candles and entries for PAIR=<pair>
	$(FREQ) plot-dataframe --config $(CONFIG) --strategy $(STRATEGY) --strategy-path $(SPATH) --pairs $(PAIR)

dry-run: install ## Run dry-run with base futures config
	$(FREQ) trade --config $(CONFIG) --strategy $(STRATEGY) --strategy-path $(SPATH)

demo: install ## Run Binance demo trading with env override config
	$(FREQ) trade --config $(CONFIG) --config config/config.binance.demo.json --strategy $(STRATEGY) --strategy-path $(SPATH)

live: install ## Run Binance live trading with env override config
	$(FREQ) trade --config $(CONFIG) --config config/config.binance.live.json --strategy $(STRATEGY) --strategy-path $(SPATH)

compose-demo: ## Run Binance demo service via Docker Compose
	docker compose up -d freqtrade-demo

compose-live: ## Run Binance live service via Docker Compose
	docker compose up -d freqtrade-live

list-strategies: ## List available strategies
	$(FREQ) list-strategies --strategy-path $(SPATH)

clean: ## Remove Python cache directories
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

clean-backtest-results: ## Remove generated backtest result artifacts
	rm -f user_data/backtest_results/*.zip user_data/backtest_results/*.meta.json user_data/backtest_results/.last_result.json
