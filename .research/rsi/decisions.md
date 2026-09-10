# RSI divergence research decisions

## Research chain index

| Hypothesis | Experiment | Evidence |
|---|---|---|
| [`H-RSI-00`](hypotheses/H-RSI-00_immutable_universe.md) | [`E-RSI-00`](experiments/E-RSI-00_immutable_universe.md) | [screening § H-RSI-00](runs/2026-09-10_rsi_divergence_screening.md#h-rsi-00--universe-audit) |
| [`H-RSI-01`](hypotheses/H-RSI-01_regular_divergence_30m.md) | [`E-RSI-01`](experiments/E-RSI-01_regular_divergence_30m.md) | [screening § H-RSI-01](runs/2026-09-10_rsi_divergence_screening.md#h-rsi-01--regular-rsi-divergence) |
| [`H-RSI-02`](hypotheses/H-RSI-02_ema50_direction_filter.md) | [`E-RSI-02`](experiments/E-RSI-02_ema50_direction_filter.md) | [screening § H-RSI-02](runs/2026-09-10_rsi_divergence_screening.md#h-rsi-02--1h-ema50-direction-filter) |
| [`H-RSI-03`](hypotheses/H-RSI-03_hidden_divergence_30m.md) | [`E-RSI-03`](experiments/E-RSI-03_hidden_divergence_30m.md) | [screening § H-RSI-03](runs/2026-09-10_rsi_divergence_screening.md#h-rsi-03--hidden-rsi-divergence) |
| [`H-RSI-04`](hypotheses/H-RSI-04_regular_divergence_1h.md) | [`E-RSI-04`](experiments/E-RSI-04_regular_divergence_1h.md) | [screening § H-RSI-04](runs/2026-09-10_rsi_divergence_screening.md#h-rsi-04--regular-divergence-on-1h) |
| [`H-RSI-05`](hypotheses/H-RSI-05_ema50_1h.md) | [`E-RSI-05`](experiments/E-RSI-05_ema50_1h.md) | [`rsi-h005-wfo/`](runs/rsi-h005-wfo/) |
| [`H-RSI-06`](hypotheses/H-RSI-06_short_only.md) | [`E-RSI-06`](experiments/E-RSI-06_short_only.md) | [`rsi-h006-wfo/`](runs/rsi-h006-wfo/) |
| [`H-RSI-07`](hypotheses/H-RSI-07_4h_regime_filter.md) | [`E-RSI-07`](experiments/E-RSI-07_4h_regime_filter.md) | [`rsi-h007-smoke/`](runs/rsi-h007-smoke/) |

## H-RSI-00 — Keep immutable research universe

- The 24-pair basket was selected with point-in-time liquidity and coverage filters before strategy returns were observed.
- Keep it as the fixed RSI screening basket; the production six-pair basket remains unchanged.

## H-RSI-01 — Discard standalone regular divergence

- 30m regular RSI divergence lost `72.21%` over `235` trades with `73.89%`
  drawdown.
- Do not promote the unfiltered signal.

## H-RSI-02 — Discard 1h EMA50 context filter

- The 30m signal plus 1h EMA50 filter remained negative (`-17.00%`) and had
  `35.51%` drawdown.
- Do not continue parameter tuning on this branch.

## H-RSI-03 — Discard hidden divergence

- Hidden divergence lost `59.62%` over `328` trades with `62.39%` drawdown.
- Close the hidden-divergence branch for this sample.

## H-RSI-04 — Discard regular 1h execution

- Raw profit was positive (`+26.29%`) but drawdown reached `40.44%`.
- It fails the risk screen.

## H-RSI-05 — Discard EMA50 branch after WFO

- Fold two was `-29.31%` with `39.83%` drawdown and bootstrap p95 drawdown was
  `92.93%`.
- No promotion or risk/ROI sweep.

## H-RSI-06 — Discard short-only branch

- Fold two was `-23.24%` with `30.83%` drawdown; aggregate trades and tail-risk
  checks also failed.
- Do not promote the short-only branch.

## H-RSI-07 — Discard 4h regime filter

- The smoke produced `32` trades, `+17.11%` raw profit, and `15.94%` drawdown,
  breaching the fixed `15%` screen ceiling.
- Close the RSI-divergence branch for this sample.
