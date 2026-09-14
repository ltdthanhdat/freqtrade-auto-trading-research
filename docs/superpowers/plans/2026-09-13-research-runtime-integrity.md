# Research Runtime Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the SQLite/Pi research workflow so source-grounded complete trading plans, candidate identities, OOS exposure, and review state are trustworthy and leakage-resistant.

**Architecture:** Extend the existing standard-library SQLite runtime in place with an additive schema-v3 compatibility bridge. Keep the current public runtime operation names and response fields, add bounded source/ranking/cohort operations, and move mutable analyst assessments, plan identity, and OOS consumption into append-only or transactionally enforced structures. Candidate generation and validation remain cycle-scoped and research-only.

**Tech Stack:** Python 3.11, SQLite, JSON-lines runtime, existing Freqtrade validation scripts, pytest, Node TypeScript contract tests, SHA-256 artifacts.

**Spec:** `docs/superpowers/specs/2026-09-13-research-runtime-integrity-design.md`

## Global Constraints

- SQLite `user_data/research.sqlite` and hash-verified artifacts remain the source of truth.
- Existing safe runtime operation names and response fields remain compatible; new fields are additive.
- A hypothesis is a complete trading plan: entry, protective stop, profit/time/trailing/regime exits, precedence, sizing, costs, evidence, and falsifiers.
- `required_data` for an identity-bound cycle is exactly `["OHLCV"]`.
- A cycle admits at most 100 source observations, 3 hypotheses, and 1 candidate.
- A conclusive OOS result consumes its partition for PASS, WARN, and FAIL.
- Only a classified infrastructure failure before verified OOS output may be retried, at most once.
- No parameter sweep, post-OOS tuning, dry-run, live trading, or automatic promotion.
- Existing validation thresholds are not weakened to rescue an existing candidate.
- Historical evidence is preserved; unverifiable legacy evidence is quarantined and cannot approve a candidate.
- Do not stage or overwrite the pre-existing working-tree changes in `Makefile`, `README.md`, `compose.yaml`, `scripts/research_loop.py`, `.dockerignore`, `Dockerfile.research`, or existing tests.

---

### Task 1: Add pure complete-plan validation

**Files:**
- Create: `research_runtime/plan.py`
- Modify: `research_runtime/core.py`
- Create: `tests/test_research_plan.py`

**Interfaces:**
- Produces `validate_trading_plan(value: object, *, identity_bound: bool) -> dict[str, object]`.
- Produces `canonical_plan_json(value: Mapping[str, object]) -> str`.
- Produces `plan_sha256(value: Mapping[str, object]) -> str`.
- Produces `validate_evidence_link(value: object) -> dict[str, object]`.
- Consumes the enum/state conventions in `research_runtime/core.py`.

- [ ] **Step 1: Write the failing plan-schema tests.**

  Add tests for one valid plan containing `entry_plan`, two explicit `exit_designs`, `sizing_plan`, `cost_model`, `development_protocol`, `outer_acceptance_policy`, and `falsifiers`. Assert canonical JSON has stable key ordering and that the same plan hashes identically.

  Add separate tests that reject a missing protective stop, omitted optional exit instead of explicit `type: "NONE"`, a parameter range, `required_data` other than `["OHLCV"]` in an identity-bound plan, an empty falsifier, and an exit design with no claim-level evidence role.

- [ ] **Step 2: Run the focused tests and verify the expected RED failure.**

  Run:

  ```bash
  uv run pytest tests/test_research_plan.py -q
  ```

  Expected: collection or assertion failures because `research_runtime.plan` does not yet exist.

- [ ] **Step 3: Implement the smallest strict validator.**

  Implement enums and required-key checks for the plan shapes in the spec. Reject numeric ranges and missing explicit `NONE` exit components. Preserve unknown provider-specific metadata only under a bounded `metadata` object; do not let it replace required fields. Canonicalize with the existing `canonical_json` helper and hash the canonical text.

- [ ] **Step 4: Run the focused tests and verify GREEN.**

  Run the same pytest command and require all plan tests to pass.

