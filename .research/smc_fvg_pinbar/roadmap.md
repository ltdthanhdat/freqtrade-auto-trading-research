# SMC_FVG_PinBar Roadmap

Status: active
Current phase: `accepted cadence-pass snapshot, prioritize execution validation`

## Goal

Use Freqtrade as a stable execution engine: seed data -> reproducible backtest -> dry-run -> then live.

## Execution order

1. seed sufficient `30m + 1h` data for the current basket
2. backtest the basket to confirm reproducibility
3. dry-run with the currently accepted snapshot
4. only tune further when there is a new objective

## Open hypotheses

- none

## Deferred

- `H004` (live risk preset) -- needs confirmation when dry-run evidence is available

## Resolved

| ID | Decision | Summary |
|---|---|---|
| H001 | keep | threshold `0.45 / 0.55` |
| H002 | keep | freeze tuning, proceed to dry-run |
| H005 | keep | leverage-aware risk handling |
| H006 | keep | prune STG |
| H007 | discard | prune/filter-only path for `>70%` |
| H008 | keep | entry mix + basket prune + concurrency |
| H009 | discard | minimal cadence-only tuning |
| H010 | discard | simple add-on branches |
| H011 | discard | `30m execution + 1h context` (old) |
| H012 | keep | hybrid `30m` with active `1h` base |

## Rules

- each round only changes `1` thing
- prioritize stable flow first
- do not tune when the root cause is unclear
- do not write raw results into this file
