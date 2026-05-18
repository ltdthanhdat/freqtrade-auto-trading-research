---
name: freqtrade-strategy-research-loop
description: "Use when iterating on a Freqtrade strategy in this repo: forming one hypothesis at a time, running a bounded backtest or dry-run validation, and updating the linked docs chain from hypothesis to experiment to run to decision to state."
---

# Freqtrade Strategy Research Loop

Use this skill for iterative strategy research inside `freqtrade-template`.

This skill is repo-local but strategy-agnostic in naming.
Current primary strategy is still `SMC_FVG_PinBar_Freqtrade`.

## Current source of truth

Read these first:

- `docs/README.md`
- `docs/smc_fvg_pinbar/README.md`
- `docs/smc_fvg_pinbar/state.md`
- `docs/smc_fvg_pinbar/decisions.md`
- `docs/smc_fvg_pinbar/roadmap.md`
- `AGENTS.md`

## Hard constraints

- Only change one hypothesis at a time.
- Default write scope is:
  - `src/strategies/SMC_FVG_PinBar_Freqtrade.py`
  - `config/config.futures.json`
  - `scripts/seed_freqtrade_data.py`
  - `docs/smc_fvg_pinbar/`
- Do not add new entry logic, indicators, TP/SL ideas, or pair expansion unless the user explicitly asks.
- Do not mix docs refactor with strategy tuning in the same loop unless the user asks for both.

## Active phase

Current active phase:

- freeze strategy for dry-run
- tune only after execution evidence exists

Meaning:

- seed data first
- then backtest `BTC/USDT:USDT 1h`
- then backtest current basket
- then dry-run current basket

## Standard loop

1. Read state first.
2. State one short hypothesis.
3. Make the smallest possible change.
4. Run the smallest comparable validation:
   - seed only if the issue is data availability
   - single-pair backtest first if the issue is strategy behavior
   - basket backtest only after the single-pair case is stable
   - dry-run only after backtest and config are stable
5. Log the run in the docs chain.
6. Keep or discard explicitly.
7. Update decision and state only if the working direction changes.

## Scripts to use

- Seed Freqtrade data:

```bash
uv run python scripts/seed_freqtrade_data.py --preset smc-basket --days 90
```

- List strategies:

```bash
uv run freqtrade list-strategies --strategy-path src/strategies
```

- Backtest:

```bash
uv run freqtrade backtesting \
  --config config/config.futures.json \
  --strategy SMC_FVG_PinBar_Freqtrade \
  --strategy-path src/strategies
```

## Metrics to compare

Always capture:

- `trades_count`
- `net_profit_pct`
- `max_drawdown_pct`
- `win_rate`

Also capture when useful:

- timerange
- tested pair or basket
- which pairs fail due to Freqtrade metadata
- whether the issue is in seed, config, callback, or execution path

## Keep / discard rule

Keep a change when:

- it improves or stabilizes the target case
- and does not make the general flow more complex

Discard when:

- it improves one narrow case but weakens the default flow
- it adds tuning while the root cause is still unclear

## Output discipline

When you finish a loop:

- create or update one file in `docs/smc_fvg_pinbar/runs/`
- update the linked file in `docs/smc_fvg_pinbar/experiments/` if interpretation changed
- update `docs/smc_fvg_pinbar/decisions.md` if there is a keep/discard decision
- update `docs/smc_fvg_pinbar/state.md` if current truth changed
- update `docs/smc_fvg_pinbar/roadmap.md` only for phase or next-step changes

Use this compact structure:

```text
Hypothesis:
- id:
- hypothesis:
- changed_scope:

Verify:
- command:
- timerange:
- pair_or_basket:

Result:
- trades_count:
- net_profit_pct:
- max_drawdown_pct:
- win_rate:
- keep_or_discard:
- linked_run:
- notes:
```