- [ ] **Step 5: Commit the isolated plan contract.**

  ```bash
  git add research_runtime/plan.py research_runtime/core.py tests/test_research_plan.py
  git commit -m "feat: validate complete trading plan hypotheses"
  ```

### Task 2: Introduce schema-v3 tables and safe migration

**Files:**
- Modify: `research_runtime/store.py`
- Modify: `tests/test_research_store.py`
- Modify: `tests/test_research_migration.py`

**Interfaces:**
- Produces `SCHEMA_VERSION = 3` and an idempotent v2-to-v3 migration.
- Produces `ResearchStore.integrity_report() -> dict[str, object]` unchanged in shape.
- Produces source membership and quarantine methods used by later service tasks.
- Preserves v1/v2 database creation and migration behavior.

- [ ] **Step 1: Write failing schema and migration tests.**

  Update the fresh-store test to require `user_version == 3`, `cycle_sources`, `source_assessments`, `legacy_evidence_quarantine`, `comparison_cohorts`, `comparison_cohort_members`, and `oos_partition_consumptions`. Require `hypotheses.approval_blocked_reason`, `hypotheses.family_id`, `hypotheses.plan_json`, `hypotheses.plan_sha256`, `cycles.ranking_sealed_at`, `cycles.ranking_json`, `cycles.ranking_sha256`, and `experiments.oos_partitions_json`.

  Build a v2 fixture database with one valid link, one support/contradiction overlap, and one cross-cycle link. Assert migration preserves the source, hypothesis, run, and artifact identity; valid links are backfilled; invalid links are copied to quarantine with original JSON and SHA-256; affected hypotheses receive `approval_blocked_reason`; and no legacy row is silently assigned a stance.

  Add tests that direct updates/deletes to `sources`, `source_assessments`, `legacy_evidence_quarantine`, and `oos_partition_consumptions` fail with a database error, while same-cycle source observation is idempotent.

- [ ] **Step 2: Run the focused tests and verify RED.**

  ```bash
  uv run pytest tests/test_research_store.py tests/test_research_migration.py -q
  ```

  Expected: failures for the missing schema-v3 objects and migration behavior.

- [ ] **Step 3: Implement the additive migration.**

  Split migration code into `_migrate_v1` and `_migrate_v2`. Add the schema objects and immutable triggers under `BEGIN IMMEDIATE`. Backfill `cycle_sources` from each legacy `sources.cycle_id`. Rebuild or bridge `hypothesis_sources` with effective key `(hypothesis_id, source_id)`; quarantine overlap, cross-cycle, unknown, and malformed links. Add the quarantine table with `original_row_json`, `original_sha256`, `reason`, and timestamps. Keep historical rows and mark legacy PASS windows as coarse research-only consumption when exact folds are unavailable.

  Do not clear `approval_blocked_reason` during migration. Run `PRAGMA foreign_key_check` and `PRAGMA integrity_check`; raise before setting `user_version=3` if either fails.

- [ ] **Step 4: Run the focused tests and verify GREEN.**

  ```bash
  uv run pytest tests/test_research_store.py tests/test_research_migration.py -q
  ```

  Require the fresh schema, upgrade fixture, trigger, and preservation tests to pass.

- [ ] **Step 5: Commit the schema bridge.**

  ```bash
  git add research_runtime/store.py tests/test_research_store.py tests/test_research_migration.py
  git commit -m "fix: migrate research state with provenance quarantine"
  ```

### Task 3: Make source observations and assessments observable and immutable

**Files:**
- Modify: `research_runtime/store.py`
- Modify: `research_runtime/service.py`
- Modify: `research_runtime/collectors.py` only if collector metadata needs a normalized immutable fact field
- Modify: `tests/test_research_service.py`
- Modify: `tests/test_research_collectors.py`

**Interfaces:**
- Produces `ResearchStore.list_source_views(cycle_id: str, limit: int = 25, after: str | None = None) -> dict[str, object]`.
- Adds runtime operation `list_source_views` with required `cycle_id` and optional `limit`/`after`.
- Changes `record_source_assessment` to append `source_assessments` and keep `sources.metadata_json` immutable.
- Keeps `collect_sources` response keys `accepted_ids`, `duplicate_ids`, and `provider_errors`, with additive `sources` views.

