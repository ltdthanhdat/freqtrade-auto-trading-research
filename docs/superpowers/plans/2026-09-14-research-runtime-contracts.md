# Research Runtime Contracts and Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the research runtime independently resumable, externally reconcilable, candidate-safe, and driven by one hashed canonical prompt without depending on the repo-local research skill.

**Architecture:** Keep `ResearchStore` as the transactional state boundary and add a schema-v4 lifecycle bridge for lease ownership, heartbeats, recovery accounting, immutable run identity, and completion timestamps. Keep the Pi extension as a thin adapter, load the canonical Markdown prompt from `prompts/strategy-research.md`, and perform Freqtrade candidate loading before any OOS allocation or backtest fold execution.

**Tech Stack:** Python 3.11, `sqlite3`, Freqtrade's `StrategyResolver`, pytest, TypeScript Pi extension, Node test runner, SHA-256.

**Spec:** `docs/superpowers/specs/2026-09-14-daily-research-orchestration-storage-design.md`

## Global Constraints

- Maximum 100 collected sources, 3 structured hypotheses, and 1 candidate per cycle.
- Identity-bound hypotheses use `required_data` exactly `["OHLCV"]`.
- Ranking is sealed before candidate writing; validation starts once; no tuning or plan changes occur after OOS begins.
- OOS partitions are consumed exactly once; comparison OOS requires a sealed three-candidate cohort and only its selected member may use holdout.
- Missing identity, plan, evidence, candidate contract, or artifacts fails closed and never authorizes trading.
- Pi may call only `strategy_research_runtime`; no shell, SQL, arbitrary filesystem writes, TradingView, worker, dry-run, live, promotion, sweep, or post-OOS tuning.
- Conclusive validation failures are research verdicts, not infrastructure retries.
- Preserve `src/strategies/`, `config/`, and existing strategy entry/stop/ROI/time/trailing/regime semantics.
- Do not touch `data-opportunity-lab` or remove system skills under `/home/datlt/.pi/agent/skills/`.

**Execution dependency:** Tasks 1–4 are the runtime prerequisites. Task 5 is deliberately deferred until the SQLite migration, DAG wiring, and disposable daily-run proof in the master plan have passed; do not delete `.agents/skills/freqtrade-strategy-research-loop/` or `.research/` during the runtime-only phase.

---

### Task 1: Load and hash the canonical research prompt

**Files:**
- Create: `research_runtime/prompt.py`
- Modify: `prompts/strategy-research.md`
- Modify: `scripts/research_loop.py::_research_prompt`
- Modify: `.pi/extensions/strategy-research.ts`
- Test: `tests/test_research_loop.py`
- Test: `tests/pi-strategy-research-contract.mjs`

**Interfaces:**
- Produces `load_research_prompt(path: Path = Path("prompts/strategy-research.md")) -> tuple[str, str]`, returning the UTF-8 template and its SHA-256 digest.
- Produces `render_research_prompt(template: str, *, cycle_id: str, validation_context: str) -> str`, replacing only `{{CYCLE_ID}}` and `{{VALIDATION_CONTEXT}}` and rejecting any remaining `{{...}}` token.
- `scripts.research_loop._research_prompt` becomes a compatibility wrapper that calls these functions; it no longer contains the protocol text.

- [ ] **Step 1: Write failing prompt-loader tests**

Add tests with exact assertions:

```python
from pathlib import Path

import pytest

from research_runtime.prompt import load_research_prompt, render_research_prompt


def test_prompt_loader_returns_stable_sha256(tmp_path: Path):
    path = tmp_path / "strategy-research.md"
    path.write_text("cycle={{CYCLE_ID}}\\ncontext={{VALIDATION_CONTEXT}}\\n", encoding="utf-8")

    template, digest = load_research_prompt(path)

    assert template.startswith("cycle={{CYCLE_ID}}")
    assert len(digest) == 64
    assert digest == load_research_prompt(path)[1]


def test_prompt_renderer_replaces_only_known_tokens():
    rendered = render_research_prompt(
        "cycle={{CYCLE_ID}}\\ncontext={{VALIDATION_CONTEXT}}\\n",
        cycle_id="C-1",
        validation_context="snapshot_sha256=abc",
    )

    assert rendered == "cycle=C-1\\ncontext=snapshot_sha256=abc\\n"


def test_prompt_renderer_rejects_unresolved_tokens():
    with pytest.raises(ValueError, match="unresolved prompt token"):
        render_research_prompt("{{CYCLE_ID}} {{UNKNOWN}}", cycle_id="C-1", validation_context="x")
```

