# Per-Strategy Risk and Exit Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SMC FVG futures sizing and protective-exit callbacks fail closed while preserving this strategy's own entry, 1R target, no-signal-exit, and regime semantics; prevent stale FVG signals and make the risk/exit contract testable without changing unrelated strategies.

**Architecture:** Put only generic, pure risk arithmetic in a small strategy module. Keep SMC-specific structural-stop extraction, trade-state persistence, 1R target calculation, and emergency behavior in `SMC_FVG_Confirmation_Freqtrade`, which `SMC_FVG_Context30m_Freqtrade` inherits. Do not introduce a universal stop, ROI, trailing, time, or regime-exit layer for other strategies. Use the exact signal tag as the only post-entry stop source; a missing or invalid plan rejects the entry or activates the SMC-configured emergency fallback.

**Tech Stack:** Python 3.11, Freqtrade strategy callbacks, pandas, NumPy-compatible scalar validation, JSON config, pytest.

**Spec:** `docs/superpowers/specs/2026-09-13-per-strategy-risk-exit-design.md`

## Global Constraints

- Implement runtime-integrity hardening first; do not begin this plan until the research-runtime plan's focused tests pass.
- Only `src/strategies/SMC_FVG_Confirmation_Freqtrade.py`, its context subclass, `config/config.futures.json`, the generic risk module, and directly related tests/config validation may change.
- Preserve every strategy's own entry, stop, TP/ROI, time, trailing, and regime-exit semantics. Shared arithmetic must not decide exits for unrelated strategies.
- Do not tune alpha, run hyperopt, expand pairs, start dry-run/live, or promote a candidate.
- Include fee, slippage, leverage, and available-equity effects in sizing; never silently use unsafe defaults when required risk inputs are absent.
- A structural stop must be on the correct side of the current/entry price and finite. A missing stop, invalid direction, invalid leverage, non-finite cost, or failed trade-state persistence rejects the entry or uses the configured SMC emergency fallback; valid structural-stop behavior retains `stoploss = -0.99`.
- Stop/ROI callbacks must not read the latest analyzed candle as a substitute for the candle that produced the entry tag.
- `1m` remains the detail timeframe for future validation; no backtest command is run by this plan.

---

### Task 1: Define the pure risk-sizing contract with failing tests first

**Files:**
- Create: `src/strategies/risk.py`
- Create: `tests/test_strategy_risk.py`
- Modify: `tests/test_validation_core.py` only if a shared finite-number helper is reused

**Interfaces:**
- Produces `RiskInputs` with `side`, `entry_rate`, `stop_rate`, `leverage`, `max_leverage`, `available_equity`, `min_stake`, `max_stake`, `risk_fraction`, `collateral_cap_fraction`, `entry_fee_rate`, `exit_fee_rate`, `entry_slippage_rate`, `stop_slippage_rate`, and `emergency_loss_ratio`.
- Produces `RiskDecision` with `accepted`, `rejection_code`, `collateral_stake`, `notional`, `quantity`, `price_distance_ratio`, `collateral_loss_ratio`, `target_risk_budget`, and `capital_cap_binding`.
- Produces `calculate_risk(inputs: RiskInputs) -> RiskDecision`.

- [ ] **Step 1: Write failing arithmetic and rejection tests.**

  Assert conservative execution prices are used:

  ```text
  long entry_worst = P * (1 + entry_slippage_rate)
  long stop_worst  = S * (1 - stop_slippage_rate)
  short entry_worst = P * (1 - entry_slippage_rate)
  short stop_worst  = S * (1 + stop_slippage_rate)
  distance = adverse_side(stop_worst - entry_worst) / entry_worst
  loss_ratio = leverage * (distance + entry_fee_rate + (stop_worst / entry_worst) * exit_fee_rate)
  E = min(available_equity, max_stake)
  risk_budget = E * risk_fraction
  risk_stake = risk_budget / loss_ratio
  capital_cap = E * collateral_cap_fraction
  candidate = min(risk_stake, capital_cap, E, max_stake)
  ```

  Assert a valid result is reduced when fees/slippage are nonzero, is capped by both risk and capital limits, and returns zero when the computed stake is below `min_stake` rather than violating the risk budget. Assert `loss_ratio >= emergency_loss_ratio` rejects. Parameterize rejection for long stop above/equal entry, short stop below/equal entry, zero/negative leverage, leverage above `max_leverage`, zero/negative rates, negative ratios, missing/non-finite values, `min_stake > available_equity`, and non-`long`/`short` sides.

