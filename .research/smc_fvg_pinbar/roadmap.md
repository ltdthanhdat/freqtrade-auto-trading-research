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
- H-RSI-01 through H-RSI-07 were screened on a separate 24-pair liquidity/coverage-filtered universe; none passed the smoke/WFO robustness gates, so the RSI-divergence branch is closed for this sample
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
| H023 | discard | Bollinger pullback is under-sampled and negative OOS |
| H024 | discard | eight-pair basket expansion fails first OOS fold catastrophically |
| H025 | discard | short-only smoke improvement fails full WFO and trade-count gate |
| H026 | discard | BTC 1h EMA50 regime filter fails first OOS fold |
| H027 | discard | removing displacement confirmations fails first OOS fold |
| H-RSI-01 | discard | standalone 30m regular RSI divergence loses heavily |
| H-RSI-02 | discard | 30m RSI divergence plus 1h EMA50 remains negative/high-DD |
| H-RSI-03 | discard | hidden 30m RSI divergence loses heavily |
| H-RSI-04 | discard | regular RSI divergence on 1h breaches drawdown ceiling |
| H-RSI-05 | discard | 1h regular divergence plus EMA50 fails WFO/Monte Carlo |
| H-RSI-06 | discard | short-only branch fails fold two, trade minimum, and tail-risk checks |
| H-RSI-07 | discard | 4h EMA50 regime filter still breaches the smoke DD ceiling |

The validation runner now records block-bootstrap diagnostics below the trade
minimum while keeping those diagnostics out of the PASS gate until the sample
is eligible. This improves evidence visibility but does not change the current
dry-run block.

## Rules

- each round only changes `1` thing
- prioritize stable flow first
- do not tune when the root cause is unclear
- do not write raw results into this file
