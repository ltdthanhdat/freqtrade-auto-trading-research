# 2026-09-10 WFO validation failure

Hypothesis:
- id: H013
- hypothesis: The frozen D011 hybrid baseline remains robust across three chronological OOS folds after frozen fee and slippage stress.
- changed_scope: none; validation-only run

Verify:
- command: `uv run python -m scripts.validate_baseline --config config/config.futures.json --datadir user_data/data/snapshots/accepted_6pair_2026q3_wfo --policy config/validation.baseline.json --strategy SMC_FVG_Context30m_Freqtrade --strategy-path src/strategies --strategy-file src/strategies/SMC_FVG_Context30m_Freqtrade.py --start 2026-01-24 --end 2026-08-22 --runs-dir .research/smc_fvg_pinbar/runs --approved-identity .research/smc_fvg_pinbar/approved-baseline-identity-wfo.json`
- timerange: `2026-01-24..2026-08-22`
- pair_or_basket: accepted six-pair basket
- linked_run: `.research/smc_fvg_pinbar/runs/20260910T135821667756Z/manifest.json`
- correctness: lookahead passed (`20` signals, no bias); recursive analysis conclusive with no lookahead
- folds: `2026-05-24..2026-06-23`, `2026-06-23..2026-07-23`, `2026-07-23..2026-08-22`

Result:
- trades_count: `95` aggregate (`43 / 27 / 25`)
- net_profit_pct: stressed `-31.66% / -14.80% / -7.64%`
- max_drawdown_pct: `31.66% / 19.28% / 14.17%`
- win_rate: see retained Freqtrade ZIP artifacts; aggregate trade minimum is not met
- keep_or_discard: discard dry-run admission; keep the frozen baseline and failure evidence
- notes: raw stressed returns are negative in every fold, so the failure is not caused only by the stress deduction. The accepted-window reproduction remains positive (`106` trades, `69.8%`, `+318.4%`, DD `8.11%`) but does not establish OOS robustness.

Decision:
- Do not start dry-run from this baseline. Create a new hypothesis for regime/entry robustness before any strategy change; do not tune thresholds against this failed result.
