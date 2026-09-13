# Per-Strategy Risk, Stop, and Exit Correctness Design

## Goal

Make position sizing and degraded-state protection correct for the current SMC/FVG strategy without flattening the different SL/TP/exit semantics of other strategies.

The shared layer accounts for risk. Each strategy owns its entry, protective stop, profit exit, time exit, trailing exit, regime exit, and precedence.

## Scope

This design applies first to:

- `src/strategies/SMC_FVG_Confirmation_Freqtrade.py`;
- `src/strategies/SMC_FVG_Context30m_Freqtrade.py`;
- the existing futures configuration and pure risk tests.

It defines the adapter contract that future strategy candidates must use, but it does not rewrite candidate artifacts, select a new strategy family, or change the current SMC entry thresholds.

## Non-goals

- no universal stop formula, ROI target, holding duration, trailing rule, or FVG behavior;
- no alpha tuning or performance optimization;
- no changes to current SMC signal definitions, FVG thresholds, pair basket, leverage, risk fraction, capital cap, cooldown, or ordinary 1R target;
- no claim of exact protection against gaps, liquidation, exchange outages, process crashes, funding, or concurrent account races;
- no enabling of exchange-native stops in this change. That requires a separate exchange-tested operational plan.

## Strategy-owned trading plan

A strategy provides a frozen plan with these independent parts:

```text
EntryPlan
ProtectiveStop
ProfitExit (including NONE)
TimeExit (including NONE)
TrailingExit (including NONE)
RegimeExit (including NONE)
EmergencyExit
ExitPrecedence
SizingPlan
CostModel
```

The SMC/FVG plan remains:

- entry: existing 1h-context/30m execution and existing signal priority;
- protective stop: FVG-derived absolute price stored in the entry tag;
- profit exit: existing gross 1R custom ROI from actual filled entry to structural stop;
- time/trailing/regime exits: `NONE` unless already defined by the strategy;
- emergency exit: explicit SMC fallback configuration for missing state;
- sizing: initial-stop-risk basis with the SMC config risk and capital limits.

A future reversal, breakout, or RSI candidate can use a fixed percentage, ATR, swing, channel, signal, time, or trailing exit. Its own plan and adapter must declare those choices. The shared code receives a stop and records risk; it does not turn those strategies into SMC or 1R strategies.

## Pure generic risk calculator

Create a small pure module with no wallet, dataframe, database, clock, exchange, or logging access.

Conceptual input:

```text
RiskInputs
- side: LONG | SHORT
- entry_rate: positive finite float
- stop_rate: positive finite float
- leverage: positive finite float
- max_leverage: positive finite float
- available_equity: positive finite float
- min_stake: optional positive float
- max_stake: positive float
- risk_fraction: 0 < x < 1
- collateral_cap_fraction: 0 < x <= 1
- entry_fee_rate: 0 <= x < 1
- exit_fee_rate: 0 <= x < 1
- entry_slippage_rate: 0 <= x < 1
- stop_slippage_rate: 0 <= x < 1
- emergency_loss_ratio: positive finite float
```

Conceptual output:

```text
RiskDecision
- accepted: bool
- rejection_code: string | null
- collateral_stake: float
- notional: float
- quantity: float
- price_distance_ratio: float
- collateral_loss_ratio: float
- target_risk_budget: float
- capital_cap_binding: bool
```

### Conservative execution prices

Let `P` be the strategy's entry estimate, `S` its own structural stop, and `L` the selected leverage.

For a long:

```text
entry_worst = P * (1 + entry_slippage_rate)
stop_worst  = S * (1 - stop_slippage_rate)
distance    = (entry_worst - stop_worst) / entry_worst
```

For a short:

```text
entry_worst = P * (1 - entry_slippage_rate)
stop_worst  = S * (1 + stop_slippage_rate)
distance    = (stop_worst - entry_worst) / entry_worst
```

Reject if `distance <= 0` or any input is non-finite/invalid.

### Estimated loss per collateral unit

Freqtrade futures uses stake as collateral and creates leveraged notional. Estimate the loss ratio per unit of collateral as:

```text
loss_ratio = L * (
    distance
    + entry_fee_rate
    + (stop_worst / entry_worst) * exit_fee_rate
)
```

This is a conservative planning estimate, not a guarantee of realized loss. Funding, gap risk, liquidation, and final exchange fees remain diagnostics/operational concerns.

Reject when `loss_ratio <= 0` or `loss_ratio >= emergency_loss_ratio`.

### Stake calculation

Use currently available collateral, not total balance including open stakes:

```text
E = min(available_equity, max_stake)
risk_budget = E * risk_fraction
risk_stake = risk_budget / loss_ratio
capital_cap = E * collateral_cap_fraction
candidate = min(risk_stake, capital_cap, E, max_stake)
```

Return zero on rejection. Never round a result upward to satisfy an exchange minimum.

Reject when:

- `min_stake` is greater than `E`;
- `candidate < min_stake`;
- `candidate <= 0`.

The strategy adapter passes `wallets.get_available_stake_amount()` and the callback's `max_stake`. `proposed_stake` is not treated as equity. Freqtrade's post-callback validator remains a second boundary.

### Required rejection codes

```text
MISSING_STOP
INVALID_STOP_SIDE
INVALID_NUMBER
INVALID_LEVERAGE
INVALID_RISK_CONFIG
NO_AVAILABLE_EQUITY
STOP_BEYOND_EMERGENCY_LIMIT
MIN_STAKE_UNAVAILABLE
MIN_STAKE_EXCEEDS_RISK
```

