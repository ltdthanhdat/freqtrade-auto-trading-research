---
name: freqtrade-strategy-research-loop
description: "Use when iterating on a Freqtrade strategy in this repo: forming one hypothesis at a time, running a bounded backtest or dry-run validation, and updating the linked research chain from hypothesis to experiment to run to decision to state."
---

# Freqtrade Strategy Research Loop

Use for iterative strategy research inside `freqtrade-template`.
Current primary strategy is `SMC_FVG_Context30m_Freqtrade`.

## Current source of truth

Read these first:

- `README.md` (root — flow chart, setup)
- `.research/smc_fvg_pinbar/state.md`
- `.research/smc_fvg_pinbar/decisions.md`
- `.research/smc_fvg_pinbar/roadmap.md`

## Hard constraints

- Only change one hypothesis at a time.
- Default write scope:
  - `src/strategies/SMC_FVG_Context30m_Freqtrade.py`
  - `config/config.futures.json`
  - `scripts/seed_freqtrade_data.py`
  - `.research/smc_fvg_pinbar/`
- Do not add new entry logic, indicators, TP/SL ideas, or pair expansion unless explicitly asked.
- Do not mix docs refactor with strategy tuning in the same loop.

## Active phase

- accepted 30m hybrid snapshot (D011)
- prioritize dry-run validation over further tuning

## Standard loop

1. Read state first.
2. State one short hypothesis.
3. Make the smallest possible change.
4. Run the smallest comparable validation:
   - seed only if the issue is data availability
   - single-pair backtest first if the issue is strategy behavior
   - basket backtest only after single-pair is stable
   - dry-run only after backtest and config are stable
5. Log the run in the research chain.
6. Keep or discard explicitly.
7. Update decision and state only if the working direction changes.

## Metrics to compare

Always capture: `trades_count`, `net_profit_pct`, `max_drawdown_pct`, `win_rate`

Also capture when useful: timerange, tested pair or basket, pairs failing due to metadata, which execution layer caused the issue (seed / config / callback / execution path).

## Keep / discard rule

Keep when:
- it improves or stabilizes the target case
- and does not make the general flow more complex

Discard when:
- it improves one narrow case but weakens the default flow
- it adds tuning while the root cause is still unclear

## Output discipline

After each loop:
- create or update `.research/smc_fvg_pinbar/runs/` with raw results
- update the linked `.research/smc_fvg_pinbar/experiments/` file if interpretation changed
- update `.research/smc_fvg_pinbar/decisions.md` if there is a keep/discard
- update `.research/smc_fvg_pinbar/state.md` if current truth changed
- update `.research/smc_fvg_pinbar/roadmap.md` only for phase or next-step changes

Use this compact log format:

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

## Reference

See `reference.md` in this folder for commands, dry-run/live setup, and known blockers.