Add a supervisor assertion that the prompt passed to Pi contains the canonical file's complete-plan rules and the current cycle identity, while the Python module no longer contains the old long protocol string.

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
uv run pytest tests/test_research_loop.py -q
```

Expected: FAIL because `research_runtime.prompt` and the new loader contract do not exist.

- [ ] **Step 3: Move the full protocol into the canonical template**

Rewrite `prompts/strategy-research.md` so it contains the current rules from `_research_prompt`, with exactly these placeholders near the cycle header:

```markdown
Run exactly one bounded strategy research cycle through `strategy_research_runtime` for `cycle_id={{CYCLE_ID}}`.

The supervisor already acquired this cycle lease. Use the prepared identity below:

{{VALIDATION_CONTEXT}}
```

Retain the explicit payload shapes, `required_data=["OHLCV"]`, complete exit/risk plan, role-specific evidence, provider restrictions, sealed ranking, one candidate, one validation, OOS-once-only rule, and terminal-stop rule. Do not add a second copy of those rules to TypeScript or Python.

- [ ] **Step 4: Implement the loader and update both callers**

Implement `research_runtime/prompt.py` with UTF-8 reads, raw-template SHA-256, exact token replacement, and unresolved-token rejection:

```python
from hashlib import sha256
from pathlib import Path
import re

_TOKEN = re.compile(r"{{[A-Z0-9_]+}}")


def load_research_prompt(path: Path = Path("prompts/strategy-research.md")) -> tuple[str, str]:
    template = path.read_text(encoding="utf-8")
    return template, sha256(template.encode("utf-8")).hexdigest()


def render_research_prompt(template: str, *, cycle_id: str, validation_context: str) -> str:
    rendered = template.replace("{{CYCLE_ID}}", cycle_id).replace(
        "{{VALIDATION_CONTEXT}}", validation_context
    )
    unresolved = _TOKEN.findall(rendered)
    if unresolved:
        raise ValueError(f"unresolved prompt token: {unresolved[0]}")
    return rendered
```

Replace `_research_prompt`'s protocol f-string with `load_research_prompt` plus `render_research_prompt`. Load and hash the canonical template before `start_or_resume_cycle`, pass `prompt_sha256` into cycle acquisition, and render the prompt only after the cycle lease is acquired. In the extension, pass `--db` from `RESEARCH_DB` and `--artifacts` from `RESEARCH_ARTIFACT_ROOT` to the `uv run python -m research_runtime.cli` subprocess, then use `readFileSync(new URL("../../prompts/strategy-research.md", import.meta.url), "utf8")` for the manual `research-cycle` command and apply the same two replacements; retain only the short command bootstrap and runtime-tool adapter.

- [ ] **Step 5: Run prompt and extension contracts**

Run:

```bash
uv run pytest tests/test_research_loop.py -q
node --test tests/pi-strategy-research-contract.mjs
```

Expected: PASS, with no long duplicate protocol string in `.pi/extensions/strategy-research.ts` or `scripts/research_loop.py`.

- [ ] **Step 6: Commit the isolated prompt change**

```bash
git add research_runtime/prompt.py prompts/strategy-research.md scripts/research_loop.py .pi/extensions/strategy-research.ts tests/test_research_loop.py tests/pi-strategy-research-contract.mjs
git commit -m "refactor: load canonical research prompt"
```

---

### Task 2: Add lease ownership, heartbeat, recovery accounting, and reconciliation

**Files:**
- Modify: `research_runtime/store.py:SCHEMA_VERSION, ResearchStore.__init__, start_or_resume_cycle, set_cycle_status`
- Modify: `research_runtime/service.py:OPERATION_FIELDS, REQUIRED_FIELDS, call`
- Modify: `research_runtime/cli.py:main`
- Test: `tests/test_research_store.py`
- Test: `tests/test_research_service.py`
- Create: `tests/test_research_reconciliation.py`

**Interfaces:**
- `ResearchStore.start_or_resume_cycle(now: datetime | str | dict[str, Any] | None = None) -> dict[str, Any]` accepts and persists `airflow_run_key`, `snapshot_sha256`, `snapshot_manifest_path`, and `prompt_sha256`; it accepts `lease_owner` as the lease actor and stores a non-empty fallback owner (`runtime-local`) for legacy local callers.
- `ResearchStore.find_cycle_by_airflow_run_key(run_key: str) -> dict[str, Any] | None` returns the newest cycle carrying that exact run identity.
- `ResearchStore.heartbeat_cycle(cycle_id: str, *, lease_owner: str, now: datetime | str | None = None) -> dict[str, Any]` extends the lease only for the matching active owner.
- `ResearchStore.reconcile_cycle(cycle_id: str, *, observed_status: str, reason: str, observed_task_id: str | None = None, observed_container_id: str | None = None, lease_owner: str | None = None, now: datetime | str | None = None) -> dict[str, Any]` is idempotent and returns the current cycle plus `action` (`NO_OP`, `RECONCILED`, or `STILL_RUNNING`); `observed_status` is one of `WATCHDOG`, `SUCCEEDED`, `FAILED`, `TIMEOUT`, or `MISSING`.
- `ResearchStore.set_cycle_status(cycle_id, status, reason, now=None, *, error_code=None, payload=None, actor="runtime")` preserves its current positional arguments while allowing terminal error metadata to be recorded.
- `ResearchService.heartbeat_cycle(payload: dict[str, Any]) -> dict[str, Any]` and `ResearchService.reconcile_cycle(payload: dict[str, Any]) -> dict[str, Any]` expose those operations through the typed transport.
- Schema v4 adds `lease_owner`, `lease_heartbeat_at`, `recovery_attempts INTEGER NOT NULL DEFAULT 0 CHECK(recovery_attempts BETWEEN 0 AND 1)`, `completed_at`, `last_error_code`, `snapshot_sha256`, `snapshot_manifest_path`, `prompt_sha256`, and `airflow_run_key` to `cycles`.

- [ ] **Step 1: Write failing schema and lifecycle tests**

Add these cases:

```python
import sqlite3

