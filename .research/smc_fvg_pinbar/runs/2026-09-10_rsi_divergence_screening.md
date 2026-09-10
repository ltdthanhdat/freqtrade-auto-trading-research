# RSI divergence screening — 2026-09-10

## H-RSI-00 — universe audit

- Hypothesis: broaden the research basket first, then apply only point-in-time market/data eligibility filters before any OOS result is observed.
- Source: Binance futures market metadata and daily OHLCV queried at `2026-09-10T16:16:47Z`.
- Candidate universe: 30 active linear `USDT` swaps with complete daily history from `2026-01-24`.
- Eligibility filter: first 90 days (`2026-01-24`–`2026-04-24`) median `close * volume` proxy at least `20,000,000` USD/day; this is a liquidity proxy, not an exchange quote-volume field.
- Retained fixed basket (24): BTC, ETH, SOL, BNB, XRP, DOGE, ADA, AVAX, LINK, LTC, DOT, UNI, AAVE, NEAR, ARB, OP, SUI, FIL, ETC, BCH, XLM, APT, WLD, TAO.
- Excluded by the pre-filter: ATOM, INJ, PENDLE, RUNE, SEI, TIA. They were not removed using strategy returns.
- Snapshot: `user_data/data/snapshots/rsi_divergence_universe_2026q3_wfo`.
- Snapshot verification: 24/24 pairs × `1m/30m/1h`; `1m=303840`, `30m=10128`, `1h=5512` rows; the validation window has no detected gaps and starts at `2026-01-24`.
- Decision: **KEEP as the immutable RSI screening basket**. The existing accepted six-pair production basket remains unchanged and is not replaced by this candidate basket.

## H-RSI-01 — regular RSI divergence

- Hypothesis: RSI(14) regular divergence on confirmed 30m pivots (`left=3`, `right=3`) can provide a standalone reversal signal; structural stop is the second confirmed price pivot.
- Causality: a pivot at `p` is only evaluated on row `p+3`; no centered/future-filled series is used. Unit tests cover confirmation delay and future-prefix invariance.
- Candidate: `.research/smc_fvg_pinbar/candidates/RSI_Divergence30m_Freqtrade.py`.
- Smoke verification: first OOS-sized window `20260524-20260623`, 24 pairs, `1m` detail, protections enabled, fee `0.001`.
- Result: 235 trades, stressed-like raw backtest profit `-72.21%`, max drawdown `73.89%`, final balance `277.858 USDT`; long `-62.62%`, short `-9.59%`.
- Decision: **DISCARD as a standalone signal**. Do not run the expensive 3-fold gate for this unfiltered version. Keep the causal helper/tests as the base for the next single-variable experiment.

Next experiment: add only a 1h EMA50 direction filter to the same divergence events (H-RSI-02); do not tune pivot or risk parameters yet.

## H-RSI-02 — 1h EMA50 direction filter

- Hypothesis: suppress regular-divergence entries against the 1h EMA50 direction while leaving RSI/pivot/stop parameters unchanged.
- Smoke verification: same `20260524-20260623` window, 24 pairs, `1m` detail, protections and fee unchanged.
- Result: 104 trades, raw profit `-17.00%`, final balance `829.974 USDT`, max drawdown `35.51%`; long `-38.19%`, short `+21.18%`.
- Decision: **DISCARD for the current gate**. The filter materially reduced overtrading (235 → 104) but still fails positive return and the 15% drawdown ceiling. No full WFO run.

Next experiment: test hidden RSI divergence as a separate signal family, without adding another confirmation filter.

## H-RSI-03 — hidden RSI divergence

- Hypothesis: hidden bullish/bearish divergence (higher price low with lower RSI low, or lower price high with higher RSI high) may follow trends better than regular reversal divergence.
- Smoke verification: same `20260524-20260623` window, 24 pairs, `1m` detail, protections and fee unchanged.
- Result: 328 trades, raw profit `-59.62%`, final balance `403.809 USDT`, max drawdown `62.39%`; long `-57.80%`, short `-1.82%`.
- Decision: **DISCARD as a standalone 30m signal**. No full WFO run.

