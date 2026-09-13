# Research Runtime Integrity and Complete-Plan Research Design

## Goal

Make the SQLite/Pi research workflow trustworthy enough to choose a strategy and its strategy-specific exit plan without opaque source evidence, repeated out-of-sample selection, mutable identities, unbounded retries, or misleading approval state.

The research unit is a **complete trading plan**, not an entry signal: entry, protective stop, profit-taking, time/trailing/regime exits, exit precedence, sizing relation, cost assumptions, and falsifiers are researched and frozen together.

## Scope

This design covers:

- source visibility, immutable collector facts, append-only assessments, and claim-level evidence;
- provenance and support/contradiction integrity;
- complete plan fields in hypotheses and candidate manifests;
- durable hypothesis-ranking seals;
- OOS exposure consumption and a later three-family comparison cohort;
- candidate, experiment, and manifest identity checks;
- lease, retry, cycle-finalization, and approval invariants;
- migration of the existing SQLite database without deleting historical evidence.

It does not change current SMC/FVG entry thresholds or decide which strategy family wins. It does not start trading.

## Design principles

1. SQLite and hash-verified artifacts remain the source of truth.
2. Existing safe operation names and response fields remain compatible; new fields are additive.
3. A source assessment can describe evidence but cannot change collector facts.
4. A source supporting an entry claim does not automatically support a stop or exit claim.
5. A hypothesis is immutable after ranking is sealed.
6. Any conclusive OOS exposure consumes its partition, whether the verdict is PASS, WARN, or FAIL.
7. A retry is allowed only for a classified infrastructure failure before verified OOS output exists.
8. A failed candidate is terminal evidence, not permission to tune the same plan.
9. The runtime never starts dry-run, live trading, or a scheduler.

## Public runtime operations

Keep these operation names and current required fields:

- `start_or_resume_cycle`
- `load_context`
- `collect_sources`
- `record_source_assessment`
- `propose_hypothesis`
- `write_candidate`
- `start_validation`
- `record_interpretation`
- `finalize_cycle`

Add these bounded operations:

### `list_source_views`

```json
{
  "tool": "list_source_views",
  "payload": {
    "cycle_id": "C-...",
    "limit": 25,
    "after": "opaque-cursor"
  }
}
```

The response is deterministically ordered and contains at most 4,000 characters of excerpt per source:

- `source_id`, `provider`, `title`, `excerpt`, `canonical_url`, `doi`, `retrieved_at`;
- immutable collector metadata and its hash;
- current append-only assessment and assessment count;
- cycle observation identity;
- `next_cursor`.

Only sources observed by the requested cycle are returned. Source bodies are not copied into `load_context`.

### `seal_hypothesis_ranking`

```json
{
  "tool": "seal_hypothesis_ranking",
  "payload": {"cycle_id": "C-..."}
}
```

It persists a canonical ranking snapshot and SHA-256 identity. Repeating the call returns the same seal. The operation is legal only while the cycle is running, before candidate creation, and when every eligible hypothesis has a complete plan and valid evidence.

`write_candidate` remains compatible: if an old caller has not explicitly sealed, it invokes the same internal seal operation. It then accepts only the sealed rank-1 eligible hypothesis and never recomputes the ranking from mutable rows.

`propose_hypothesis` keeps its existing required fields and accepts additive `family_id`, `trading_plan`, and `evidence_links` fields. In an identity-bound production cycle, `trading_plan` and claim-level `evidence_links` are required for eligibility; legacy fixture callers may omit them but cannot create an approval-grade candidate.

### `create_evaluation_cohort`

This orchestrator/human operation is used only after each family candidate is frozen and before any comparison OOS result is exposed. It is not an autonomous agent shortcut. The request contains a cohort ID, exactly three candidate cycle/hypothesis identities, candidate/plan/dependency hashes, the common snapshot identity, comparison-OOS interval, sealed-holdout interval, and a canonical selection-rule JSON. The response contains the cohort manifest and hash. Every member must be registered before a member can validate against `COMPARISON_OOS`; the cohort owns that partition's consumption record. A cohort is sealed once and cannot add, replace, or reorder members.

