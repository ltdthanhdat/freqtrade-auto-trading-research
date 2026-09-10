# Dry-run Validation and Runtime Safety Design

## Purpose

Establish a reproducible gate for starting Freqtrade dry-run with the frozen
`SMC_FVG_Context30m_Freqtrade` baseline. The gate evaluates the accepted
six-pair basket and emits `PASS`, `WARN`, or `FAIL`; only `PASS` permits a
dry-run start. This design does not promote a bot to live trading.

## Scope and invariants

- The strategy, its entry logic, and the accepted six-pair basket are frozen
  while a validation run is evaluated.
- Each validation run uses a pinned strategy commit, effective config and
  policy hash, resolved local strategy-dependency hashes, and data snapshot
  hash.
- Missing required market data (`1m`, `30m`, or `1h`) is not silently filled
  from another source and cannot produce `PASS`.
- Validation never tunes a parameter after seeing an OOS result. A failed run
  creates research evidence, not an automatic strategy change.
- The project remains dry-run only. There is no automatic live promotion.

## Components

### Data seeding

`scripts/seed_freqtrade_data.py` remains the only data acquisition entry
point. It downloads the accepted basket and all three required timeframes,
then produces a named immutable snapshot under `user_data/data/snapshots/`.

### Validation runner

Add `scripts/validate_baseline.py`. It receives a snapshot, the baseline
config, and a fixed validation policy. It executes the stages below and writes
one run directory under `.research/smc_fvg_pinbar/runs/`.

1. Verify config basket, strategy commit and dependencies, snapshot OHLCV
   coverage for every accepted pair/timeframe, and hashes.
2. Run Freqtrade strategy loading, lookahead analysis, and recursive analysis.
3. Run chronological fixed-parameter OOS folds.
4. Run predefined cost-stress cases and per-pair/per-side/per-entry-tag
   attribution.
5. Run block-bootstrap Monte Carlo on exported trade returns.
6. Apply the policy and write a verdict and a machine-readable manifest.

The runner may invoke Freqtrade and analysis scripts, but does not edit a
strategy or configuration file.

### Decay monitor

`scripts/monitor_decay.py` continues to compare a recent dry-run trade window
with a long baseline export using a time-block bootstrap. It becomes the
source of runtime performance evidence, not a tuning mechanism. Its future
extension reports equity-path percentiles, maximum drawdown, and losing-streak
statistics in addition to win rate.

### Runtime enforcement and audit

Freqtrade remains responsible for enforcement using its persisted SQLite
trade database and native `PairLocks`. A separate gitignored
`user_data/validation_state.sqlite` stores validation state and audit events;
it does not alter Freqtrade's database schema.

The validation state database has two logical records:

- `current_state`: one current state per scope (`global`, `pair`, or
  `pair-side`) with `state`, `entered_at`, `lock_until`, `reason`, and the
  validation run identifier that caused it.
- `state_events`: append-only transition history with the same identifiers,
  trigger metrics, config hash, and a reference to the research artifact.

## State model

| State | Meaning | Enforcement |
|---|---|---|
| `ACTIVE` | The basket may enter trades. | No validation lock. |
| `YELLOW` | Performance is weak but evidence is insufficient for a pause. | Audit and alert only in v1. |
| `PAIR_OR_SIDE_LOCKED` | One pair or one futures side is temporarily excluded. | Native PairLock. |
| `PAUSED` | No new basket entries are allowed. | Global native PairLock. |

`CooldownPeriod` and short native protection locks reopen at their recorded
`lock_until`. A `PAUSED` state does not reopen merely because a timer elapsed.
It may reopen only after configuration/data health passes, the predefined
regime predicate is valid, the minimum cooldown has elapsed, and no red
trigger remains. If any condition fails, the state manager extends the lock.

In dry-run, this reopen rule may operate automatically so it can be tested. A
future live workflow must require an explicit human review before reopening.

## Validation policy

The policy lives in `config/validation.baseline.json` and is versioned with
the repository. It declares the accepted basket, fold schedule, cost-stress
cases, bootstrap seed and sample count, and state trigger thresholds.

The portfolio drawdown budget is 15%.

### OOS folds

The runner uses chronological non-overlapping OOS folds. Each fold first has
an in-sample history sufficient for indicator startup and for the already
frozen baseline; it does not select new parameters. A run requires at least
three OOS folds and at least 100 aggregate OOS trades. If the available common
history cannot satisfy this, the result is `WARN`, never `PASS`.

### Verdict rules

| Verdict | Conditions |
|---|---|
| `PASS` | Lookahead and recursive checks pass; at least three valid OOS folds and 100 aggregate OOS trades exist; aggregate OOS remains positive under cost stress; no OOS fold breaches 15% drawdown; Monte Carlo 95th-percentile maximum drawdown is at most 15%; and attribution does not reveal a single pair or tag as the sole source of the result. |
| `WARN` | The run is reproducible and free of detected bias, but lacks enough history/trades or has weak robustness without a 15% breach. |
| `FAIL` | A correctness check fails, data/config identity is broken, a fold breaches 15% drawdown, aggregate stressed OOS is negative, or an analysis stage cannot complete. |

The exact cost multipliers and regime predicates are fixed in the validation
policy before the corresponding run; they are not selected from its result.

## Dry-run workflow

1. A `PASS` manifest and the dry-run command must share the same strategy and
   dependency hashes, policy, basket, and config hash; the effective config
   must explicitly set `dry_run: true`.
2. Start Freqtrade dry-run with its own trade database.
3. On each closed trade, native protections evaluate PairLocks and the state
   evaluator records state evidence.
4. A red trigger or 15% portfolio drawdown creates a global PairLock, writes a
   diagnostic artifact, and enters `PAUSED`.
5. Dry-run produces a periodic review report: `continue`, `pause`, or
   `investigate`. It never changes strategy parameters or starts live trading.

## Testing and failure handling

- Unit tests cover fold boundaries, verdict boundaries at 15%, deterministic
  bootstrap output, and legal state transitions.
- Integration tests use a small fixture snapshot to prove strategy loading,
  missing-timeframe failure, basket mismatch failure, and persisted PairLock
  behavior across restart.
- Every Freqtrade backtest uses its own artifact filename/run directory; the
  runner never deletes historical backtest results.
- A failed seed, incomplete fold, missing artifact, or evaluator crash blocks
  `PASS`. A recovery never silently unlocks a `PAUSED` state.

## Explicit non-goals

- No automatic parameter optimization or hyperopt/WFO selection.
- No changes to entry/exit logic, pairs, leverage, or risk sizing in v1.
- No UI, dashboard, Telegram workflow, external service, or live-trading
  automation.