Next experiment: hold the regular-divergence logic fixed and move execution from 30m to 1h to test whether the higher timeframe reduces noise.

## H-RSI-04 — regular divergence on 1h

- Hypothesis: using the same regular-divergence logic on 1h candles reduces 30m noise enough to improve robustness.
- Smoke result: 106 trades, raw profit `+26.29%`, but max drawdown `40.44%`; one trade lost `-86.74%`.
- Decision: **DISCARD without WFO**. Positive return alone is not sufficient when drawdown is above the fixed 15% limit.

## H-RSI-05 — 1h regular divergence plus 1h EMA50

- Hypothesis: align the 1h regular-divergence signal with the same-timeframe EMA50 direction.
- Smoke result: 39 trades, raw profit `+53.11%`, max drawdown `10.24%`.
- WFO verification: lookahead `PASS`, recursive `PASS`; folds were `39 / +51.98% / 10.37% DD`, `49 / -29.31% / 39.83% DD`, and `38 / +12.18% / 14.63% DD` after stress.
- Bootstrap: p95 max DD `92.93%`, p05 net profit `-70.99%`, gate eligible because aggregate trades were `126`.
- Attribution: only the bearish tag was profitable across OOS; the bullish tag was negative, so attribution gate failed.
- Decision: **DISCARD for deployment**. The smoke was regime-dependent and WFO/Monte Carlo exposes unacceptable tail risk. Production strategy/config remains untouched.

Next experiment: test the same 1h EMA50 branch with long entries disabled; this is a new directional hypothesis, not a tuning change to H-RSI-05.

## H-RSI-06 — 1h regular divergence plus EMA50, short-only

- Hypothesis: the bearish regular-divergence side may carry the edge while long reversals add the losses; disable long entries without changing the short signal, stop, or risk handling.
- Smoke result: 33 short trades, raw profit `+25.12%`, max drawdown `11.55%`, win rate `63.6%`.
- WFO verification: lookahead `PASS`, recursive `PASS`; folds were `33 / +24.19% / 11.72% DD`, `34 / -23.24% / 30.83% DD`, and `30 / +15.60% / 9.55% DD` after stress.
- Bootstrap: aggregate `97` trades is below the `100`-trade gate; diagnostic p95 max DD `51.96%`, p05 net profit `-40.03%`.
- Attribution: only one bearish short tag is present, so the two-positive-source requirement is not met.
- Decision: **DISCARD for deployment**. Removing longs does not resolve the adverse middle fold or the tail-risk evidence; do not widen the short-only branch with parameter tuning.

Next experiment: add one higher-timeframe bearish-regime filter (`4h close < 4h EMA50`) to H-RSI-06 and screen it on the same first OOS fold.

## H-RSI-07 — short-only regular divergence plus 4h EMA50 regime

- Hypothesis: require the 4h close to remain below its EMA50 before accepting a 1h bearish divergence, which may suppress short signals taken during higher-timeframe strength.
- Changed scope: one `4h` informative EMA50 regime filter; pivot, RSI, stop, fee, protection, leverage, and pair universe unchanged.
- Smoke verification: `20260524-20260623`, 24 pairs, `1h` execution, `1m` detail, protections enabled, fee `0.001`; immutable snapshot `rsi_divergence_universe_2026q3_wfo_4h`.
- Result: 32 short trades, raw profit `+17.11%`, win rate `59.4%`, max drawdown `15.94%`, final balance `1171.064 USDT`.
- Artifact: `.research/smc_fvg_pinbar/runs/rsi-h007-smoke/backtest-result-2026-09-10_23-41-51.zip`.
- Decision: **DISCARD without full WFO**. The first OOS-sized screen already breaches the fixed `15%` drawdown ceiling and is weaker than H-RSI-06 on the same window; a full WFO would not be an economical gate candidate.

RSI divergence screening stop condition: H-RSI-01 through H-RSI-07 have no candidate meeting the smoke/WFO robustness gates. Production strategy/config remains unchanged and dry-run remains blocked.