- [ ] **Step 1: Write failing source-view and assessment tests.**

  Assert a duplicate source collected in a second cycle creates a `cycle_sources` membership and appears in that cycle's bounded view. Assert views include title, excerpt truncated at 4,000 characters, URL/DOI, provider, immutable collector metadata/hash, effective assessment, assessment count, and cursor. Assert a source from another cycle is never returned.

  Assert `record_source_assessment` creates an append-only assessment row, rejects `full_text`, `full_text_available`, DOI, URL, license, and retrieval-time mutations, and rejects assessment after ranking seal. Assert structured identity-bound assessments require `relevance`, `asset`, `timeframe`, and `mechanism`.

- [ ] **Step 2: Run the focused tests and verify RED.**

  ```bash
  uv run pytest tests/test_research_service.py tests/test_research_collectors.py -q
  ```

  Expected: failures because source membership, source views, and append-only assessments are absent.

- [ ] **Step 3: Implement source membership and bounded views.**

  Make `insert_source` preserve global canonical deduplication but insert a `cycle_sources` row for both new and cross-cycle duplicate observations. Recompute the cycle count from memberships. Implement stable `(observed_at, source_id)` cursor pagination and return collector facts separately from the newest assessment.

  Replace `update_source_metadata` calls from the service with `insert_source_assessment`. Keep the old method only as a rejecting compatibility shim so no caller can mutate facts. Strip or reject immutable fact keys from agent assessments.

- [ ] **Step 4: Add the typed runtime operation and run focused tests.**

  Add `list_source_views` to `ResearchService.OPERATION_FIELDS`, required fields, and `call()`. Ensure all source IDs used by a hypothesis are validated through `cycle_sources`, not the legacy `sources.cycle_id`. Run the focused tests and require GREEN.

- [ ] **Step 5: Commit source evidence hardening.**

  ```bash
  git add research_runtime/store.py research_runtime/service.py research_runtime/collectors.py tests/test_research_service.py tests/test_research_collectors.py
  git commit -m "fix: expose immutable source evidence to research"
  ```

### Task 4: Enforce claim-level evidence and complete-plan hypotheses

**Files:**
- Modify: `research_runtime/service.py`
- Modify: `research_runtime/store.py`
- Modify: `tests/test_research_service.py`
- Modify: `tests/test_research_store.py`

**Interfaces:**
- Extends `propose_hypothesis` with optional `family_id`, `trading_plan`, and `evidence_links`; identity-bound candidates require them.
- Produces `ResearchStore.add_hypothesis_source(..., evidence: dict[str, object] | None = None) -> None` with one stance per `(hypothesis_id, source_id)`.
- Produces `_has_candidate_evidence()` that checks exit-role coverage, not only generic support.

- [ ] **Step 1: Write failing provenance and claim-role tests.**

  Add tests rejecting duplicate source IDs, a support/contradiction intersection, a source not observed by the cycle, and opposite stances for the same hypothesis/source. Add a valid complete-plan proposal with `ENTRY_SUPPORT`, `STOP_SUPPORT`, and `PROFIT_EXIT_SUPPORT`; assert it is eligible only with a distinct contradiction/falsifier link.

  Add tests proving entry-only support cannot authorize a candidate whose plan has a stop and profit exit, and that an `approval_blocked_reason` makes a hypothesis ineligible until a new hash-linked reassessment is recorded.

- [ ] **Step 2: Run the focused tests and verify RED.**

  ```bash
  uv run pytest tests/test_research_service.py tests/test_research_store.py -q
  ```

  Expected: failures for overlap, plan fields, and exit-role evidence checks.

- [ ] **Step 3: Implement atomic proposal validation.**

  Validate plan JSON with `research_runtime.plan`, normalize support/contradiction IDs to sets, reject intersection, verify membership and effective assessments, and insert the hypothesis plus all evidence links in one transaction. Rework duplicate-mechanism handling to attach new evidence atomically without changing frozen fields. Do not allow proposal or evidence mutation after ranking seal.