- [ ] **Step 2: Run the focused tests and verify RED.**

  ```bash
  uv run pytest tests/test_strategy_risk.py -q
  ```

  Expected: import or collection failure because `src.strategies.risk` does not yet exist.

- [ ] **Step 3: Implement only the pure calculator.**

  Use `math.isfinite` on every numeric input, preserve the side-specific directional check, calculate quote loss on leveraged margin including all four cost components, clamp only after validating, and return a reason code for every rejection. Do not import Freqtrade, wallets, pandas, or strategy classes into this module.

- [ ] **Step 4: Run the focused tests and verify GREEN.**

  ```bash
  uv run pytest tests/test_strategy_risk.py -q
  ```

- [ ] **Step 5: Commit the pure risk contract.**

  ```bash
  git add src/strategies/risk.py tests/test_strategy_risk.py
  git commit -m "feat: add fee-aware fail-closed risk sizing"
  ```

### Task 2: Add explicit SMC risk/cost configuration and validate it

**Files:**
- Modify: `config/config.futures.json`
- Modify: `src/strategies/SMC_FVG_Confirmation_Freqtrade.py`
- Modify: `tests/test_strategy_risk.py`
- Modify: `tests/test_seed_freqtrade_data.py` if config validation is shared there

**Interfaces:**
- Adds numeric keys `smc_entry_fee_rate`, `smc_exit_fee_rate`, `smc_entry_slippage_rate`, `smc_stop_slippage_rate`, and `smc_missing_stoploss_roi` to the futures config.
- Keeps `smc_risk_per_trade`, `smc_capital_cap`, and `smc_leverage` as the SMC namespace; the missing-state value is exactly `-0.10`.
- Preserves `stoploss = -0.99` for ordinary valid structural-stop behavior. The SMC-only missing-state path uses `abs(smc_missing_stoploss_roi)` as the finite leveraged emergency custom-stop value and has no invented generic profit target.
- Produces `_smc_risk_inputs(...)` and `_emergency_stoploss(...)` private strategy methods.

- [ ] **Step 1: Write failing configuration and adapter tests.**

  Assert the config parses as JSON, contains all eight `smc_*` risk keys, has `smc_missing_stoploss_roi == -0.10`, uses finite non-negative fee/slippage rates, and does not expose generic `risk_per_trade`/`capital_cap` keys. Instantiate the strategy with the config and a fake wallet exposing `get_available_stake_amount`; assert `_smc_risk_inputs` uses available equity, not total historical stake.

  Assert missing cost keys, non-finite values, or an invalid configured leverage cause the adapter to reject sizing instead of falling back to `proposed_stake`. Assert the missing-state emergency custom stop is `abs(smc_missing_stoploss_roi)` and is finite and leveraged according to the installed Freqtrade callback semantics.

- [ ] **Step 2: Run focused tests and verify RED.**

  ```bash
  uv run pytest tests/test_strategy_risk.py -q
  ```

- [ ] **Step 3: Implement namespaced configuration and adapter.**

  Add the four cost keys with explicit values matching the validation policy. Read all risk values through `self.config.get("smc_...")`; do not reuse the research fixture's generic names. Implement the emergency conversion with `stoploss_from_absolute` using `current_rate * (1 - ratio)` for long and `current_rate * (1 + ratio)` for short.

- [ ] **Step 4: Run focused tests and verify GREEN.**

  ```bash
  uv run pytest tests/test_strategy_risk.py -q
  ```

- [ ] **Step 5: Commit only the SMC risk configuration/adapter.**

  ```bash
  git add config/config.futures.json src/strategies/SMC_FVG_Confirmation_Freqtrade.py tests/test_strategy_risk.py
  git commit -m "fix: configure SMC risk costs explicitly"
  ```

### Task 3: Test and implement tag-bound structural-stop sizing

**Files:**
- Modify: `src/strategies/SMC_FVG_Confirmation_Freqtrade.py`
- Modify: `tests/test_strategy_risk.py`
- Create or modify: `tests/test_smc_fvg_callbacks.py`

**Interfaces:**
- Produces `_structural_stop_from_entry_tag(entry_tag: str | None, side: str) -> float | None`.
- `custom_stake_amount(...)` uses `entry_tag` first and rejects when it is absent, malformed, stale, non-finite, or directionally invalid.
- `custom_stake_amount(...)` returns the pure calculator's accepted stake, bounded by Freqtrade `min_stake`/`max_stake`.

