---
name: smc-fvg-pinbar-freqtrade-autoresearch
description: Use when continuing the SMC_FVG_PinBar work inside freqtrade-template: parity checks against Jesse, small Freqtrade strategy adjustments, compare-script runs, dry-run preparation, or docs updates for the Freqtrade migration path.
---

# SMC_FVG_PinBar Freqtrade Autoresearch

Use this skill only for iterative work inside `freqtrade-template`.

## Current source of truth

Read these first:

- `docs/README.md`
- `docs/state/smc_fvg_pinbar_freqtrade_state.md`
- `docs/notes/smc_fvg_pinbar_freqtrade_notes.md`
- `docs/research/smc_fvg_pinbar_freqtrade_migration_validation.md`
- `docs/plans/smc_fvg_pinbar_freqtrade_tuning_plan.md`
- `AGENTS.md`

## Hard constraints

- Only change one hypothesis at a time.
- Default write scope is:
  - `src/strategies/SMC_FVG_PinBar_Freqtrade.py`
  - `config/config.futures.json`
  - `scripts/prepare_smc_fvg_pinbar_data.py`
  - `scripts/compare_smc_fvg_pinbar_with_jesse.py`
  - `docs/state/smc_fvg_pinbar_freqtrade_state.md`
  - `docs/notes/smc_fvg_pinbar_freqtrade_notes.md`
  - `docs/research/smc_fvg_pinbar_freqtrade_migration_validation.md`
- Do not patch Jesse strategy or Jesse root docs unless the user explicitly asks.
- Do not add new entry logic, indicators, TP/SL ideas, or pair expansion while parity is still unclear.

## Active phase

Current active phase:

- parity first
- tuning later

Meaning:

- baseline `BTC-USDT 1h` is the first gate
- then recent `BTC-USDT`
- then recent selected basket

## Standard loop

1. Read state first.
2. State one short hypothesis.
3. Make the smallest possible change.
4. Run the smallest comparable validation:
   - baseline only if debugging engine behavior
   - compare script if validating broader parity
5. Compare against existing numbers.
6. Keep or discard explicitly.
7. Update docs if the working direction changes.

## Scripts to use

- Prepare Freqtrade data:

```bash
uv run python scripts/prepare_smc_fvg_pinbar_data.py --scope btc-baseline
uv run python scripts/prepare_smc_fvg_pinbar_data.py --scope recent-selected
```

- Full compare:

```bash
uv run python scripts/compare_smc_fvg_pinbar_with_jesse.py
```

- List strategies:

```bash
uv run freqtrade list-strategies --strategy-path src/strategies
```

## Metrics to compare

Always capture:

- `trades_count`
- `net_profit_pct`
- `max_drawdown_pct`
- `win_rate`

Also capture when useful:

- avg absolute diff vs Jesse
- which pairs fail due to Freqtrade metadata

## Keep / discard rule

Keep a change when:

- it reduces parity diff on the target case
- and does not clearly break baseline

Discard when:

- it improves one case but degrades baseline or several others
- it mixes parity work with fresh strategy tuning

## Output discipline

When you finish a loop:

- update `docs/research/smc_fvg_pinbar_freqtrade_migration_validation.md`
- update `docs/state/smc_fvg_pinbar_freqtrade_state.md` if direction changed

Use this compact structure:

```text
Experiment:
- hypothesis:
- file_changed:

Result:
- trades_count:
- net_profit_pct:
- max_drawdown_pct:
- win_rate:
- keep_or_discard:
- notes:
```
