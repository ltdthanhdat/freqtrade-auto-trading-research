# RSI divergence research decisions

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
