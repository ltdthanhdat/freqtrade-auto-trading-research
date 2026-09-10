# RSI divergence research

This tree is research-only. RSI candidates, their local futures-risk base,
configs, and run evidence live under `.research/rsi`; no RSI module is loaded
from `src/strategies` and no RSI candidate is part of the production dry-run
gate.

## Layout

- `candidates/` — RSI strategy variants, local base, configs, and universe
- `hypotheses/` — one falsifiable research question per H-RSI record
- `experiments/` — one bounded test record per hypothesis, with linked evidence
- `runs/` — screening notes and immutable backtest/WFO artifacts
- `state.md` — current research truth
- `decisions.md` — keep/discard decisions
- `roadmap.md` — next research boundary

The research chain is explicit and stays separate from production code:

`hypotheses/` → `experiments/` → `runs/` → `decisions.md` → `state.md`

Run a candidate explicitly with the local strategy path:

```bash
uv run python -m freqtrade backtesting \
  --config .research/rsi/candidates/config-rsi-divergence-24pair-1h.json \
  --strategy-path .research/rsi/candidates \
  --strategy RSI_Divergence1h_EMA50Short_Freqtrade
```

The retained H-RSI-01 through H-RSI-07 evidence did not meet the robustness
screen. Production remains `SMC_FVG_Context30m_Freqtrade`; RSI is not a
replacement or a deployment-approved strategy.

Historical run transcripts preserve the original commands and paths so their
results remain auditable. New runs must use the `.research/rsi` paths above.