Missing or invalid risk configuration fails closed. It must not fall back to the proposed stake.

## Freqtrade callback adapter

Keep the public callback signatures:

- `leverage`;
- `custom_stake_amount`;
- `order_filled`;
- `custom_stoploss`;
- `custom_roi`;
- indicator and entry/exit population methods.

The adapter resolves a strategy-owned `EntryRiskIntent` from the entry tag and current callback context. It must not recover a stop from the latest dataframe candle because that candle may represent another signal after a delayed entry or restart.

For SMC/FVG:

1. parse `signal_kind|stop_rate`;
2. validate the stop side strictly (`long stop < entry`, `short stop > entry`);
3. pass that stop into the generic risk calculator;
4. return zero when invalid;
5. preserve the tag for restart-safe reconstruction.

The actual exchange fill can differ from the estimate. `order_filled` recomputes the normal SMC exit plan from `trade.open_rate` and the strategy stop.

## Stop and ROI semantics

Installed Freqtrade semantics used by the adapter are:

- futures position quantity is `stake_amount / entry_rate * leverage`; stake is collateral;
- `current_profit` is fee-aware and leverage-adjusted;
- `stoploss_from_absolute(..., leverage=trade.leverage)` returns the leveraged ratio expected by Freqtrade;
- leverage must be passed exactly once;
- custom ROI is compared to leveraged current profit.

For a valid SMC structural stop:

```python
stoploss_from_absolute(
    stop_rate,
    current_rate=current_rate,
    is_short=trade.is_short,
    leverage=trade.leverage,
)
```

Do not multiply or divide that result by leverage again.

For the SMC 1R target only:

```text
raw_risk = abs(trade.open_rate - stop_rate) / trade.open_rate
target_roi = raw_risk * trade.leverage
```

Other strategy adapters may return their own ROI/exit rule. The generic module must not calculate a universal target.

## Missing-state protection

Keep ordinary SMC class `stoploss = -0.99` unchanged so valid structural stops are not unexpectedly tightened.

Add the SMC-only config key:

```json
"smc_missing_stoploss_roi": -0.10
```

Validate it as finite and strictly between `-1` and `0`. It is used only when both versioned custom data and the entry tag fail validation. It represents loss on collateral under the installed leveraged semantics; at 5x it is approximately a 2% adverse price move.

Resolution order:

1. valid versioned persisted exit-plan data;
2. valid structural stop parsed from `trade.enter_tag`;
3. SMC-only missing-state fallback `abs(smc_missing_stoploss_roi)` for `custom_stoploss`, with no custom ROI.

A missing or invalid stop at entry returns zero from sizing and prevents opening. A filled trade with unrecoverable state receives the finite emergency fallback, not `None` and not the latest candle's stop.

Persist one versioned custom-data object where possible:

```json
{
  "version": 1,
  "stop_rate": 1.234,
  "signal_kind": "displacement"
}
```

`order_filled` catches persistence errors and verifies readback, but the entry tag remains the canonical fallback. Invalid custom data never overrides a valid tag. Atomic exchange fill plus database persistence is impossible inside the strategy callback and remains an operational limitation.

## Restart-stable SMC FVG state

This correctness change is SMC-specific:

```text
FVG_VALIDITY_CANDLES = 48
startup_candle_count = 64
```

An FVG created at candle index `c` is eligible for ages `0..47`; expire it before evaluating index `i` when `i - c >= 48`. Keep the existing price invalidation rules. Apply the same bounded lifetime to the 30m and 1h FVG state.

Do not emit signals until at least 52 complete rows are available for the relevant calculation (`48` lifetime + `3` gap detection candles + `1` previous candle). The additional startup margin covers EMA20 and informative-frame merging. This constant is operationally selected and must not be optimized.

The bounded FVG list becomes reconstructible from recent history. EMA remains recursively dependent on prior history; achieving bit-for-bit equality across arbitrary history windows would change its semantics and is deferred.

## Verification

Pure risk tests must prove:

- long/short adverse-slippage calculations;
- leverage is applied exactly once;
- fee and slippage costs change stake as expected;
- total balance is not used when available collateral is lower;
- max/capital caps bind correctly;
- wrong-side, missing, non-finite, stale, and over-limit stops reject;
- below-minimum stakes reject rather than round upward;
- invalid config fails closed;
- each rejection code is deterministic.

Strategy adapter tests must prove:

- SMC tag stop is used rather than latest dataframe stop;
- actual fill rate recalculates SMC's 1R ROI;
- custom data failure still gets tag/fallback protection;
- invalid custom data cannot override a valid tag;
- ordinary structural stop behavior remains unchanged;
- the SMC emergency fallback is used only in degraded state;
- FVG state expires at the fixed age and restart slices produce equivalent bounded state;
- existing entry signal definitions and thresholds are unchanged.

Validation is correctness-only in this workstream. Strategy performance is not an acceptance criterion.

## Later strategy-family integration

When a new candidate is researched, its complete plan is frozen before outer OOS. The candidate manifest records its own stop/TP/time/trailing/regime definitions, precedence, sizing basis, risk ledger identity, and cost model. The generic risk layer verifies safety and records comparable facts; it does not replace the candidate's exit implementation.

A three-family comparison uses one frozen complete candidate per family, a common pre-registered comparison OOS, and a sealed holdout for the selected winner. Existing SMC results are not retroactively promoted by this design.
