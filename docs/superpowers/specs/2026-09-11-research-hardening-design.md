# Research Flow Hardening Design

## Goal

Harden the existing SQLite/Pi research loop so a candidate cannot be promoted
from a contaminated repeated OOS search, an unreviewed database state, weak
source provenance, or an ambiguous retry/audit record. Keep research bounded and
never start dry-run or live trading automatically.

## Scope

- Persist the research dataset/window and a small search cohort identity.
- Preserve every validation attempt and enforce legal cycle state transitions.
- Require an explicit approved hypothesis state in the dry-run gate.
- Require direct, relevant, and contradictory source evidence for promotion.
- Add a bounded supervisor that resumes only retryable/incomplete cycles.
- Add the missing holdout and leave-one-pair-out diagnostics to validation.
- Wire decay alerts to the existing persisted lock state.
- Make docs describe the current SQLite and rolling-OOS flow.

## Invariants

- The database and hash-verified artifacts remain the source of truth.
- A cycle still admits at most 100 sources, three hypotheses, and one candidate.
- A retry never replaces a prior run row or artifact.
- A terminal cycle cannot be reopened by a generic finalize call.
- A PASS manifest is not dry-run eligible until its hypothesis is
  `APPROVED_FOR_DRY_RUN` in the named research database.
- Reusing a dataset/window after a prior PASS is marked contaminated; it may be
  used for diagnostics but cannot establish a fresh promotion decision.
- Holdout data is never used to generate or tune a candidate.
- No code path in the research loop invokes `freqtrade trade`, demo, live, or
  Compose trading services.

## Design

### Identity and contamination

`cycles` stores the requested dataset, timerange, policy hash, and a
`search_cohort` identifier. A validation manifest stores the cycle and
hypothesis IDs plus the same identity. The dry-run gate verifies all hashes and
requires the hypothesis state in `user_data/research.sqlite` to be
`APPROVED_FOR_DRY_RUN`. A small `validation_windows` table records completed
PASS windows by dataset and policy; a later research cycle on the same window is
research-only until a new holdout is supplied.

### State and audit

Schema version 2 adds cycle identity and validation-window records. Cycle status
transitions are checked against a finite map and update a meaningful stage.
Validation attempts use unique IDs (`...-attempt-01`, etc.) and `runs` is
append-only. Finalization reconciles retryable/testing children and records one
monotonic event with a real UTC timestamp.

### Evidence

Source metadata records `relevance` (`direct`, `supporting`, or `falsifier`),
asset, timeframe, mechanism, and full-text availability. Candidate admission
requires at least one direct/reproducible supporting source and one independent
contradicting or falsifier source; provider diversity alone is insufficient.

### Validation

The current fixed 120/30 expanding folds remain the baseline for candidate
screening and are named rolling OOS unless a fitting stage is added. The
manifest also records a leave-one-pair-out summary and holdout status. The
existing bootstrap p95 drawdown gate remains; a stricter lower-confidence profit
diagnostic is persisted without silently changing the current PASS threshold.

### Supervisor and decay

`research-loop` runs a finite number of invocations, with bounded backoff, and
stops on PASS/NEEDS_REVIEW or any non-retryable conclusion. It never changes a
failed candidate. `monitor_decay` writes `ACTIVE` or `PAUSED`/`YELLOW` state to
the existing validation-state SQLite store, while reopening a paused state still
requires the explicit `review-approved` reason.

## Verification

- New tests fail first for each gate, then pass after the smallest change.
- Full Python tests, Ruff, TypeScript checks, and static contract tests pass.
- A read-only database audit reports `integrity_check=ok`, no active leases, and
  a complete cycle/event history.
- One bounded research cycle is run after the changes. It remains research-only
  if it reuses the contaminated snapshot; no trading process is started.
