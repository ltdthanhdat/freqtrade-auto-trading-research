# Bounded strategy research cycle

Run exactly one bounded strategy research cycle through `strategy_research_runtime` for `cycle_id={{CYCLE_ID}}`.

The supervisor already acquired this cycle lease. Use the prepared identity below:

{{VALIDATION_CONTEXT}}

Use only the `strategy_research_runtime` tool for this cycle. Do not call
`start_or_resume_cycle`; first call `load_context` and the bounded
`list_source_views` operation before reasoning. Do not include `hypothesis_id`
in a `propose_hypothesis` payload. Do not use shell, SQL, arbitrary
file writes, automated TradingView acquisition, Freqtrade trade commands,
dry-run, live worker, promotion, or changes to the parent strategy, config,
policy, or snapshot.

## Sources and assessments

Collect a bounded set of sources from the supported providers. Reuse existing
current-cycle assessments and assess only sources missing a structured
assessment. Prefer only openalex, arxiv, and crossref, with at most four
results per provider. do not use semantic_scholar. The `collect_sources` payload
is exactly `{cycle_id, provider, query, limit}`: use integer `limit`,
not `max_results`. A provider HTTP 429 is recorded by the runtime; do not loop
on that provider. If one provider returns a retryable error, record it and
continue with another provider. Keep collector facts, including
`full_text_available`, immutable.

The `record_source_assessment` payload is exactly
`{cycle_id, source_id, assessment: {relevance, asset, timeframe, mechanism}}`.
For `relevance`, use exactly one of `direct`, `directly_relevant`, `relevant`,
`indirect`, `contradicting`, `falsifier`, or `irrelevant`; do not invent labels
such as `adjacent` or `unknown`. Assess source quality without changing
collector facts. Use claim-level
provenance for every source used by a hypothesis.

## Hypotheses and plans

Propose at most three distinct hypotheses. The `propose_hypothesis` payload
fields are top-level: `cycle_id`, `thesis`, `mechanism`, `market_scope`,
`required_data`, `falsifier`, `scores`, `supporting_source_ids`,
`contradicting_source_ids`, `trading_plan`, and `evidence_links`. Use
`required_data` exactly `["OHLCV"]`; unsupported data stays in backlog. Do not
put plan fields at the top level.

Every identity-bound hypothesis needs a complete frozen trading plan with
`schema_version=1`, `required_data=["OHLCV"]`, and `entry_plan` and `sizing_plan`
fields including: `signal_definition`, `confirmation`,
`timestamp_semantics`, `order_assumption`, `validity_window`, and non-empty
`sizing_plan`,
`duplicate_signal_policy`, and `pre_fill_invalidation`; one or two exact
`exit_designs`; non-empty `sizing_plan`, `cost_model`,
`development_protocol`, and `outer_acceptance_policy`; falsifiers; and an
`evidence_map` covering `entry`, `stop`, and `profit_exit`.

Each exit design object must include a non-empty `name`. It is a complete exit
specification and must specify `protective_stop`, `profit_exit`, `time_exit`,
`trailing_exit`, `regime_exit`, `exit_precedence`, `gap_behavior`,
`stop_update_policy`, and `emergency_behavior`. Each component `type` must be
one of the exact uppercase values `ATR`, `FIXED_PERCENT`, `FVG_ABSOLUTE`,
`REGIME`, `R_MULTIPLE`, `SIGNAL`, `TIME`, `TRAILING`, or `NONE`; every
non-`NONE` component also needs a non-empty `formula`. The `exit_precedence`
list may contain only the exact uppercase values `PROTECTIVE_STOP`,
`PROFIT_TARGET`, `TIME_EXIT`, `TRAILING_EXIT`, `REGIME_EXIT`, `SIGNAL_EXIT`,
`EMERGENCY_EXIT`, or `LIQUIDATION`. `gap_behavior`, `stop_update_policy`, and
`emergency_behavior` must be non-empty text strings, not nested objects. Use
explicit `type: NONE` when a component is absent, and never use ranges. Do not
cite entry evidence as proof of stop or profit claims.

Use `supporting_source_ids` and `contradicting_source_ids` only from this
cycle, with no overlap. For an identity-bound cycle, both
`supporting_source_ids` and `contradicting_source_ids` must be non-empty; if
necessary, collect and assess a source that challenges the hypothesis. The
`evidence_links` list must cover every cited source exactly once. Each link is
`{source_id, stance, note, evidence}`, where `evidence` is exactly an object
with `roles` (a list), `supported_claim`, `transfer_assumption`, and
`limitations`; do not wrap these fields in an `items` object. Supporting links
must cover `ENTRY_SUPPORT`, `STOP_SUPPORT`, and `PROFIT_EXIT_SUPPORT`; use
role-specific claim-level evidence. A contradicting link must use
`CONTRADICTION` or `FALSIFIER`. If complete claim-level evidence is
unavailable, do not create a candidate.

## Candidate and validation

After proposals, call `seal_hypothesis_ranking`. Write exactly one
AST-policy-v1-safe candidate for the sealed highest-scoring eligible rank-1
hypothesis with `write_candidate`; it must contain one class named
`strategy_name` inheriting `IStrategy`. Do not write a second candidate, tune a
candidate, expand pairs, or run parameter sweeps. Do not run a parameter sweep. Do not call
`create_evaluation_cohort`: this cycle has one candidate budget and no
three-member comparison cohort.

Call `start_validation` exactly once for that candidate with the fixed
experiment identity below, `wfo=true`, the listed `WFO_OOS` partitions, and
`timeframe_detail='1m'`. Its payload is exactly
`{cycle_id, hypothesis_id, experiment: {id, parent_strategy, parent_sha256,
changed_variable, config_path, config_sha256, pairs, timeframes,
timeframe_detail, snapshot_path, snapshot_sha256, policy_path, policy_sha256,
strategy_name, strategy_path, strategy_file, start_at, end_at, runs_dir,
artifact_root, wfo, oos_partitions}}`; all experiment fields are nested under
`experiment`, with no `max_results` or other unknown fields. Use parent
strategy `SMC_FVG_Context30m_Freqtrade`. Use parent strategy
'SMC_FVG_Context30m_Freqtrade'.

The sealed holdout is the cycle's recorded holdout interval. Never use it in
development, OOS validation, tuning, or selection. never use it in development, OOS validation, tuning, or selection. WFO and OOS evidence must be consumed exactly once by the runtime. WFO/OOS consumption is exactly once. Record the returned interpretation
with `record_interpretation` and call `finalize_cycle` with the
runtime-required terminal status. A PASS remains `NEEDS_REVIEW` and never
authorizes trading. Stop after finalization; there is no post-OOS tuning. There is no automatic promotion.

The runtime owns state, artifacts, validation commands, and retry limits. The
prompt is not a safety boundary: if identity, plan, evidence, candidate
contract, artifacts, or approval is missing, fail closed and do not claim a
result. Do not start any worker, demo, live, dry-run, or trading process.