## SQLite schema migration

Set `SCHEMA_VERSION = 3`. Apply the migration under `BEGIN IMMEDIATE`; run foreign-key and integrity checks before changing `PRAGMA user_version`.

### Immutable source facts and cycle observations

Retain the existing `sources` columns for compatibility. New records treat `metadata_json` as collector facts only. Add update/delete triggers.

Add:

```sql
CREATE TABLE cycle_sources (
  cycle_id TEXT NOT NULL REFERENCES cycles(id),
  source_id TEXT NOT NULL REFERENCES sources(id),
  observed_at TEXT NOT NULL,
  PRIMARY KEY (cycle_id, source_id)
);
```

The globally deduplicated canonical source may be observed in multiple cycles. `cycles.source_count` equals the number of its `cycle_sources` rows. A same-cycle duplicate is idempotent; a cross-cycle duplicate adds membership and a new observation identity.

### Append-only assessments

```sql
CREATE TABLE source_assessments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cycle_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  relevance TEXT,
  asset TEXT,
  timeframe TEXT,
  mechanism TEXT,
  assessment_json TEXT NOT NULL CHECK(json_valid(assessment_json)),
  actor TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (cycle_id, source_id)
    REFERENCES cycle_sources(cycle_id, source_id)
);
```

Add update/delete triggers. `record_source_assessment` inserts a row instead of mutating `sources.metadata_json`. The latest row by `(created_at, id)` is the effective assessment; all prior rows remain auditable. No assessment is accepted after ranking is sealed.

`full_text_available`, license, retrieval time, DOI, URL, and collector identity remain immutable facts. The agent cannot set or upgrade them.

### Evidence links

Rebuild the existing `hypothesis_sources` table under a compatible table name or migration bridge so its effective key is:

```text
(hypothesis_id, source_id)
```

Store one `stance` (`SUPPORT` or `CONTRADICT`), a note, and claim-level `evidence_json` per link. The same source cannot support and contradict the same hypothesis. Every link must reference a `cycle_sources` membership for the hypothesis's cycle and an effective assessment.

`evidence_json` has this shape for complete plans:

```json
{
  "roles": ["STOP_SUPPORT", "PROFIT_EXIT_SUPPORT"],
  "supported_claim": "A volatility-normalized stop is protective for this holding mechanism.",
  "transfer_assumption": "The source's asset and timeframe behavior transfers to crypto OHLCV.",
  "limitations": "The source does not establish an exact multiplier."
}
```

Allowed roles are `ENTRY_SUPPORT`, `STOP_SUPPORT`, `PROFIT_EXIT_SUPPORT`, `TIME_EXIT_SUPPORT`, `TRAILING_EXIT_SUPPORT`, `REGIME_EXIT_SUPPORT`, `SIZING_SUPPORT`, `CONTRADICTION`, and `FALSIFIER`. Entry-only evidence cannot satisfy an exit-evidence requirement.

### Hypothesis and plan identity

Add structured `family_id`, `plan_json`, and `plan_sha256` fields to hypotheses, plus nullable `approval_blocked_reason`. The service validates the plan schema instead of treating arbitrary metadata as a plan. A non-null approval-blocked reason prevents eligibility until a later fresh assessment clears the reason through a recorded, hash-linked reassessment; migration never clears it silently.

A complete `TradingPlanHypothesis` contains:

```text
schema_version
cycle_id / hypothesis_id / family_id
parent_identity
thesis / market_mechanism / market_scope
required_data: ["OHLCV"]
directions
execution_timeframe / informative_timeframes
entry_plan
exit_designs
sizing_plan
cost_model
evidence_map
development_protocol
outer_acceptance_policy
falsifiers
```

`entry_plan` specifies signal definition, confirmation, timestamp semantics, order/price assumption, validity window, duplicate-signal policy, and pre-fill invalidation.

Each `exit_design` specifies:

- a mandatory protective stop type and exact formula;
- profit exit type and formula, including `NONE` when absent;
- time exit, trailing exit, and regime exit, each explicit or `NONE`;
- exit precedence;
- gap behavior, stop update policy, and emergency behavior;
- exact constants and their parameter origin.

`R_MULTIPLE`, FVG stops, fixed percentages, ATR stops, time exits, trailing exits, and signal exits are all valid strategy-specific choices. None is universal.

`sizing_plan` declares the risk basis, risk budget, capital/notional caps, leverage rule, concurrent-risk limit, stop relation, fee/slippage allowances, minimum-order behavior, and precision behavior. Generic accounting checks the declaration; it does not replace the strategy's exit design.

### Ranking seal

Add to `cycles`:

```text
ranking_sealed_at TEXT NULL
ranking_json TEXT NULL CHECK(ranking_json IS NULL OR json_valid(ranking_json))
ranking_sha256 TEXT NULL
```

The canonical ranking includes every proposed hypothesis, deterministic order (`total_score DESC`, `created_at ASC`, `id ASC`), eligibility, plan hash, evidence hash, and the ranking algorithm version.

After sealing:

- source collection and assessments are rejected;
- new hypotheses and evidence links are rejected;
- scores and plan JSON cannot change;
- only the sealed rank-1 eligible hypothesis may write a candidate;
- ranking cannot be reopened.

### OOS exposure ledger

Add `oos_partitions_json` to experiments and an append-only consumption table:

```sql
CREATE TABLE oos_partition_consumptions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dataset TEXT NOT NULL,
  snapshot_sha256 TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('WFO_OOS', 'HOLDOUT', 'COMPARISON_OOS')),
  start_at TEXT NOT NULL,
  end_at TEXT NOT NULL,
  owner_id TEXT NOT NULL,
  cycle_id TEXT NOT NULL REFERENCES cycles(id),
  experiment_id TEXT NOT NULL REFERENCES experiments(id),
  run_id TEXT NOT NULL REFERENCES runs(id),
  verdict TEXT NOT NULL,
  consumed_at TEXT NOT NULL,
  CHECK(start_at < end_at),
  UNIQUE(snapshot_sha256, kind, start_at, end_at, owner_id)
);
```

Immutable triggers reject updates and deletes. Overlapping intervals on the same snapshot and partition kind are rejected unless they share one pre-registered comparison-cohort owner.

`start_validation` checks consumption **before** running a validator. A verified completed OOS result consumes each observed planned partition for PASS, WARN, or FAIL. A RETRYABLE error with no verified OOS output consumes nothing and may receive one bounded retry. Run insertion, consumption, hypothesis transition, and audit events are one transaction.

The existing `validation_windows` table remains a compatibility read source during migration but is not authoritative for new runs.

Add comparison-cohort registration tables:

```sql
CREATE TABLE comparison_cohorts (
  id TEXT PRIMARY KEY,
  dataset TEXT NOT NULL,
  snapshot_sha256 TEXT NOT NULL,
  comparison_start_at TEXT NOT NULL,
  comparison_end_at TEXT NOT NULL,
  holdout_start_at TEXT NOT NULL,
  holdout_end_at TEXT NOT NULL,
  selection_rule_json TEXT NOT NULL CHECK(json_valid(selection_rule_json)),
  manifest_sha256 TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('SEALED', 'SELECTED', 'CLOSED')),
  created_at TEXT NOT NULL,
  sealed_at TEXT NOT NULL,
  CHECK(comparison_start_at < comparison_end_at),
  CHECK(holdout_start_at < holdout_end_at)
);

CREATE TABLE comparison_cohort_members (
  cohort_id TEXT NOT NULL REFERENCES comparison_cohorts(id),
  cycle_id TEXT NOT NULL REFERENCES cycles(id),
  hypothesis_id TEXT NOT NULL REFERENCES hypotheses(id),
  candidate_sha256 TEXT NOT NULL,
  plan_sha256 TEXT NOT NULL,
  PRIMARY KEY(cohort_id, candidate_sha256),
  UNIQUE(cohort_id, cycle_id, hypothesis_id)
);
```

