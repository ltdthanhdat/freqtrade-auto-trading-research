# trading-bot: freqtrade backtest, plot, trade (use config + strategy path)

PYTHON   := uv run python
FREQ     := $(PYTHON) -m freqtrade
CONFIG   ?= config/config.futures.json
SPATH    := src/strategies
STRATEGY ?= SMC_FVG_Context30m_Freqtrade
DAYS     ?= 60
TIMERANGE ?=
TIMEFRAMES ?= 30m,1h,1m
DATASET  ?= recent_selected
VALIDATION_START ?= 2025-10-19
VALIDATION_END ?= 2026-05-17
APPROVED_IDENTITY ?= config/approved-baseline-identity.json
RESEARCH_RUNS_DIR ?= user_data/research-artifacts/validation
RESEARCH_DB ?= user_data/research.sqlite
VALIDATION_STATE_DB ?= user_data/validation-state.sqlite
VALIDATION_MANIFEST ?=
VALIDATION_POLICY ?= config/validation.baseline.json
RESEARCH_DATASET ?= accepted_6pair_2026q3_full
RESEARCH_TIMERANGE ?= 20260124-20260911
MAX_CYCLES ?= 1
RESEARCH_TIMEOUT ?= 300
RESEARCH_MODEL ?= openai-codex/gpt-5.6-luna
BASELINE ?= user_data/backtest_results/baseline.zip
DB ?= user_data/tradesv3.demo.sqlite

PAIR     ?= BTC/USDT:USDT
SNAPSHOT_DATADIR := user_data/data/snapshots/$(DATASET)

.PHONY: help install seed seed-range seed-snapshot research-data list-data list-snapshot backtest backtest-snapshot validate-snapshot validate-pass monitor-decay plot plot-df dry-run demo live compose-demo compose-live compose-research list-strategies research-cycle research-loop research-dashboard clean clean-backtest-results

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z0-9_-]+:.*## / {printf "%-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install dependencies with uv
	uv sync

seed: install ## Seed active data with DAYS=<n>
	$(PYTHON) -m scripts.seed_freqtrade_data --config $(CONFIG) --preset smc-basket --days $(DAYS)

seed-range: install ## Seed active data with TIMERANGE=<start-end>
	$(PYTHON) -m scripts.seed_freqtrade_data --config $(CONFIG) --preset smc-basket --timerange $(TIMERANGE)

seed-snapshot: install ## Seed snapshot data with DATASET=<name> DAYS=<n>
	$(PYTHON) -m scripts.seed_freqtrade_data --config $(CONFIG) --dataset snapshots/$(DATASET) --preset smc-basket --days $(DAYS)

research-data: ## Seed and verify the snapshot used by research-cycle
	$(PYTHON) -m scripts.prepare_research_data --config $(CONFIG) --policy $(VALIDATION_POLICY) --dataset $(RESEARCH_DATASET) --timerange $(RESEARCH_TIMERANGE)

# List downloaded data
list-data: ## List downloaded market data
	$(FREQ) list-data --config $(CONFIG)

list-snapshot: ## List snapshot data with DATASET=<name>
	$(FREQ) list-data --config $(CONFIG) --datadir $(SNAPSHOT_DATADIR)

# Backtest current strategy
backtest: install ## Run backtest with optional TIMERANGE=<start-end>
	$(FREQ) backtesting --config $(CONFIG) --strategy $(STRATEGY) --strategy-path $(SPATH) --timeframe-detail 1m $(if $(TIMERANGE),--timerange $(TIMERANGE),)

backtest-snapshot: install ## Run backtest on snapshot data with DATASET=<name> TIMERANGE=<start-end>
	$(FREQ) backtesting --config $(CONFIG) --datadir $(SNAPSHOT_DATADIR) --strategy $(STRATEGY) --strategy-path $(SPATH) --timeframe-detail 1m $(if $(TIMERANGE),--timerange $(TIMERANGE),)