- [ ] **Step 1: Write failing callback tests.**

  Use fake `dp`, wallet, and strategy config. Assert a long tag such as `pin_bar|95.0` at rate `100.0` and a short tag such as `displacement|105.0` produce side-correct risk inputs and a fee-aware stake. Assert the latest analyzed candle contains a different stop but cannot override the exact tag.

  Assert absent/malformed tags, `NaN`/infinite stops, long stop above entry, short stop below entry, unavailable data provider, zero equity, and invalid leverage all return `0`. Assert a valid calculated stake is bounded by `max_stake` and returns `0` when below `min_stake`.

- [ ] **Step 2: Run focused tests and verify RED.**

  ```bash
  uv run pytest tests/test_smc_fvg_callbacks.py tests/test_strategy_risk.py -q
  ```

- [ ] **Step 3: Implement tag-first SMC sizing.**

  Remove the latest-candle stop lookup from `custom_stake_amount`. Parse only the supplied entry tag, construct `RiskInputs` using `wallets.get_available_stake_amount()`, configured leverage, all configured costs, and current rate, then return the decision stake. Keep the method fail closed for any adapter error or invalid input; do not return `min(proposed_stake, max_stake)`.

- [ ] **Step 4: Run focused tests and verify GREEN.**

  ```bash
  uv run pytest tests/test_smc_fvg_callbacks.py tests/test_strategy_risk.py -q
  ```

- [ ] **Step 5: Commit tag-bound sizing.**

  ```bash
  git add src/strategies/SMC_FVG_Confirmation_Freqtrade.py tests/test_smc_fvg_callbacks.py tests/test_strategy_risk.py
  git commit -m "fix: size SMC entries from immutable signal stops"
  ```

### Task 4: Make first-fill state persistence and emergency stop behavior fail closed

**Files:**
- Modify: `src/strategies/SMC_FVG_Confirmation_Freqtrade.py`
- Modify: `tests/test_smc_fvg_callbacks.py`

**Interfaces:**
- `order_filled(...)` persists one SMC exit plan only on the first successful entry order.
- The persisted keys remain SMC-specific: `smc_signal_kind`, `smc_stop_rate`, `smc_target_roi`; add `smc_risk_state` and `smc_plan_version`.
- `custom_stoploss(...)` returns the persisted structural stop, tag stop, or bounded emergency stop; it never returns `None` for a live trade with no valid stop.
- `custom_roi(...)` preserves SMC's gross 1R target (`distance_ratio * leverage`) and returns `None` only when no live trade/entry plan exists before entry, never inventing an exit target from a latest candle.

- [ ] **Step 1: Write failing fill/stop/ROI tests.**

  Create fake `Trade`/`Order` objects for long and short first fills, add-entry fills, wrong-side fills, and duplicate first-fill callbacks. Assert only the first correct entry stores state, the stop is parsed from `trade.enter_tag`, and the target remains one gross leveraged R.

  Assert a malformed/missing tag does not read the latest dataframe candle. Assert `custom_stoploss` returns a correct structural stop for long and short, the configured `abs(smc_missing_stoploss_roi)` emergency value when state and tag are invalid, and an emergency value when `set_custom_data` raises. Assert `custom_roi` returns the persisted target, tag-derived target, and no invented target when the stop/plan is missing; it must not touch analyzed data.

- [ ] **Step 2: Run focused tests and verify RED.**

  ```bash
  uv run pytest tests/test_smc_fvg_callbacks.py -q
  ```

- [ ] **Step 3: Implement atomic-looking plan persistence using existing Freqtrade custom data.**

  Keep the existing order-side and `nr_of_successful_entries == 1` guard. Parse the exact tag, validate it against the trade side/open rate, calculate the existing gross 1R ROI, and write all state fields. If any write fails, attempt to mark `smc_risk_state="EMERGENCY"` and let `custom_stoploss` use the bounded emergency stop. Never query `dp`/latest candles to repair missing state.

  In `custom_stoploss`, validate persisted/tag stop direction against `current_rate`; otherwise call `_emergency_stoploss`, which returns the finite SMC-configured leveraged fallback. In `custom_roi`, use persisted target or a valid tag stop only and do not invent a profit target in degraded state. Preserve `stoploss = -0.99`, `minimal_roi`, `use_custom_roi`, `use_custom_stoploss`, `use_exit_signal=False`, and no explicit time/trailing/regime exit behavior.

- [ ] **Step 4: Run focused tests and verify GREEN.**

  ```bash
  uv run pytest tests/test_smc_fvg_callbacks.py -q
  ```