- [ ] **Step 4: Run focused tests and verify GREEN.**

  ```bash
  uv run pytest tests/test_research_service.py tests/test_research_store.py -q
  ```

  Require all new and existing safe proposal tests to pass.

- [ ] **Step 5: Commit claim-level hypothesis evidence.**

  ```bash
  git add research_runtime/service.py research_runtime/store.py tests/test_research_service.py tests/test_research_store.py
  git commit -m "fix: require claim-level evidence for research candidates"
  ```

### Task 5: Seal ranking and couple cycle stages to evidence

**Files:**
- Modify: `research_runtime/core.py`
- Modify: `research_runtime/store.py`
- Modify: `research_runtime/service.py`
- Modify: `tests/test_research_core.py`
- Modify: `tests/test_research_store.py`
- Modify: `tests/test_research_service.py`

**Interfaces:**
- Produces `ResearchStore.seal_hypothesis_ranking(cycle_id: str) -> dict[str, object]`.
- Adds runtime operation `seal_hypothesis_ranking` with required `cycle_id`.
- Extends `load_context` additively with `ranking_sealed`, `ranking_sha256`, and source-view availability.
- Keeps `write_candidate` backward-compatible by auto-sealing once, then requiring sealed rank 1.

- [ ] **Step 1: Write failing ranking/stage/finalization tests.**

  Assert ranking order is score descending, creation time ascending, then ID ascending. Assert the persisted ranking includes all hypotheses, eligibility, plan hash, evidence hash, and version. Assert a second seal is idempotent and any post-seal proposal, assessment, source collection, score/plan change, or evidence-link change fails.

  Assert `write_candidate` cannot select rank 2, a hypothesis without a complete plan, or a hypothesis after ranking was changed. Assert `write_candidate` auto-seals for a legacy safe caller and still leaves a durable seal.

  Assert `finalize_cycle` rejects `NEEDS_REVIEW` without a linked PASS run and interpretation, rejects a requested status inconsistent with the latest run, and retains the legal terminal transition tests.

- [ ] **Step 2: Run the focused tests and verify RED.**

  ```bash
  uv run pytest tests/test_research_core.py tests/test_research_store.py tests/test_research_service.py -q
  ```

  Expected: failures for seal persistence and stage/result coupling.

- [ ] **Step 3: Implement the ranking seal and stage guards.**

  Add the cycle seal columns and canonical ranking hash. Make seal and eligibility calculation one transaction. Enforce stage transitions `COLLECTING -> SCORING -> RANKED -> CANDIDATE_FROZEN -> VALIDATING -> REVIEW -> DONE` while retaining public cycle statuses. Derive finalization legality from the latest linked run, hypothesis state, and an interpretation event. Build a bounded internal `ReviewBundle` containing all identity and review fields.

- [ ] **Step 4: Run focused tests and verify GREEN.**

  ```bash
  uv run pytest tests/test_research_core.py tests/test_research_store.py tests/test_research_service.py -q
  ```

- [ ] **Step 5: Commit ranking and stage integrity.**

  ```bash
  git add research_runtime/core.py research_runtime/store.py research_runtime/service.py tests/test_research_core.py tests/test_research_store.py tests/test_research_service.py
  git commit -m "fix: seal research ranking before candidate generation"
  ```

### Task 6: Enforce OOS exposure consumption and bounded retries

**Files:**
- Modify: `research_runtime/store.py`
- Modify: `research_runtime/service.py`
- Modify: `research_runtime/validation.py`
- Modify: `scripts/validate_baseline.py` only for manifest partition fields if missing
- Modify: `tests/test_research_service.py`
- Modify: `tests/test_research_validation.py`
- Modify: `tests/test_validation_manifest.py`

**Interfaces:**
- Produces `ResearchStore.is_partition_consumed(...) -> bool`.
- Produces `ResearchStore.consume_partitions(...) -> None`, transactionally linked to run identity.
- Extends experiment identity with `oos_partitions_json` and `owner_id`/cohort identity.
- `start_validation` rejects consumed/overlapping partitions before invoking the validator and allows one infrastructure retry only.

