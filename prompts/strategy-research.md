# Bounded strategy research cycle

Use only the `strategy_research_runtime` tool for this cycle. Do not use shell,
SQL, arbitrary file writes, or automated TradingView acquisition.

1. The `research-data` preflight has already seeded and checked the snapshot.
   Use its reported datadir and timerange; do not silently switch datasets.
   Call `start_or_resume_cycle`, then `load_context`.
2. Collect a bounded set of sources from the supported providers. Keep source
   provenance, retrieval time, and contradictions; do not retry a provider more
   than the runtime allows.
3. Assess source quality and propose no more than three structured hypotheses.
   One hypothesis contains one mechanism or market assumption, explicit OHLCV
   inputs, executable rules, and a falsifier. Unsupported data stays backlog.
4. Implement only the highest-scoring eligible hypothesis with `write_candidate`.
   Never tune a failed candidate or run a parameter sweep.
5. Call `start_validation` exactly once for that candidate. The runtime runs the
   frozen correctness, walk-forward, stress, and bootstrap checks.
6. Record a concise interpretation with `record_interpretation`, then call
   `finalize_cycle` with the resulting status. Stop at `NEEDS_REVIEW`,
   `INCONCLUSIVE`, `REJECTED`, `INCOMPLETE`, or `FAILED`.

The runtime owns state, artifacts, validation commands, and retry limits. Do not
start any trading process or alter the parent strategy, configuration, snapshot,
or validation policy during the cycle.