- [ ] **Step 5: Commit fail-closed callback state.**

  ```bash
  git add src/strategies/SMC_FVG_Confirmation_Freqtrade.py tests/test_smc_fvg_callbacks.py
  git commit -m "fix: fail closed when SMC exit state is missing"
  ```

### Task 5: Add finite FVG lifetime and sufficient startup history

**Files:**
- Modify: `src/strategies/SMC_FVG_Confirmation_Freqtrade.py`
- Modify: `src/strategies/SMC_FVG_Context30m_Freqtrade.py`
- Create or modify: `tests/test_smc_fvg_signals.py`

**Interfaces:**
- Adds `FVG_MAX_AGE_CANDLES = 48` to the SMC strategy family.
- Sets `startup_candle_count = 64` for both the base and context strategy.
- Active bullish/bearish FVG collections expire after 48 candles in the dataframe that is being processed, in addition to current price invalidation.
- The context's informative 1h bearish-FVG annotation applies the same finite-age rule in its own timeframe.

- [ ] **Step 1: Write failing signal-age/startup tests.**

  Assert both strategy classes report `startup_candle_count >= 64` and the age constant is 48. Build a synthetic dataframe with an otherwise matching bullish or bearish FVG and entry body after the FVG has exceeded 48 bars; assert no entry signal/tag/stop is emitted. Build a matching signal within the age window and assert the signal remains present.

  Exercise `_annotate_active_bearish_fvg` with an old bearish gap and assert its active marker expires, while a fresh gap remains active.

- [ ] **Step 2: Run focused tests and verify RED.**

  ```bash
  uv run pytest tests/test_smc_fvg_signals.py -q
  ```

  Expected: failures because the current classes allow indefinite active FVGs and advertise only 4/8 startup candles.

- [ ] **Step 3: Implement bounded state with no entry-rule changes.**

  Filter active collections using `i - fvg.bar_index < self.FVG_MAX_AGE_CANDLES` before signal matching. Apply the same filter to the context informative annotation. Set startup counts to 64. Do not alter the pin-bar, trend-body, displacement, FVG retrace, confirmation, context EMA, or side-selection predicates.

- [ ] **Step 4: Run focused tests and verify GREEN.**

  ```bash
  uv run pytest tests/test_smc_fvg_signals.py -q
  ```

- [ ] **Step 5: Commit bounded FVG state.**

  ```bash
  git add src/strategies/SMC_FVG_Confirmation_Freqtrade.py src/strategies/SMC_FVG_Context30m_Freqtrade.py tests/test_smc_fvg_signals.py
  git commit -m "fix: bound SMC FVG lifetime and startup history"
  ```

### Task 6: Verify that the context strategy preserves its own exit architecture

**Files:**
- Modify: `tests/test_runtime_protections.py`
- Modify: `tests/test_smc_fvg_callbacks.py`
- Create: `tests/test_smc_fvg_contract.py`

**Interfaces:**
- Context strategy inherits SMC callback behavior without introducing a separate universal risk or exit policy.
- Context-specific timeframe (`30m`), informative timeframe (`1h`), EMA regime filter, cooldown protection, and short displacement exception remain unchanged.
- Entry tags preserve the structural-stop payload through the inherited callback boundary.

- [ ] **Step 1: Write failing preservation tests.**

  Assert `SMC_FVG_Context30m_Freqtrade` retains `timeframe == "30m"`, the 1h informative method, its exact `CooldownPeriod` protection, `can_short`, and the context filters. Assert a long/short context tag reaches the inherited stake/stop/ROI callbacks without a current-candle lookup.

  Assert no unrelated strategy fixture inherits the new `SMC_*` keys or `SMC` callback methods, and no generic `FuturesRiskBase_Freqtrade` production abstraction is introduced.

- [ ] **Step 2: Run focused tests and verify RED.**

  ```bash
  uv run pytest tests/test_runtime_protections.py tests/test_smc_fvg_callbacks.py tests/test_smc_fvg_contract.py -q
  ```

- [ ] **Step 3: Add only compatibility-preserving assertions/implementation adjustments.**

  Keep all context code paths unchanged except the inherited startup/expiry and risk callbacks. If a callback requires a context-specific override, call the pure calculator with the context's existing stop and use a namespaced key; do not move exit logic into a base shared by other strategies.

- [ ] **Step 4: Run focused tests and verify GREEN.**

  ```bash
  uv run pytest tests/test_runtime_protections.py tests/test_smc_fvg_callbacks.py tests/test_smc_fvg_contract.py -q
  ```