- [ ] **Step 1: Write failing ledger and retry tests.**

  Use fake validators that return a manifest with explicit OOS fold intervals. Assert PASS, WARN, and FAIL each consume intervals and a second validation is rejected before the fake validator is called. Assert a RETRYABLE exception with no manifest creates one append-only attempt without consumption; a second such attempt returns `INCONCLUSIVE` and is not retried.

  Assert overlapping intervals on the same snapshot are rejected, non-overlapping intervals are accepted, and a pre-registered comparison cohort is the only owner allowed to share its comparison partition.

- [ ] **Step 2: Run the focused tests and verify RED.**

  ```bash
  uv run pytest tests/test_research_service.py tests/test_research_validation.py tests/test_validation_manifest.py -q
  ```

- [ ] **Step 3: Implement pre-run checks and atomic consumption.**

  Parse verified fold intervals from the validator manifest. Before validation, require identity-bound experiments to contain a non-empty OOS plan and check the immutable ledger. After a conclusive result, insert the run, consume observed intervals, append the hypothesis transition/event, and update cycle stage in one database transaction. Keep legacy fixture validators without production identity compatible but research-only.

  Add a per-experiment attempt count. Classify only infrastructure failures with no verified OOS output as retryable; after the second, transition to `INCONCLUSIVE` and preserve both run rows.

- [ ] **Step 4: Run focused tests and verify GREEN.**

  ```bash
  uv run pytest tests/test_research_service.py tests/test_research_validation.py tests/test_validation_manifest.py -q
  ```

- [ ] **Step 5: Commit OOS ledger enforcement.**

  ```bash
  git add research_runtime/store.py research_runtime/service.py research_runtime/validation.py scripts/validate_baseline.py tests/test_research_service.py tests/test_research_validation.py tests/test_validation_manifest.py
  git commit -m "fix: consume every conclusive research OOS partition"
  ```

### Task 7: Harden candidate and experiment identity at the validation boundary

**Files:**
- Modify: `research_runtime/candidates.py`
- Modify: `research_runtime/validation.py`
- Modify: `research_runtime/service.py`
- Modify: `tests/test_research_candidates.py`
- Modify: `tests/test_research_validation.py`

**Interfaces:**
- Produces `validate_candidate_source(source: str, strategy_name: str, *, identity_bound: bool) -> ast.Module`.
- Extends `CandidateIdentity` with `candidate_sha256`, AST policy version, class identity, and dependency hash fields while preserving existing path/hash/name access.
- Rechecks candidate source hash and dependency identity inside `validate_candidate()` immediately before the runner call.

- [ ] **Step 1: Write failing candidate-boundary tests.**

  Add rejected fixtures importing `subprocess`, `socket`, `requests`, `sqlite3`, `os`, `pathlib`, using dynamic imports, environment access, filesystem writes, or `eval/exec`. Add a valid Freqtrade candidate fixture with one `IStrategy` class and an invalid fixture with no `IStrategy` base.

  Add a mutation test that changes the candidate after the service precheck but before validation's identity check; assert validation raises an identity error and the runner is not called. Add experiment metadata mismatch tests for pairs, timeframe, detail, and strategy path.

- [ ] **Step 2: Run the focused tests and verify RED.**

  ```bash
  uv run pytest tests/test_research_candidates.py tests/test_research_validation.py -q
  ```

- [ ] **Step 3: Implement static policy and boundary rechecks.**

  Add a versioned AST allow/deny policy that rejects process/network/filesystem/SQL/dynamic-import access and requires one concrete `IStrategy` class for identity-bound candidates. Retain a narrow fixture-only path for existing unit tests that intentionally use a plain class. Rehash the candidate source and all local strategy dependencies inside `validate_candidate`, derive effective experiment identity from config/policy/snapshot, and compare every recorded field with the command namespace before execution.

- [ ] **Step 4: Run focused tests and verify GREEN.**

  ```bash
  uv run pytest tests/test_research_candidates.py tests/test_research_validation.py -q
  ```

