# SMC_FVG_PinBar Roadmap

Status: active
Current phase: `validation failed; OOS robustness investigation`

## Goal

Use Freqtrade as a stable execution engine: seed data -> reproducible backtest -> dry-run -> then live.

## Execution order

1. seed sufficient `30m + 1h` data for the current basket
2. backtest the basket to confirm reproducibility
3. dry-run with the currently accepted snapshot
4. only tune further when there is a new objective

The current validation run failed the OOS gate, so step 3 is blocked. The next
loop must inspect retained fold evidence and state one hypothesis before any
strategy edit.

## Open hypotheses

- H013 result: fixed WFO and rolling current-window diagnostics both fail while lookahead/recursive checks pass; treat the current issue as performance robustness, not a correctness defect
- next hypothesis must be a separately justified strategy thesis; no threshold, basket, or policy tuning is approved from the retained failures

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
| H013 | discard dry-run admission | D011 fails fixed WFO; rolling diagnostic confirms the failure is not confined to one window |
| H014 | discard | remove extra 30m short branch |
| H015 | discard | require 1h price and EMA20 slope alignment |
| H016 | discard | require 1h price/EMA20 side alignment only |
| H017 | keep evidence / block dry-run | rolling current-window diagnostic fails |
| H018 | discard | half-R target improves win-rate but remains negative OOS |
| H019 | discard | no cooldown worsens OOS and still misses trade minimum |
| H020 | discard | symmetric displacement branch generated no new signals |
| H021 | discard | pure 1h FVG baseline worsens OOS despite more trades |
| H022 | discard | breakout-retest fails first OOS fold smoke with extreme drawdown |

## Rules

- each round only changes `1` thing
- prioritize stable flow first
- do not tune when the root cause is unclear
- do not write raw results into this file