- [ ] **Step 5: Commit preservation coverage.**

  ```bash
  git add tests/test_runtime_protections.py tests/test_smc_fvg_callbacks.py tests/test_smc_fvg_contract.py
  git commit -m "test: lock SMC context exit semantics"
  ```

### Task 7: Add strategy/config load gates without running a backtest

**Files:**
- Modify: `tests/test_validation_regressions.py`
- Modify: `tests/test_smc_fvg_contract.py`
- Modify: `config/validation.baseline.json` only if the existing policy explicitly needs the new risk fields
- Modify: `README.md` only for truthful risk/exit documentation

**Interfaces:**
- Strategy loading rejects malformed SMC cost/risk configuration before validation.
- Validation metadata can identify plan version, risk formula version, strategy name, and config hash.
- No backtest, dry-run, live process, or promotion is started by this plan.

- [ ] **Step 1: Write failing load/identity tests.**

  Assert both SMC strategy classes import and instantiate with `config/config.futures.json`. Assert the config hash and risk formula version are stable in the strategy validation metadata. Assert a config missing a required `smc_*` key is rejected before a validator runner is called.

  Assert source inspection contains no `return min(proposed_stake, max_stake)` fallback, no latest-candle stop recovery in callbacks, and retains `stoploss = -0.99` for ordinary structural-stop compatibility while exposing the explicit SMC missing-state fallback.

- [ ] **Step 2: Run focused tests and verify RED.**

  ```bash
  uv run pytest tests/test_validation_regressions.py tests/test_smc_fvg_contract.py -q
  ```

- [ ] **Step 3: Implement the load gate and metadata only.**

  Reuse the existing validation identity code to hash the config and record the risk/exit contract versions. Add explicit config validation for finite SMC values. Keep baseline performance thresholds and pair/timeframe policy unchanged.

- [ ] **Step 4: Run focused tests and verify GREEN.**

  ```bash
  uv run pytest tests/test_validation_regressions.py tests/test_smc_fvg_contract.py -q
  ```

- [ ] **Step 5: Commit load-gate coverage.**

  ```bash
  git add tests/test_validation_regressions.py tests/test_smc_fvg_contract.py config/validation.baseline.json README.md
  git commit -m "test: gate SMC risk and exit identity"
  ```

### Task 8: Run the complete hardening verification gate

**Files:**
- No new production files
- Test and strategy files from Tasks 1-7

**Interfaces:**
- Produces evidence that risk sizing is cost-aware, missing-state behavior is protective, FVG state is bounded, and context exits remain strategy-specific.

- [ ] **Step 1: Run the focused SMC and risk suite.**

  ```bash
  uv run pytest tests/test_strategy_risk.py tests/test_smc_fvg_callbacks.py tests/test_smc_fvg_signals.py tests/test_smc_fvg_contract.py tests/test_runtime_protections.py -q
  ```

  Require exit code `0`.

- [ ] **Step 2: Run the complete Python suite and static checks.**

  ```bash
  uv run pytest -q
  uv run ruff check src/strategies research_runtime scripts tests
  uv run python -m compileall -q src research_runtime scripts
  git diff --check
  ```

- [ ] **Step 3: Load strategies without starting trading.**

  ```bash
  uv run python -m freqtrade list-strategies --strategy-path src/strategies
  ```

  Require `SMC_FVG_Confirmation_Freqtrade` and `SMC_FVG_Context30m_Freqtrade` to load successfully. Do not run `freqtrade trade`, `make dry-run`, `make demo`, `make live`, `compose-demo`, or `compose-live`.

- [ ] **Step 4: Confirm no unrelated strategy behavior was changed.**

  ```bash
  git diff -- src/strategies config tests | sed -n '1,260p'
  pgrep -af 'freqtrade (trade|webserver)|compose-(demo|live)' || true
  ```

  Review every changed line against the SMC-only scope and require no new trading process.

- [ ] **Step 5: Record hypothesis, verification, and decision.**

  Hypothesis: fee/slippage-aware, tag-bound risk sizing plus bounded FVG state prevents unsafe sizing/stops and stale entries without changing SMC's intended 1R/no-signal-exit/context behavior.

  Verify with the focused suite, complete suite, static checks, and strategy-load output above. Keep the changes only if every gate passes; otherwise discard the failing implementation or write the next single-variable regression test before changing code. Do not infer OOS performance, dry-run readiness, or promotion approval from unit tests alone.