- [ ] **Step 5: Commit candidate-boundary hardening.**

  ```bash
  git add research_runtime/candidates.py research_runtime/validation.py research_runtime/service.py tests/test_research_candidates.py tests/test_research_validation.py
  git commit -m "fix: verify candidate and experiment identity at validation"
  ```

### Task 8: Respect lease ownership and final review bundle in all callers

**Files:**
- Modify: `scripts/research_loop.py`
- Modify: `.pi/extensions/strategy-research.ts`
- Modify: `research_runtime/dashboard.py`
- Modify: `scripts/validate_manifest.py`
- Modify: `tests/test_research_loop.py`
- Modify: `tests/test_research_dashboard.py`
- Modify: `tests/test_validation_manifest.py`
- Modify: `tests/pi-strategy-research-contract.mjs`

**Interfaces:**
- Supervisor returns without launching Pi when `start_or_resume_cycle` returns `acquired: false`.
- `/research-cycle` returns without sending an agent message when the lease is not acquired.
- Dashboard approval requires a hash-verified linked PASS `ReviewBundle`, not only `NEEDS_REVIEW` state.
- `validate_manifest` verifies plan hash, run identity, OOS consumption, holdout state, and DB review state.

- [ ] **Step 1: Write failing caller and approval tests.**

  Mock `start_or_resume_cycle` with `acquired=False` and assert the supervisor's command runner is never called. Add a TypeScript contract assertion that the extension checks acquisition before `sendUserMessage`.

  Seed a dashboard hypothesis in `NEEDS_REVIEW` with no run, a PASS run with a wrong manifest hash, and a valid linked PASS bundle. Assert only the valid bundle can be approved. Add a manifest test for candidate/plan/config/policy/snapshot mismatch.

- [ ] **Step 2: Run the focused tests and verify RED.**

  ```bash
  uv run pytest tests/test_research_loop.py tests/test_research_dashboard.py tests/test_validation_manifest.py -q
  node --test tests/pi-strategy-research-contract.mjs
  ```

- [ ] **Step 3: Implement caller guards and review verification.**

  Check `acquired` immediately after cycle acquisition in both callers. Extend dashboard read models with the bounded review bundle and require the linked run/manifest identity before the local-user transition. Keep dashboard routes read-mostly and do not add cycle-start or trading controls.

  Update the extension's operation description and prompt to call `list_source_views`, include complete plan/exit evidence, seal ranking, and stop on lease loss or terminal result. Replace the old instruction that asks the agent to self-attest `full_text_available`.

- [ ] **Step 4: Run focused tests and verify GREEN.**

  ```bash
  uv run pytest tests/test_research_loop.py tests/test_research_dashboard.py tests/test_validation_manifest.py -q
  node --test tests/pi-strategy-research-contract.mjs
  ```

- [ ] **Step 5: Commit caller and approval hardening.**

  ```bash
  git add scripts/research_loop.py .pi/extensions/strategy-research.ts research_runtime/dashboard.py scripts/validate_manifest.py tests/test_research_loop.py tests/test_research_dashboard.py tests/test_validation_manifest.py tests/pi-strategy-research-contract.mjs
  git commit -m "fix: couple research callers and approval to verified state"
  ```

### Task 9: Add sealed comparison cohorts for complete-plan family selection

**Files:**
- Modify: `research_runtime/store.py`
- Modify: `research_runtime/service.py`
- Modify: `research_runtime/validation.py`
- Modify: `tests/test_research_store.py`
- Modify: `tests/test_research_service.py`
- Modify: `tests/test_research_validation.py`

**Interfaces:**
- Produces `ResearchStore.create_evaluation_cohort(payload: Mapping[str, object]) -> dict[str, object]`.
- Adds runtime operation `create_evaluation_cohort` for orchestrator/human use, not autonomous agent use.
- Produces immutable cohort manifest/hash with exactly three frozen candidate/plan identities, common comparison OOS, sealed holdout, and selection rule.
- Allows `owner_id=cohort_id` for one comparison partition and only one selected member for holdout.

