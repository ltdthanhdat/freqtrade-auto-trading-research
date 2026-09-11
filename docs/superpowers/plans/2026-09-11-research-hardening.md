# Research Flow Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the SQLite/Pi research pipeline against repeated-OOS selection, weak provenance, unreviewed promotion, and lossy retries, then run one bounded research cycle.

**Architecture:** Extend the existing standard-library SQLite runtime in place. Keep validation and artifact generation in the current scripts, add only the identity/state fields needed for fail-closed gates, and use a small bounded supervisor rather than a daemon.

**Tech Stack:** Python 3.11, SQLite, existing Freqtrade/NumPy/Pandas validation code, pytest, Ruff, TypeScript/Node contract tests.

**Spec:** `docs/superpowers/specs/2026-09-11-research-hardening-design.md`

## Global Constraints

- No dry-run/live/trade/Compose trading process.
- Existing six-pair basket and stress parameters remain unchanged.
- Every production behavior change gets a failing regression test first.
- Retryable/incomplete cycles may resume only within a finite supervisor budget.
- Existing PASS thresholds are not weakened to accommodate the current winner.

### Task 1: Identity and state schema hardening

**Files:**
- Modify: `research_runtime/store.py`
- Modify: `research_runtime/service.py`
- Test: `tests/test_research_store.py`, `tests/test_research_service.py`

**Interfaces:**
- Add v2 migration for `cycles` identity fields and `validation_windows`.
- Add `record_validation_window`/`window_is_contaminated` read methods.
- Preserve append-only run attempts with unique IDs.
- Enforce cycle transitions and stage updates.

- [ ] Write tests for migration, legal terminal transitions, retry attempt retention, timestamp monotonicity, and contaminated-window lookup.
- [ ] Run the focused tests and observe the expected failures.
- [ ] Implement the smallest v2 migration and store methods.
- [ ] Run focused store/service tests.
- [ ] Commit `fix: preserve research state and validation identity`.

### Task 2: Review-state and identity enforcement

**Files:**
- Modify: `scripts/validate_manifest.py`
- Modify: `Makefile`
- Modify: `research_runtime/validation.py`
- Test: `tests/test_validation_manifest.py`, `tests/test_research_validation.py`

**Interfaces:**
- `validate_manifest` accepts an optional research DB and hypothesis ID.
- It verifies manifest cycle/hypothesis IDs, candidate hash, DB hypothesis state,
  and contaminated-window status.
- `make validate-pass` passes the DB by default.

- [ ] Add failing tests for missing approval, mismatched candidate identity, and repeated-window rejection.
- [ ] Implement fail-closed checks without changing existing baseline thresholds.
- [ ] Run focused manifest/validation tests.
- [ ] Commit `fix: enforce reviewed research promotion`.

### Task 3: Evidence relevance and audit presentation

**Files:**
- Modify: `research_runtime/service.py`
- Modify: `research_runtime/dashboard.py`
- Modify: `dashboard/index.html`
- Test: `tests/test_research_service.py`, `tests/test_research_dashboard.py`

**Interfaces:**
- Candidate admission requires direct supporting evidence and an independent
  contradictory/falsifier source with matching relevance metadata.
- Dashboard exposes all cycles and state-event history through read-only routes.

- [ ] Add failing evidence/dashboard tests.
- [ ] Implement metadata checks and `/api/cycles` plus `/api/events`.
- [ ] Run focused tests and static markup checks.
- [ ] Commit `fix: strengthen research evidence and history`.

### Task 4: Validation diagnostics and bounded supervisor

**Files:**
- Modify: `scripts/validate_baseline.py`
- Modify: `research_runtime/validation.py`
- Create: `scripts/research_loop.py`
- Modify: `Makefile`, `.pi/extensions/strategy-research.ts`, `prompts/strategy-research.md`
- Test: `tests/test_validate_baseline.py`, `tests/test_research_validation.py`, `tests/test_research_loop.py`, `tests/pi-strategy-research-contract.mjs`

**Interfaces:**
- Manifest persists holdout status and leave-one-pair-out diagnostics.
- `python -m scripts.research_loop --max-cycles N` resumes only retryable/incomplete cycles and stops on terminal conclusions.

- [ ] Add failing diagnostics/supervisor tests.
- [ ] Implement deterministic diagnostics and finite loop/backoff.
- [ ] Run focused tests and extension checks.
- [ ] Commit `feat: add bounded research supervisor diagnostics`.

### Task 5: Decay lock wiring and documentation

**Files:**
- Modify: `scripts/monitor_decay.py`
- Modify: `scripts/validation_core.py`
- Modify: `README.md`, `AGENTS.md`, `dashboard/DESIGN.md`
- Test: `tests/test_runtime_protections.py`, `tests/test_validation_regressions.py`

**Interfaces:**
- Decay monitor writes persisted state transitions with a required run ID.
- Docs point to SQLite/artifacts and describe rolling OOS, holdout, and review gate.

- [ ] Add failing state-wiring tests and stale-doc contract checks.
- [ ] Implement state writes and update docs.
- [ ] Run full suite, Ruff, extension tests, and `git diff --check`.
- [ ] Commit `docs: align research operations with hardened flow`.

### Task 6: Re-run research safely

**Files:**
- Runtime artifacts only: `user_data/research.sqlite`, `user_data/research-artifacts/`

- [ ] Verify no active worker/trading process.
- [ ] Run `make research-data` read/verify path and capture snapshot identity.
- [ ] Run one bounded supervisor/cycle with the existing snapshot; stop on the new contamination/review gate.
- [ ] Audit DB integrity, cycle/event history, manifest hashes, and process list.
- [ ] Report PASS/RESEARCH_ONLY/NEEDS_REVIEW separately; do not start dry/live.
