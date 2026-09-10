# 2026-09-10 OOS robustness screening

## H014 - remove the extra 30m short branch

- verify: real validation on the frozen WFO snapshot, manifest `.research/smc_fvg_pinbar/runs/20260910T140757975541Z/manifest.json`
- changed scope: candidate only; base strategy/config/policy unchanged
- result: `FAIL`; folds `30 / 26 / 24` trades, stressed returns `-33.55% / -13.55% / -8.94%`, drawdowns `33.55% / 18.09% / 15.37%`
- keep_or_discard: discard H014; removing the extra short branch did not restore OOS robustness

## H015 - require 1h price and EMA20 slope alignment

- verify: real validation on the frozen WFO snapshot, manifest `.research/smc_fvg_pinbar/runs/20260910T141313135891Z/manifest.json`
- changed scope: candidate entry filter only; base strategy/config/policy unchanged
- result: `FAIL`; folds `33 / 21 / 20` trades, stressed returns `-10.82% / -13.97% / -3.41%`, drawdowns `20.53% / 16.64% / 8.96%`
- keep_or_discard: discard H015; fewer trades and negative aggregate stressed OOS profit remain

## H016 - require only 1h price/EMA20 side alignment

- verify: real validation on the frozen WFO snapshot, manifest `.research/smc_fvg_pinbar/runs/20260910T141649405325Z/manifest.json`
- changed scope: candidate entry filter only; base strategy/config/policy unchanged
- result: `FAIL`; results are identical to H015 (`74` trades, stressed returns `-10.82% / -13.97% / -3.41%`, drawdowns `20.53% / 16.64% / 8.96%`), so the slope condition changed no signals in this sample
- keep_or_discard: discard H016; no evidence of a useful improvement

## H017 - rolling current-window diagnostic

- verify: current baseline strategy on a newly seeded six-pair snapshot, `2026-02-12..2026-09-10`; manifest `.research/smc_fvg_pinbar/runs/20260910T142336334271Z/manifest.json`
- changed scope: validation window/data snapshot only; no strategy change
- data: all six pairs have chronological `1m/30m/1h` coverage from `2026-02-12`, common end `2026-09-10T14:00Z`
- correctness: lookahead passed (`20` signals, no bias); recursive analysis conclusive with no lookahead
- result: `FAIL`; folds `27 / 30 / 21` trades, stressed returns `-21.97% / -7.66% / -6.74%`, drawdowns `23.28% / 17.58% / 10.83%`; aggregate `78` trades, below the required `100`; attribution has no two profitable pair/tag sources
- supplementary bootstrap (not eligible as a gate because the sample is below `100` trades): p95 max drawdown `68.55%`, p05 net profit `-66.10%`, p95 losing streak `6` trades
- gate check: `make validate-pass VALIDATION_MANIFEST=.research/smc_fvg_pinbar/runs/20260910T142336334271Z/manifest.json` rejected the manifest (`validation verdict is not PASS`)
- keep_or_discard: keep as supplementary failure evidence; it does not override the fixed WFO failure

## H018 - halve the target ROI while keeping entries and stops frozen

- verify: real validation on the frozen WFO snapshot, manifest `.research/smc_fvg_pinbar/runs/20260910T143726751765Z/manifest.json`
- changed scope: candidate exit target only (`1R -> 0.5R`); entry logic, stop, basket, fee/slippage, and policy unchanged
- result: `FAIL`; folds `46 / 28 / 25` trades, stressed returns `-12.38% / -12.90% / -4.93%`, drawdowns `21.28% / 20.98% / 11.56%`; aggregate `99` trades, below the required `100`
- interpretation: win-rate improved to roughly `61% / 57% / 60%`, but expectancy stayed negative; long-side losses and single-source attribution remain
- keep_or_discard: discard H018; do not promote the half-R target or sweep more ROI values against this sample

## Conclusion

The frozen strategy is not eligible for dry-run. Three small entry-filter hypotheses were discarded, and the rolling diagnostic reproduces negative OOS behavior without a correctness failure. Further parameter or basket tuning would be post-hoc selection against the failed window; require a separately specified strategy thesis before another candidate.

The same supplementary bootstrap on the fixed WFO export gives p95 max drawdown
`92.42%` and p05 net profit `-86.04%` (95 trades). These are diagnostic-only
because both samples miss the policy trade minimum, but they reinforce rather
than weaken the fail-closed decision.