- [ ] **Step 1: Write failing cohort tests.**

  Assert cohort creation rejects fewer/more than three members, mutable candidate or plan identities, mismatched snapshot/config/policy identities, duplicate members, missing selection rule, and a member whose candidate is not frozen. Assert no member can validate comparison OOS before all three are registered.

  Assert three conclusive comparison results consume one cohort-owned partition and only the predeclared winner can use the holdout. Assert a post-registration candidate mutation invalidates the cohort.

- [ ] **Step 2: Run the focused tests and verify RED.**

  ```bash
  uv run pytest tests/test_research_store.py tests/test_research_service.py tests/test_research_validation.py -q
  ```

- [ ] **Step 3: Implement immutable cohort registration.**

  Add the cohort tables and service operation. Validate all candidate, plan, dependency, config, policy, and snapshot hashes before sealing. Record the selection rule as canonical JSON. Make validation resolve `owner_id`, partition role, and allowed candidate from the sealed cohort rather than from a model-provided field.

- [ ] **Step 4: Run focused tests and verify GREEN.**

  ```bash
  uv run pytest tests/test_research_store.py tests/test_research_service.py tests/test_research_validation.py -q
  ```

- [ ] **Step 5: Commit cohort governance.**

  ```bash
  git add research_runtime/store.py research_runtime/service.py research_runtime/validation.py tests/test_research_store.py tests/test_research_service.py tests/test_research_validation.py
  git commit -m "feat: seal complete-plan comparison cohorts"
  ```

### Task 10: Rename validation terminology and report complete-plan evidence

**Files:**
- Modify: `scripts/validate_baseline.py`
- Modify: `scripts/validation_core.py`
- Modify: `research_runtime/validation.py`
- Modify: `tests/test_validate_baseline.py`
- Modify: `tests/test_validation_core.py`
- Modify: `tests/test_research_validation.py`

**Interfaces:**
- Manifest labels the existing process as `expanding_window_frozen_candidate_oos`, not conventional WFO optimization.
- Complete-plan manifests include plan identity, exit reason counts, risk-ledger coverage, net realized R, loss-overrun p95, costs, holding duration, MAE/MFE, and OOS consumption.
- Existing hard gates remain unchanged unless a versioned policy explicitly adds a new risk gate before evaluation.

- [ ] **Step 1: Write failing terminology and evidence tests.**

  Assert a validation manifest sets `selection` to `frozen_candidate`/`expanding_window_oos` and does not claim parameter fitting. Assert missing plan hash, missing exit coverage, or missing risk-ledger coverage cannot produce `NEEDS_REVIEW`. Assert all existing OOS, stress, bootstrap, and attribution gates remain active.

- [ ] **Step 2: Run the focused tests and verify RED.**

  ```bash
  uv run pytest tests/test_validate_baseline.py tests/test_validation_core.py tests/test_research_validation.py -q
  ```

- [ ] **Step 3: Implement manifest and metric fields without changing alpha.**

  Rename only the misleading manifest label. Add deterministic diagnostic fields and exit-reason taxonomy. Compute risk metrics from the candidate's declared plan and recorded trades; use them for reporting and predeclared hard safety gates, never for post-result tuning. Keep current fold/trade/drawdown/pass thresholds intact.

- [ ] **Step 4: Run focused tests and verify GREEN.**

  ```bash
  uv run pytest tests/test_validate_baseline.py tests/test_validation_core.py tests/test_research_validation.py -q
  ```

- [ ] **Step 5: Commit terminology and evidence reporting.**

  ```bash
  git add scripts/validate_baseline.py scripts/validation_core.py research_runtime/validation.py tests/test_validate_baseline.py tests/test_validation_core.py tests/test_research_validation.py
  git commit -m "fix: report complete-plan validation evidence accurately"
  ```

### Task 11: Update prompt/contracts and run a canonical database dry audit

**Files:**
- Modify: `prompts/strategy-research.md`
- Modify: `.pi/extensions/strategy-research.ts`
- Modify: `README.md` only for the research-flow/trace wording that is now false
- Modify: `tests/pi-strategy-research-contract.mjs`
- Runtime data: `user_data/research.sqlite`, `user_data/research-artifacts/` only after backup and migration tests pass

