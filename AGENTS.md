# AGENTS

Freqtrade repo for `SMC_FVG_Context30m`.

## Goal

1. seed data in correct Freqtrade format
2. reproducible backtest
3. dry-run / live only after above is stable

## Approach

- Think before editing.
- If multiple interpretations exist, state assumptions explicitly.
- If the root cause is unclear, write a hypothesis first.
- Only change one variable per loop.

## Code edit rules

- Minimal changes only.
- No features outside scope.
- No refactoring unrelated code.
- No premature optimization.

## Default write scope

- `src/strategies/SMC_FVG_Context30m_Freqtrade.py`
- `config/config.futures.json`
- `scripts/seed_freqtrade_data.py`
- `.research/`

## Verify

- seed data → data downloads, output lands in `user_data/data`
- backtest → strategy loads, backtest runs
- dry-run → futures config valid, pairs in correct Freqtrade format

## Seed & backtest notes

- Always include `1m` in timeframes when seeding. By default, backtest only checks exit (stoploss/ROI/trailing) at the execution TF's candle close (30m). `--timeframe-detail 1m` tells backtest to check each 1m candle inside that 30m candle — exit timing matches live more closely. Entry still happens at 30m close only, unaffected.
- Backtest default timeframes: `30m`, `1h`, `1m`.

## Source of truth

Read `README.md` root, then `.research/smc_fvg_pinbar/state.md` → `decisions.md` → `roadmap.md`.

## Response style

- Keep it short.
- Tuning / experiment / backtest: state `hypothesis` → `verify` → `keep` or `discard`.
- Operations (config, seed, dry-run, errors): answer directly, no forced format.