validate-snapshot: install ## Validate snapshot gate with DATASET=<name>
	$(PYTHON) -m scripts.validate_baseline --config $(CONFIG) --datadir $(SNAPSHOT_DATADIR) --policy $(VALIDATION_POLICY) --strategy $(STRATEGY) --strategy-path $(SPATH) --strategy-file $(SPATH)/$(STRATEGY).py --start $(VALIDATION_START) --end $(VALIDATION_END) --runs-dir $(RESEARCH_RUNS_DIR) --approved-identity $(APPROVED_IDENTITY) --wfo

validate-pass: ## Require VALIDATION_MANIFEST with verdict PASS
	@test -n "$(VALIDATION_MANIFEST)" || { echo "VALIDATION_MANIFEST is required" >&2; exit 1; }
	@$(PYTHON) -m scripts.validate_manifest --manifest "$(VALIDATION_MANIFEST)" --config "$(CONFIG)" --policy "$(VALIDATION_POLICY)" --strategy "$(STRATEGY)" --strategy-path "$(SPATH)" --research-db "$(RESEARCH_DB)" --state-db "$(VALIDATION_STATE_DB)"

research-cycle: research-data ## Start or resume one bounded Pi research cycle
	RESEARCH_DATASET=$(RESEARCH_DATASET) RESEARCH_TIMERANGE=$(RESEARCH_TIMERANGE) pi --approve --model openai-codex/gpt-5.6-luna --thinking max --no-builtin-tools

research-loop: research-data ## Run a bounded supervisor that resumes interrupted research cycles
	RESEARCH_MODEL=$(RESEARCH_MODEL) $(PYTHON) -m scripts.research_loop --db "$(RESEARCH_DB)" --dataset "$(RESEARCH_DATASET)" --timerange "$(RESEARCH_TIMERANGE)" --max-cycles "$(MAX_CYCLES)" --cycle-timeout "$(RESEARCH_TIMEOUT)"

research-dashboard: ## Open the local research dashboard server
	$(PYTHON) -m research_runtime.dashboard --db user_data/research.sqlite --artifacts user_data/research-artifacts --port 7400

monitor-decay: install ## Monitor demo/live decay with BASELINE=<zip> DB=<sqlite>
	$(PYTHON) -m scripts.monitor_decay --baseline $(BASELINE) --db $(DB) --state-db "$(VALIDATION_STATE_DB)"

# Plot profit from latest backtest result; strategy must match the backtest
plot: install ## Plot profit for the latest backtest
	$(FREQ) plot-profit --config $(CONFIG) --strategy $(STRATEGY) --strategy-path $(SPATH)

# Candle chart with entry/exit markers (from latest backtest)
plot-df: install ## Plot candles and entries for PAIR=<pair>
	$(FREQ) plot-dataframe --config $(CONFIG) --strategy $(STRATEGY) --strategy-path $(SPATH) --pairs $(PAIR)

dry-run: validate-pass install ## Run dry-run only with a PASS validation manifest
	$(FREQ) trade --config $(CONFIG) --strategy $(STRATEGY) --strategy-path $(SPATH)

demo: install ## Run Binance demo trading with env override config
	$(FREQ) trade --config $(CONFIG) --config config/config.binance.demo.json --strategy $(STRATEGY) --strategy-path $(SPATH)

live: install ## Run Binance live trading with env override config
	$(FREQ) trade --config $(CONFIG) --config config/config.binance.live.json --strategy $(STRATEGY) --strategy-path $(SPATH)

compose-demo: ## Run Binance demo service via Docker Compose
	docker compose up -d freqtrade-demo

compose-live: ## Run Binance live service via Docker Compose
	docker compose up -d freqtrade-live

compose-research: ## Run one bounded research cycle via Docker Compose
	RESEARCH_ROOT="$(CURDIR)" docker compose --profile research run --rm research

list-strategies: ## List available strategies
	$(FREQ) list-strategies --strategy-path $(SPATH)

clean: ## Remove Python cache directories
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

clean-backtest-results: ## Remove generated backtest result artifacts
	rm -f user_data/backtest_results/*.zip user_data/backtest_results/*.meta.json user_data/backtest_results/.last_result.json