**Interfaces:**
- The agent prompt requires source views, role-specific exit evidence, complete plan fields, sealed ranking, one candidate, one validation start, interpretation, and finalization.
- The prompt forbids source self-attestation, parameter sweeps, post-OOS tuning, direct shell/SQL, and trading.
- The canonical database is migrated through the v3 bridge with a backup and an integrity report.

- [ ] **Step 1: Write failing prompt-contract assertions.**

  Require the prompt and extension source to mention `list_source_views`, `seal_hypothesis_ranking`, complete exit-plan evidence, `full_text_available` as immutable collector data, OOS consumption for all conclusive verdicts, and no post-OOS tuning. Assert old unsupported self-attestation wording is absent.

- [ ] **Step 2: Run the contract tests and verify RED.**

  ```bash
  node --test tests/pi-strategy-research-contract.mjs
  ```

- [ ] **Step 3: Update prompt and docs.**

  Make the runtime prompt describe the actual operation sequence and complete-plan research protocol. Keep the model restricted to runtime operations during a bounded cycle. Update README flow/trace text to distinguish development, comparison OOS, and sealed holdout, and to state that the current snapshot is not approval-grade.

- [ ] **Step 4: Run contract tests and verify GREEN.**

  ```bash
  node --test tests/pi-strategy-research-contract.mjs
  ```

- [ ] **Step 5: Back up and migrate the canonical state through the project runtime.**

  ```bash
  cp user_data/research.sqlite user_data/research.sqlite.pre-v3-$(date -u +%Y%m%dT%H%M%SZ)
  uv run python -m research_runtime.cli <<'EOF'
  {"tool":"load_context","payload":{"cycle_id":"C-20260911T160015Z-e2cbad9b"}}
  EOF
  ```

  Instantiate the v3 store through the project package, record the migration/quarantine counts from its structured report, and verify `integrity_check=ok` plus no foreign-key errors. Do not delete or rewrite historical artifacts. If migration fails, restore only the backup copy after preserving the error output and stop.

- [ ] **Step 6: Commit prompt/docs only; keep runtime data uncommitted.**

  ```bash
  git add prompts/strategy-research.md .pi/extensions/strategy-research.ts README.md tests/pi-strategy-research-contract.mjs
  git commit -m "docs: require complete-plan source-grounded research"
  ```

### Task 12: Full verification of research-runtime integrity

**Files:**
- Test-only changes from Tasks 1-11
- No new production files

**Interfaces:**
- Produces a reproducible verification record; does not start trading or promote a candidate.

- [ ] **Step 1: Run the complete Python suite.**

  ```bash
  uv run pytest -q
  ```

  Expected: exit code `0` and zero failures. If not, stop and fix the failing hypothesis with a new RED test before continuing.

- [ ] **Step 2: Run static and contract checks.**

  ```bash
  uv run ruff check research_runtime scripts tests
  uv run python -m compileall -q research_runtime scripts src
  node --test tests/pi-strategy-research-contract.mjs
  git diff --check
  ```

- [ ] **Step 3: Run isolated migration, concurrency, and candidate-boundary checks.**

  Use temporary SQLite/artifact directories for migration and cohort tests. Verify two concurrent acquisition attempts produce one `acquired=true` and one `acquired=false`, the losing caller never invokes Pi, two validation attempts preserve both rows, and forbidden candidate imports are rejected before Freqtrade execution.

- [ ] **Step 4: Confirm the operational boundary.**

  ```bash
  pgrep -af 'freqtrade (trade|webserver)|compose-(demo|live)|research_loop' || true
  git status --short
  ```

  Require no new trading process, no candidate copied into `src/strategies`, and no pre-existing working-tree file staged by this plan.

- [ ] **Step 5: Record the research-runtime result.**

  Record the test commands, exit codes, migration/quarantine counts, and remaining blockers in the implementation session. Do not claim strategy performance or dry-run eligibility from this plan.