A `COMPARISON_OOS` consumption uses `owner_id=cohort_id`; members cannot be added or changed after the cohort is sealed. Only one member can later be selected for the sealed holdout.

## Cycle and approval invariants

Keep public statuses but enforce stages:

```text
COLLECTING -> SCORING -> RANKED -> CANDIDATE_FROZEN
           -> VALIDATING -> REVIEW -> DONE
```

`write_candidate` is illegal before `RANKED`; `start_validation` is illegal before `CANDIDATE_FROZEN`. `finalize_cycle` must reject a requested status that disagrees with the derived stage/latest run and must require an interpretation event for a completed research conclusion. `NEEDS_REVIEW` requires a linked, hash-verified PASS and an uncontaminated review bundle; a PASS maps to `NEEDS_REVIEW`, never directly to approval.

Every caller checks `acquired`. If `start_or_resume_cycle` returns `acquired=false`, it exits without launching an agent. Validation permits one normal attempt and one infrastructure retry; a second infrastructure failure becomes `INCONCLUSIVE`.

A `ReviewBundle` includes cycle/hypothesis/candidate/plan hashes, source and evidence identities, experiment identity, latest conclusive run, manifest/report hashes, OOS consumption, holdout state, and allowed review actions. Dashboard approval requires the same bundle and linked PASS manifest; a bare `NEEDS_REVIEW` row is insufficient.

## Candidate and experiment integrity

Candidate writing and validation require:

- exactly one concrete `IStrategy` class with the declared strategy name;
- AST policy version and rejection of subprocess, network, dynamic import, filesystem, SQL, environment, and external-data access;
- candidate source hash and dependency hash rechecked inside the validation boundary;
- parent, config, policy, snapshot, pair, timeframe, and detail identities derived or verified by the runtime;
- effective experiment metadata equal to the actual validator command;
- manifest plan hash equal to the frozen hypothesis plan hash.

The static policy is an accidental/obvious-violation guard, not a claim of a perfect Python sandbox. Candidate validation remains isolated and artifact-only.

## Complete-plan development protocol

Before any development result is exposed, the hypothesis stores:

- one entry design;
- at most two complete exit designs for that entry family;
- exact constants/formulas, not ranges;
- source claim roles and transfer assumptions;
- development windows, selector, tie-breaker, and attempt limit;
- cost model and risk acceptance thresholds.

The agent evaluates each design once on identical development folds, selects with a frozen lexicographic rule, and freezes the complete selected plan and code hash. After outer OOS begins, no plan field, parameter, exit component, or implementation may change.

A design is rejected for failing correctness/safety or non-positive stressed development return. Among survivors, prefer conservative return-to-drawdown; practical ties prefer fewer components, lower cost burden, and fewer fitted values. No closest failure is tuned.

## Three-family comparison protocol

The one-candidate-per-cycle budget remains. A later comparison uses three separate candidate cycles:

1. Build one frozen complete plan per family using development data only.
2. Before viewing any comparison result, register a cohort containing all three candidate hashes, dependency/config/policy/snapshot identities, a common comparison OOS partition, a deterministic selection rule, and a sealed holdout partition.
3. Run each cohort member once against the same comparison OOS. The partition is consumed by the cohort, not individually reused.
4. Select at most one winner using the predeclared rule. The comparison OOS is selection data and cannot approve the winner.
5. Run only the frozen winner once on the sealed holdout. Any post-holdout change invalidates that result.
6. Approve only from the final holdout review bundle. If none passes, select none.

The cohort registration is an orchestrator/human operation, not an autonomous agent shortcut. It is not permitted to expose one member's outer result before all members are frozen and registered.

## Acceptance metrics

Every complete-plan manifest reports, per fold and aggregate:

- stressed net profit, drawdown, trades, fees, slippage, turnover, time in market;
- planned loss, net realized R, loss-overrun p95, concurrent planned risk;
- holding duration and exit counts by `PROTECTIVE_STOP`, `PROFIT_TARGET`, `TIME_EXIT`, `TRAILING_EXIT`, `REGIME_EXIT`, `SIGNAL_EXIT`, `EMERGENCY_EXIT`, and `LIQUIDATION`;
- MAE/MFE diagnostics, cost burden, fold stability, bootstrap p05 profit and p95 drawdown;
- source/plan/candidate/config/policy/snapshot identities and OOS consumption.

Hard gates are fixed before development:

- lookahead and recursive checks pass;
- plan/candidate/dependency hashes match;
- all required folds exist;
- risk-ledger coverage is 100%;
- wrong-side or missing initial stops are zero;
- missing exit plans, liquidation events, and unexplained emergency exits are zero;
- aggregate stressed profit is positive;
- at least two of three folds are positive;
- aggregate OOS trades meet the policy floor;
- fold and bootstrap drawdown remain within policy;
- bootstrap p05 net profit is non-negative when the policy says the sample is gate-eligible;
- attribution is not dominated by one pair or unintended branch.

Strategy families are compared by a frozen lexicographic rule: hard gates first, then conservative return-to-drawdown, then risk efficiency and loss-overrun, then drawdown/cost burden/simplicity for practical ties. Win rate alone cannot select a winner.

## Migration and legacy evidence

The quarantine table preserves unverifiable legacy links without deleting them:

```sql
CREATE TABLE legacy_evidence_quarantine (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  hypothesis_id TEXT,
  source_id TEXT,
  legacy_stance TEXT,
  legacy_note TEXT,
  reason TEXT NOT NULL,
  original_row_json TEXT NOT NULL CHECK(json_valid(original_row_json)),
  original_sha256 TEXT NOT NULL,
  quarantined_at TEXT NOT NULL
);
```

The v2→v3 migration:

1. creates additive tables/columns and backfills `cycle_sources` from `sources.cycle_id`;
2. adds nullable `hypotheses.approval_blocked_reason` and the quarantine table;
3. validates and backfills same-cycle non-overlapping evidence;
4. quarantines overlapping, cross-cycle, unknown, or otherwise unverifiable legacy links with the original row JSON and SHA-256;
5. marks affected hypotheses with `approval_blocked_reason`;
6. preserves historical thesis, scores, candidates, runs, manifests, and artifacts unchanged;
7. marks legacy PASS windows as coarse research-only consumption when exact folds cannot be recovered;
8. installs immutable/provenance triggers;
9. records one migration audit event with counts and hashes;
10. fails closed on integrity errors before completing the schema upgrade.

Quarantined evidence remains visible to audit but cannot satisfy eligibility, ranking seals, candidate creation, or dry-run approval. A later fresh assessment may attach a source correctly without deleting the quarantine record.

## Verification

Focused tests must prove:

- source content is visible and bounded;
- collector facts cannot be forged through assessment;
- assessments are append-only;
- cross-cycle reuse creates membership rather than a provenance failure;
- support/contradiction overlap is rejected;
- ranking seal freezes score, plan, and evidence;
- candidates cannot be written before a seal or from a non-winner;
- every conclusive OOS verdict consumes its partition before another run;
- pre-run contamination blocking works;
- comparison-cohort registration freezes all candidates before exposure;
- candidate/dependency and experiment metadata are rechecked at validation;
- `acquired=false`, retry limits, and finalization invariants are enforced;
- dashboard approval requires the exact linked PASS review bundle;
- migration quarantines unsafe legacy evidence without deleting it.

No performance result from the existing snapshot is promoted by this design. A fresh dataset and sealed holdout are required for strategy-family selection.

## Out of scope

- changing SMC/FVG entry thresholds or choosing a winning family;
- universal SL/TP, universal 1R, or universal trailing behavior;
- hyperopt, parameter grids, post-OOS tuning, or real WFO fitting;
- new providers, TradingView automation, distributed workers, or a job queue;
- dashboard redesign;
- exchange-side stop deployment and live operational reconciliation;
- retrofitting incomplete legacy manifests into approval-grade results.
