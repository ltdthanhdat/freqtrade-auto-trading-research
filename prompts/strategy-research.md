# Bounded strategy research cycle

Use only the `strategy_research_runtime` tool for this cycle. Do not use shell,
SQL, arbitrary file writes, or automated TradingView acquisition.

1. The `research-data` preflight has already seeded and checked the snapshot.
   Use its reported datadir and timerange; do not silently switch datasets.
   Call `start_or_resume_cycle`, then `load_context` and the bounded
   `list_source_views` operation before reasoning.
2. Collect a bounded set of sources from the supported providers. Keep source
   provenance, retrieval time, and contradictions; do not retry a provider more
   than the runtime allows. Prefer only `openalex`, `arxiv`, and `crossref`,
   with at most four results per provider; if one returns a retryable error,
   record it and continue with another provider. Treat `full_text_available`
   and all collector metadata as immutable facts: never self-attest or alter
   them. Do not use shell, SQL, arbitrary file writes, or TradingView.
3. Assess source quality and propose no more than three structured hypotheses.
   Each hypothesis is one complete frozen trading plan: `entry_plan`, exact
   `exit_designs` with protective stop, profit, time, trailing, and regime
   components (use explicit `type: NONE` when absent), exit precedence,
   `sizing_plan`, `cost_model`, `development_protocol`,
   `outer_acceptance_policy`, falsifiers, and role-specific claim-level
   evidence for entry, stop, and each exit. Use `required_data` exactly `["OHLCV"]`;
   unsupported data stays backlog.
4. Seal the ranking with `seal_hypothesis_ranking`. Implement only the
   highest-scoring eligible hypothesis with `write_candidate`; write at most
   one candidate. Never tune a failed candidate, run a parameter sweep, or
   perform post-OOS tuning; the plan is frozen once OOS begins.
5. Call `start_validation` exactly once for that candidate. The runtime runs the
   frozen correctness, expanding-window frozen-candidate OOS, stress, bootstrap,
   and complete-plan risk/exit evidence checks. Record and consume every
   conclusive OOS partition; do not use comparison OOS until a sealed cohort
   contains all three family candidates, and only its selected winner may use
   the sealed holdout.
6. Record a concise interpretation with `record_interpretation`, then call
   `finalize_cycle` with the resulting status. Stop at `NEEDS_REVIEW`,
   `INCONCLUSIVE`, `REJECTED`, `INCOMPLETE`, or `FAILED`. There is no automatic promotion;
   do not start dry-run or live trading.

The runtime owns state, artifacts, validation commands, and retry limits. Do not
start any trading process or alter the parent strategy, configuration, snapshot,
or validation policy during the cycle.