import pytest

from research_runtime.store import ResearchStore
from tests.test_research_store import make_v2_integrity_fixture


def test_v3_database_migrates_to_v4_and_preserves_cycle_rows(tmp_path):
    path = tmp_path / "research.sqlite"
    make_v2_integrity_fixture(path)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version = 3")

    store = ResearchStore(path)
    result = store.start_or_resume_cycle("2026-09-14T07:00:00Z")
    cycle_id = result["cycle"]["id"]

    reopened = ResearchStore(path)
    cycle = reopened.get_cycle(cycle_id)

    assert cycle["id"] == cycle_id
    assert cycle["recovery_attempts"] == 0
    assert reopened.integrity_report() == {"integrity_check": "ok", "foreign_key_errors": []}


def test_heartbeat_requires_the_current_lease_owner(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite", lease_seconds=60)
    cycle = store.start_or_resume_cycle({"now": "2026-09-14T07:00:00Z", "lease_owner": "dag-a"})["cycle"]

    with pytest.raises(ValueError, match="lease owner"):
        store.heartbeat_cycle(cycle["id"], lease_owner="dag-b", now="2026-09-14T07:00:10Z")

    updated = store.heartbeat_cycle(cycle["id"], lease_owner="dag-a", now="2026-09-14T07:00:10Z")
    assert updated["lease_heartbeat_at"] == "2026-09-14T07:00:10Z"


def test_recovery_budget_allows_one_resume_only(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite", lease_seconds=60)
    first = store.start_or_resume_cycle({"now": "2026-09-14T07:00:00Z", "lease_owner": "dag-a"})
    cycle_id = first["cycle"]["id"]

    store.reconcile_cycle(
        cycle_id,
        observed_status="FAILED",
        reason="container disappeared",
        now="2026-09-14T09:00:00Z",
        lease_owner="dag-a",
    )
    resumed = store.start_or_resume_cycle({"now": "2026-09-14T09:01:00Z", "lease_owner": "dag-a"})
    assert resumed["acquired"] is True
    assert resumed["cycle"]["recovery_attempts"] == 1

    store.reconcile_cycle(
        cycle_id,
        observed_status="FAILED",
        reason="second container disappeared",
        now="2026-09-14T11:00:00Z",
        lease_owner="dag-a",
    )
    blocked = store.start_or_resume_cycle({"now": "2026-09-14T11:01:00Z", "lease_owner": "dag-a"})
    assert blocked["acquired"] is False
    assert blocked["blocked_reason"] == "recovery_budget_exhausted"


def test_needs_review_cycle_blocks_automatic_new_cycle(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    cycle_id = store.start_or_resume_cycle("2026-09-14T07:00:00Z")["cycle"]["id"]
    store.set_cycle_status(cycle_id, "NEEDS_REVIEW", "validation passed")

    blocked = store.start_or_resume_cycle({"now": "2026-09-15T07:00:00Z", "dataset": "snapshots/daily-2"})

    assert blocked["acquired"] is False
    assert blocked["cycle"]["id"] == cycle_id
    assert blocked["blocked_reason"] == "review_required"
```

Add reconciliation tests for: a terminal `COMPLETED`, `NEEDS_REVIEW`, or `FAILED` cycle returning `NO_OP`; an already `INCOMPLETE` cycle returning `NO_OP` until explicitly resumed; a `PASS` run with verified manifest/report becoming `NEEDS_REVIEW`; a `FAIL` run with verified artifacts becoming `FAILED`; a `WARN`/inconclusive run becoming `INCOMPLETE`; and a stale `RUNNING` cycle with no conclusive run becoming `INCOMPLETE`. Verify every actual transition adds one `state_events` row and no duplicate event appears on a second reconciliation call.

- [ ] **Step 2: Run the lifecycle tests and verify failure**

Run:

```bash
uv run pytest tests/test_research_store.py tests/test_research_service.py tests/test_research_reconciliation.py -q
```

Expected: FAIL because the schema columns and typed methods do not exist.

- [ ] **Step 3: Implement the schema-v4 migration**

Set `SCHEMA_VERSION = 4` and add `_migrate_v4(connection)` that checks `PRAGMA table_info(cycles)` before each `ALTER TABLE`, adds the nine lifecycle/identity columns, backfills `completed_at` from `updated_at` for existing terminal cycles and `runs.completed_at` from `created_at` for existing non-retryable runs, and creates an index for stale-cycle lookup:

```sql
CREATE INDEX IF NOT EXISTS idx_cycles_running_lease
ON cycles(status, lease_until, updated_at);
```

Call `_migrate_v4` for fresh, v1, v2, v3, and v4 databases in the existing initialization bridge. Update existing schema-version assertions from `3` to `4`. Keep `_migrate_v1`, `_migrate_v2`, and `_migrate_v3` idempotent and preserve all existing rows.

- [ ] **Step 4: Implement owner-checked heartbeat and bounded resume**

Update identity extraction in `start_or_resume_cycle` to include `airflow_run_key`, `snapshot_sha256`, `snapshot_manifest_path`, and `prompt_sha256`; compare non-empty stored values on resume and reject mismatches. Treat `lease_owner` as the lease actor rather than immutable experiment identity, require the production supervisor to pass its sanitized Airflow run key as owner, and use `runtime-local` only for legacy local callers. Store the lease owner on create/resume, set `lease_heartbeat_at` at acquisition, and increment `recovery_attempts` exactly when an `INTERRUPTED`/`INCOMPLETE` cycle is resumed. Select the newest non-terminal cycle for resume; never resume an older interrupted cycle after a newer cycle exists. Before creating a new cycle, inspect the newest cycle globally: an active `RUNNING` lease blocks acquisition, `INCOMPLETE`/`INTERRUPTED` resumes only within the one-recovery budget, and `NEEDS_REVIEW` blocks automatic creation until an explicit review transition closes it. Return:

```python
{"cycle": dict(row), "acquired": False, "blocked_reason": "recovery_budget_exhausted"}
```

when the one-recovery budget is exhausted. Return the newest `NEEDS_REVIEW` row with `acquired=False` and `blocked_reason="review_required"` until an explicit review transition closes it. `heartbeat_cycle` must execute under `BEGIN IMMEDIATE`, require status `RUNNING`, require a matching non-empty `lease_owner`, reject an expired lease, update `lease_until`, `lease_heartbeat_at`, and `updated_at`, and return the updated row.

- [ ] **Step 5: Implement idempotent reconciliation and typed dispatch**

Implement `reconcile_cycle` under `BEGIN IMMEDIATE`:

- Return `NO_OP` for terminal `COMPLETED`, `NEEDS_REVIEW`, or `FAILED` cycles, and for an already `INCOMPLETE` cycle when no newer run or lease-expiry transition is being reconciled; `INCOMPLETE` remains resumable through `start_or_resume_cycle`.
- Inspect the latest run for the cycle's experiment. A run is conclusive only when its verdict is `PASS`, `WARN`, or `FAIL` and its artifact manifest/report paths exist with hashes matching the stored artifact metadata. A conclusive verdict without verified artifacts becomes `INCOMPLETE`, never a performance claim.
- Map a verified conclusive `PASS` to cycle `NEEDS_REVIEW`, a verified conclusive `FAIL` to `FAILED`, and a verified conclusive `WARN` to `INCOMPLETE`.
- If no conclusive run exists and `observed_status` is `FAILED`, `TIMEOUT`, `MISSING`, or the lease is expired, transition `RUNNING`/`INTERRUPTED` to `INCOMPLETE` and record the supplied task/container details in the event payload.
- Set `completed_at` whenever a cycle enters `NEEDS_REVIEW`, `FAILED`, or `INCOMPLETE`, set `last_error_code` for failed/incomplete transitions when supplied, and clear `lease_until`.
- Use a conditional non-terminal update so a concurrent finalizer wins safely. The method appends exactly one event for a real transition and returns `NO_OP` if another actor has already transitioned the row.

Add the two operations to `ResearchService.OPERATION_FIELDS` and `REQUIRED_FIELDS` with these exact payloads:

```json
{"tool":"heartbeat_cycle","payload":{"cycle_id":"C-1","lease_owner":"dag-a","now":"2026-09-14T07:01:00Z"}}
{"tool":"reconcile_cycle","payload":{"cycle_id":"C-1","observed_status":"TIMEOUT","reason":"research container timed out","observed_task_id":"run_research","observed_container_id":"container-id","lease_owner":"dag-a","now":"2026-09-14T07:30:00Z"}}
```

- [ ] **Step 6: Run all lifecycle tests and commit**

Run:

```bash
uv run pytest tests/test_research_store.py tests/test_research_service.py tests/test_research_reconciliation.py tests/test_research_cli.py -q
```

Expected: PASS.

```bash
git add research_runtime/core.py research_runtime/store.py research_runtime/service.py research_runtime/cli.py tests/test_research_store.py tests/test_research_service.py tests/test_research_reconciliation.py
git commit -m "feat: add research cycle reconciliation"
```

---

### Task 3: Persist complete timestamps and machine-readable run summaries

**Files:**
- Create: `scripts/run_summary.py`
- Create: `scripts/reconcile_research_cycle.py`
- Create: `scripts/publish_research_report.py`
- Modify: `research_runtime/store.py:record_validation_bundle`
- Modify: `scripts/research_loop.py:run_research_loop, main`
- Test: `tests/test_research_loop.py`
- Test: `tests/test_research_store.py`
- Create: `tests/test_research_run_summary.py`

**Interfaces:**
- `write_run_summary(root: Path, run_key: str, payload: Mapping[str, object]) -> Path` writes `root / "runs" / safe_run_key / "run-summary.json"` atomically; terminal writes require a non-null `completed_at`.
- Required summary fields are `schema_version=1`, `airflow_run_key`, `status`, `phase`, `started_at`, and `completed_at`; `cycle_id` and `snapshot_sha256` are optional before cycle acquisition. The supervisor may hold a non-terminal draft in memory, but every persisted summary is terminal.
- `scripts.research_loop.run_research_loop` accepts `run_key: str | None = None`, `summary_root: Path | None = None`, and `snapshot_manifest: Path | None = None`, and its CLI accepts matching `--run-key`, `--artifacts`, and `--snapshot-manifest` options.
- `scripts.reconcile_research_cycle.main` accepts `--db`, `--artifacts`, optional `--cycle-id`, optional `--latest`, `--observed-status`, `--reason`, `--run-key`, `--task-id`, `--container-id`, and `--lease-owner` and calls `ResearchService.reconcile_cycle`.
- `scripts.publish_research_report.main` accepts `--artifacts` and `--run-key`, reads only that run's JSON summary, prints a bounded status line, and exits non-zero only for missing/corrupt summary.

- [ ] **Step 1: Write failing summary and timestamp tests**

Add:

```python
import json
from pathlib import Path

import pytest

from scripts.run_summary import write_run_summary


def test_run_summary_is_keyed_by_airflow_run_and_written_atomically(tmp_path: Path):
    path = write_run_summary(
        tmp_path,
        "scheduled__2026-09-14T07-15-00+00-00",
        {
            "status": "INCOMPLETE",
            "phase": "prepare_snapshot",
            "started_at": "2026-09-14T07:15:00Z",
            "completed_at": "2026-09-14T07:16:00Z",
            "reason": "missing 1m coverage",
        },
    )

    assert path == tmp_path / "runs" / "scheduled__2026-09-14T07-15-00+00-00" / "run-summary.json"
    payload = json.loads(path.read_text())
    assert payload["schema_version"] == 1
    assert payload["airflow_run_key"] == "scheduled__2026-09-14T07-15-00+00-00"
    assert not list(path.parent.glob("*.tmp"))


def test_run_summary_rejects_missing_terminal_fields(tmp_path: Path):
    with pytest.raises(ValueError, match="completed_at"):
        write_run_summary(tmp_path, "run-1", {"status": "FAILED", "phase": "research"})
```

Add a store test that a conclusive `record_validation_bundle` inserts a non-null `runs.completed_at`, and a cycle status transition inserts non-null `cycles.completed_at`.

- [ ] **Step 2: Run focused tests and verify failure**

```bash
uv run pytest tests/test_research_run_summary.py tests/test_research_loop.py tests/test_research_store.py -q
```

Expected: FAIL because the summary module and completion timestamp handling do not exist.

- [ ] **Step 3: Implement atomic summary writing**

Sanitize only path characters outside `[A-Za-z0-9_.-]` to `-`, reject an empty result, validate the required fields, add `schema_version` and `airflow_run_key`, serialize with sorted keys and an ending newline, write to a sibling temporary file, flush/fsync, and replace the final path. Never overwrite a summary from a different `airflow_run_key`.

- [ ] **Step 4: Wire summaries and completion timestamps into the supervisor**

At supervisor start, create the run-key summary with phase `acquire_cycle` and `completed_at=None` only in memory; write the terminal form on every return path: lease not acquired, timeout, keyboard interruption, Pi command failure, conclusive `FAILED`, `NEEDS_REVIEW`, or `COMPLETED`. Include `cycle_id`, `snapshot_sha256`, `snapshot_manifest_path`, `last_phase`, `stopped_reason`, `returncode`, and a bounded error tail when available. If the supervisor cannot acquire a cycle because a different active owner holds the lease, record `INCOMPLETE` without creating another cycle.

Pass `snapshot_manifest` into cycle identity and the rendered validation context. Do not let summary-writing errors replace the original research result; append the summary error to the supervisor log and retain the original exit status.

Update `_insert_run` callers so conclusive and retryable run records set `completed_at` at the time the result is committed. Update `set_cycle_status` to set `completed_at` for `COMPLETED`, `NEEDS_REVIEW`, `INCOMPLETE`, and `FAILED`, and leave it null only for non-terminal `RUNNING`/`INTERRUPTED` rows. Return the terminal cycle status separately from `stopped_reason` so a cycle that reaches the `max_cycles` loop limit while still `RUNNING`/`INCOMPLETE` cannot be reported as a successful `max_cycles` result.

- [ ] **Step 5: Implement the reconciliation CLI**

`reconcile_research_cycle.py` must construct `ResearchService(ResearchStore(args.db), args.artifacts)`. Select the target in this order: explicit `--cycle-id`; then `ResearchStore.find_cycle_by_airflow_run_key(args.run_key)` when `--run-key` is supplied; then the newest cycle through `ResearchStore.list_cycles(limit=1)` when `--latest` is set. If no target exists, return a sorted `NO_OP` JSON response and, when a run key is supplied with an observed failure, write an `INCOMPLETE` terminal summary so pre-cycle/preflight failures are still reported. Otherwise it calls:

```python
service.call(
    "reconcile_cycle",
    {
        "cycle_id": cycle_id,
        "observed_status": args.observed_status,
        "reason": args.reason,
        "observed_task_id": args.task_id,
        "observed_container_id": args.container_id,
        "lease_owner": args.lease_owner,
    },
)
```

Pass `args.artifacts` to `ResearchService`, use `args.run_key` to update or create the terminal run summary with the reconciliation action, print one sorted JSON result, and return `0` for `NO_OP`, `RECONCILED`, or `STILL_RUNNING`; return `1` only for invalid arguments or runtime errors. This CLI must not initialize Pi or require Pi credentials. `publish_research_report.py` reads the same summary path, logs `status`, `cycle_id`, `snapshot_sha256`, and report references, and does not open SQLite.

- [ ] **Step 6: Run focused tests and commit**

```bash
uv run pytest tests/test_research_run_summary.py tests/test_research_loop.py tests/test_research_store.py tests/test_research_reconciliation.py -q
```

Expected: PASS.

```bash
git add scripts/run_summary.py scripts/reconcile_research_cycle.py scripts/publish_research_report.py scripts/research_loop.py research_runtime/store.py tests/test_research_run_summary.py tests/test_research_loop.py tests/test_research_store.py
git commit -m "feat: persist research run summaries"
```

---

### Task 4: Preflight Freqtrade candidates before OOS consumption

**Files:**
- Create: `research_runtime/freqtrade_preflight.py`
- Modify: `research_runtime/validation.py:validate_candidate`
- Test: `tests/test_research_validation.py`
- Test: `tests/test_research_candidates.py`

**Interfaces:**
- Create `CandidatePreflightResult` with `passed: bool`, `strategy_name: str`, `strategy_path: Path`, and `details: tuple[str, ...]`.
- Create `preflight_candidate(*, config_path: Path, strategy_name: str, strategy_path: Path) -> CandidatePreflightResult`.
- `validate_candidate` accepts an injectable `preflight_fn: Callable[..., CandidatePreflightResult] = preflight_candidate`, calls it after candidate hash/AST identity checks and before `run_validation_fn`, and returns a rejected `ResearchVerdict` with `error_code="candidate_preflight"`, preflight artifact references, and no OOS consumption without invoking the validator.

- [ ] **Step 1: Write the regression test for missing `populate_exit_trend`**

Add a candidate source with a futures config, one `IStrategy` class, and `populate_entry_trend` but no override for `populate_exit_trend`. The config must include at least `strategy`, a single-entry `strategy_path`, `trading_mode: "futures"`, `margin_mode: "isolated"`, `dry_run: true`, `stake_currency`, `stake_amount`, and an `exchange` object with `name` and the candidate pair whitelist. Stub `collect_identity_fn` to return the four expected hashes and the matching strategy metadata so the test isolates the preflight gate. Call `validate_candidate` with a validator that raises if called:

```python
import hashlib
import json
from pathlib import Path

from research_runtime.freqtrade_preflight import preflight_candidate
from research_runtime.validation import validate_candidate


def identity_bound_experiment_for(candidate: Path, tmp_path: Path) -> dict[str, object]:
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({
            "strategy": candidate.stem,
            "strategy_path": str(candidate.parent),
            "trading_mode": "futures",
            "can_short": True,
            "exchange": {"pair_whitelist": ["BTC/USDT:USDT"]},
        }),
        encoding="utf-8",
    )
    digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
    return {
        "id": "EXP-preflight",
        "candidate_path": str(candidate),
        "candidate_sha256": digest,
        "strategy_name": candidate.stem,
        "strategy_path": str(candidate.parent),
        "strategy_file": str(candidate),
        "config_path": str(config),
        "snapshot_path": str(tmp_path / "snapshot"),
        "policy_path": str(tmp_path / "policy.json"),
        "start_at": "2026-01-01T00:00:00Z",
        "end_at": "2026-02-01T00:00:00Z",
        "runs_dir": str(tmp_path / "runs"),
        "parent_sha256": "a" * 64,
        "config_sha256": "b" * 64,
        "snapshot_sha256": "c" * 64,
        "policy_sha256": "d" * 64,
        "identity_bound": True,
        "plan_sha256": "e" * 64,
    }


def test_candidate_preflight_rejects_missing_exit_callback_before_oos(tmp_path):
    candidate = tmp_path / "Candidate.py"
    candidate.write_text(
        "from freqtrade.strategy import IStrategy\n"
        "class Candidate(IStrategy):\n"
        "    can_short = True\n"
        "    def populate_entry_trend(self, dataframe, metadata):\n"
        "        return dataframe\n",
        encoding="utf-8",
    )
    experiment = identity_bound_experiment_for(candidate, tmp_path)

    def must_not_run(_experiment):
        raise AssertionError("OOS validator was called")

    result = validate_candidate(
        experiment,
        collect_identity_fn=lambda *_: {
            "config_sha256": "b" * 64,
            "snapshot_sha256": "c" * 64,
            "policy_sha256": "d" * 64,
            "accepted_pairs": ("BTC/USDT:USDT",),
            "strategy": candidate.stem,
            "strategy_path": str(candidate.parent),
        },
        preflight_fn=preflight_candidate,
        run_validation_fn=must_not_run,
    )

    assert result.verdict == "FAIL"
    assert result.state == "REJECTED"
    assert result.error_code == "candidate_preflight"
    assert not result.artifacts.get("oos_partitions")
```

Add the inverse test using `tests/fixtures/rsi_candidates/FuturesRiskBase_Freqtrade.py` and the same minimal valid futures config; assert the validator is called exactly once after preflight succeeds. Update existing wrapper tests that intentionally use non-Freqtrade fixture classes to pass `preflight_fn=lambda **_: CandidatePreflightResult(True, "CandidateA", Path(values["candidate_path"]).parent, ())`, so those tests continue to isolate verdict mapping without bypassing the production gate.

- [ ] **Step 2: Run the regression tests and verify failure**

```bash
uv run pytest tests/test_research_validation.py tests/test_research_candidates.py -q
```

Expected: FAIL because validation currently proceeds directly to the runner.

- [ ] **Step 3: Implement the Freqtrade loader gate**

Load the effective config with the same merge path used by `collect_identity`, set `strategy` and `strategy_path` to the frozen candidate values, and call `StrategyResolver.load_strategy(config_values)`. Require the returned class name to equal `strategy_name`. Catch `OperationalException`, `ImportError`, `ValueError`, and `TypeError` into deterministic `details`; do not catch process/system exceptions as a successful preflight.

`StrategyResolver.load_strategy` is required instead of a mere `hasattr` check because the active Freqtrade version's `validate_strategy` detects missing futures callbacks, including ``populate_exit_trend``.

- [ ] **Step 4: Add a preflight artifact without allocating OOS**

When preflight fails, write `preflight.json` and `report.md` below `Path(experiment["runs_dir"]) / experiment["id"]` (or the equivalent artifact-root validation directory) with the candidate path, candidate SHA-256, strategy name, config path/hash, error code, and details. Return `manifest_path`, `report_path`, their hashes, and the preflight details in `ResearchVerdict.artifacts`. Do not create `oos_partition_consumptions`; the surrounding `record_validation_bundle` may record the rejected run only after the preflight artifact exists.

- [ ] **Step 5: Run validation tests and commit**

```bash
uv run pytest tests/test_research_validation.py tests/test_research_candidates.py tests/test_validation_regressions.py -q
```

Expected: PASS, including the missing-`populate_exit_trend` regression.

```bash
git add research_runtime/freqtrade_preflight.py research_runtime/validation.py tests/test_research_validation.py tests/test_research_candidates.py
git commit -m "fix: preflight candidates before oos"
```

---

### Task 5: Retire the repo-local research skill after proving the replacement

**Deferred execution:** Execute this task only from the master plan's post-integration cleanup step, after central storage migration, Airflow wiring, the disposable daily-run failure proof, and the Docker proof have passed. It is intentionally not part of the runtime prerequisite gate.

**Files:**
- Delete: `.agents/skills/freqtrade-strategy-research-loop/SKILL.md`
- Delete: `.agents/skills/freqtrade-strategy-research-loop/reference.md`
- Delete: `.research/` after archive/integrity verification
- Modify: `README.md`
- Modify: `tests/pi-strategy-research-contract.mjs`
- Modify: `tests/test_research_docker.py`
- Create: `tests/test_research_cleanup.py`
- Modify: `.dockerignore` if the deleted path is currently included

**Interfaces:**
- The runner uses `prompts/strategy-research.md` and its recorded SHA-256.
- The extension registers one runtime tool and reads the canonical prompt for the manual command.
- Docker succeeds when `/pi/agent-source` contains no repo-local research skill.

- [ ] **Step 1: Add deletion-gate contract tests before deleting files**

Add assertions that active source files contain no `.agents/skills/freqtrade-strategy-research-loop` path, that `scripts/research_loop.py` imports the canonical prompt loader, and that the Docker contract does not copy or require the repo skill. Keep historical design documents unchanged; the active-source scan covers `research_runtime/`, `scripts/`, `.pi/`, `prompts/`, `Dockerfile.research`, `compose.yaml`, `Makefile`, and the non-cleanup tests. Build the cleanup test's path from `Path(".agents") / "skills" / "freqtrade-strategy-research-loop"` so the test itself does not make the active-reference assertion fail.

- [ ] **Step 2: Run the gate and verify it fails while the skill exists**

```bash
node --test tests/pi-strategy-research-contract.mjs
```

Expected: the deletion-gate assertion fails because `.agents/skills/freqtrade-strategy-research-loop/` still exists.

- [ ] **Step 3: Delete the repo-local skill and archive legacy research state**

Remove only `.agents/skills/freqtrade-strategy-research-loop/`. Before removing `.research/`, create the immutable archive record with `find .research -type f -print0 | sort -z | xargs -0 sha256sum > "$BACKUP_ROOT/legacy-research.sha256"`, compare the legacy import counts with `user_data/research-migration.json`, and run `rg -n --hidden --glob '!docs/**' '\.research' research_runtime scripts .pi prompts Dockerfile.research compose.yaml Makefile README.md AGENTS.md tests` to verify that no active code imports it. Then remove `.research/` (including generated caches), while retaining `research_runtime/migrate_legacy.py` and the migration report until the central-state migration is accepted. Update README manual instructions to say that the daily path is Airflow → pinned Docker runner → canonical prompt → runtime, and that `make research-cycle` is a local debug path. Do not remove system skills or touch `data-opportunity-lab`.

- [ ] **Step 4: Run the full repository contract suite**

```bash
node --test tests/pi-strategy-research-contract.mjs
uv run pytest -q
uv run ruff check .
uv run python -m compileall -q research_runtime scripts src tests
```

`tests/test_research_cleanup.py` must assert that `.research/` is absent and that `research_runtime/migrate_legacy.py` remains importable. Expected: PASS with no active skill references and no runtime behavior change outside the new lifecycle/preflight contracts.

- [ ] **Step 5: Run the Docker proof without the repo skill**

Build and render using the isolated research image after the storage-path plan has supplied explicit state/artifact mounts:

```bash
docker build -f Dockerfile.research -t freqtrade-research:skillless .
docker compose --profile research config --quiet
```

Run the existing isolated-mount/help smoke test and assert the container can start Pi with a disposable `/tmp/pi-agent` that has no repo skill. Do not start `freqtrade-demo`, `freqtrade-live`, dry-run, or live services.

- [ ] **Step 6: Commit the retirement**

```bash
git add -A -- .
git commit -m "refactor: retire repo-local research skill"
```

## Verification checklist

- `uv run pytest -q` passes with the existing strategy/risk regressions.
- `node --test tests/pi-strategy-research-contract.mjs` passes.
- `uv run ruff check .` and compileall pass.
- Schema-v4 integrity and foreign-key checks pass on a copied v3 database.
- Reconciliation is idempotent and recovery attempts never exceed one.
- Conclusive candidate preflight failure creates no OOS consumption rows.
- Every Airflow run summary has a terminal `completed_at`, including preflight failures.
- Docker build/help/isolation pass without the repo-local research skill.
