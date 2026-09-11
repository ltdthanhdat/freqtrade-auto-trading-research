# Research Runtime and Legacy Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the canonical SQLite research runtime, import existing SMC/RSI research, and remove `.research/` without weakening the current dry-run gate.

**Architecture:** A small `research_runtime` Python package owns schema creation, scoring, legal state transitions, cycle leases, and JSON-lines operations. Legacy Markdown and artifacts are imported once into a local SQLite database and verified before `.research/` is removed; the active approved identity moves to `config/` so existing dry-run validation remains reproducible.

**Tech Stack:** Python 3.11 standard library, SQLite, pytest, existing Freqtrade validation modules.

**Spec:** `docs/superpowers/specs/2026-09-11-automated-strategy-research-design.md`

## Global Constraints

- `user_data/research.sqlite` is the only authoritative state for new research.
- Enable SQLite foreign keys on every connection and use `PRAGMA user_version` for schema migrations.
- One cycle admits at most 100 new sources, three hypotheses, and one candidate validation.
- Every accepted source retains canonical URL/DOI, provider, retrieval time, and fingerprint.
- Every state change appends `state_events`; no direct state overwrite is allowed.
- Do not delete `.research/` until import counts, hashes, integrity, and selected SMC/RSI records are verified.
- No task may start dry-run or live trading.

---

### Task 1: Research domain primitives and deterministic scoring

**Files:**
- Create: `research_runtime/__init__.py`
- Create: `research_runtime/core.py`
- Create: `tests/test_research_core.py`

**Interfaces:**
- Produces: `HypothesisState`, `CycleStatus`, `score_hypothesis(evidence_quality, reproducibility, ohlcv_transferability, novelty, falsifiability) -> int`, `next_state_allowed(current, target) -> bool`, and `canonical_json(value) -> str`.
- Consumes: only Python standard-library types.

- [ ] **Step 1: Write failing scoring and transition tests**

```python
from research_runtime.core import HypothesisState, next_state_allowed, score_hypothesis


def test_score_is_sum_of_frozen_dimensions():
    assert score_hypothesis(
        evidence_quality=30,
        reproducibility=20,
        ohlcv_transferability=15,
        novelty=10,
        falsifiability=5,
    ) == 80


def test_score_rejects_a_dimension_above_its_weight():
    with pytest.raises(ValueError, match="evidence_quality"):
        score_hypothesis(31, 20, 15, 10, 5)


def test_review_is_the_only_path_to_dry_run_eligibility():
    assert next_state_allowed(HypothesisState.NEEDS_REVIEW, HypothesisState.APPROVED_FOR_DRY_RUN)
    assert not next_state_allowed(HypothesisState.TESTING, HypothesisState.APPROVED_FOR_DRY_RUN)
```

- [ ] **Step 2: Run the focused test and confirm import failure**

Run: `uv run pytest tests/test_research_core.py -v`

Expected: FAIL because `research_runtime.core` does not exist.

- [ ] **Step 3: Implement the enums, fixed weights, and transition map**

```python
class HypothesisState(StrEnum):
    DRAFT = "DRAFT"
    SCORED = "SCORED"
    BACKLOG = "BACKLOG"
    QUEUED = "QUEUED"
    IMPLEMENTING = "IMPLEMENTING"
    TESTING = "TESTING"
    INCONCLUSIVE = "INCONCLUSIVE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REJECTED = "REJECTED"
    APPROVED_FOR_DRY_RUN = "APPROVED_FOR_DRY_RUN"


SCORE_LIMITS = {
    "evidence_quality": 30,
    "reproducibility": 25,
    "ohlcv_transferability": 20,
    "novelty": 15,
    "falsifiability": 10,
}


def score_hypothesis(evidence_quality, reproducibility, ohlcv_transferability, novelty, falsifiability):
    values = dict(zip(SCORE_LIMITS, (
        evidence_quality, reproducibility, ohlcv_transferability, novelty, falsifiability
    )))
    for name, value in values.items():
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= SCORE_LIMITS[name]:
            raise ValueError(f"invalid {name}")
    return sum(values.values())
```

Implement the approved state graph as an immutable mapping. Keep terminal states terminal; a retry creates or resumes a cycle/run rather than reopening a rejected hypothesis.

- [ ] **Step 4: Run the focused tests**

Run: `uv run pytest tests/test_research_core.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the domain primitives**

```bash
git add research_runtime/__init__.py research_runtime/core.py tests/test_research_core.py
git commit -m "feat: add research domain primitives"
```

### Task 2: SQLite schema, state events, budgets, and leases

**Files:**
- Create: `research_runtime/store.py`
- Create: `tests/test_research_store.py`

**Interfaces:**
- Consumes: `HypothesisState`, `CycleStatus`, `next_state_allowed`, and `canonical_json` from `research_runtime.core`.
- Produces: `ResearchStore(path)`, `start_or_resume_cycle(now) -> dict`, `transition_hypothesis(...)`, `insert_source(...)`, `insert_hypothesis(...)`, `insert_experiment(...)`, and `record_run(...)`.

- [ ] **Step 1: Write failing schema and integrity tests**

```python
def test_store_creates_exact_v1_tables(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    with store.connect() as connection:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert tables == {
            "cycles", "sources", "hypotheses", "hypothesis_sources",
            "experiments", "runs", "state_events",
        }
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
```

Add tests proving canonical URL and DOI uniqueness, the 100/3/1 budgets, illegal transition rejection, append-only state history, live-lease exclusion, and expired-lease resume.

- [ ] **Step 2: Run the store tests and confirm failure**

Run: `uv run pytest tests/test_research_store.py -v`

Expected: FAIL because `ResearchStore` is missing.

- [ ] **Step 3: Implement schema version 1 in one transaction**

Use `sqlite3.connect`, `row_factory = sqlite3.Row`, `PRAGMA foreign_keys=ON`, and these keys:

```sql
CREATE TABLE cycles (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  stage TEXT NOT NULL,
  source_count INTEGER NOT NULL DEFAULT 0 CHECK(source_count BETWEEN 0 AND 100),
  hypothesis_count INTEGER NOT NULL DEFAULT 0 CHECK(hypothesis_count BETWEEN 0 AND 3),
  candidate_count INTEGER NOT NULL DEFAULT 0 CHECK(candidate_count BETWEEN 0 AND 1),
  lease_until TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE sources (
  id TEXT PRIMARY KEY,
  cycle_id TEXT NOT NULL REFERENCES cycles(id),
  provider TEXT NOT NULL,
  canonical_url TEXT,
  doi TEXT,
  title TEXT NOT NULL,
  excerpt TEXT NOT NULL,
  license TEXT,
  retrieved_at TEXT NOT NULL,
  fingerprint TEXT NOT NULL UNIQUE,
  metadata_json TEXT NOT NULL,
  UNIQUE(provider, canonical_url),
  UNIQUE(doi)
);
```

Use these exact remaining tables. Store JSON as canonical text and validate it before insertion. Use `BEGIN IMMEDIATE` only for short lease/budget/transition transactions; never hold a write transaction during network or backtest work.

```sql
CREATE TABLE hypotheses (
  id TEXT PRIMARY KEY,
  cycle_id TEXT NOT NULL REFERENCES cycles(id),
  thesis TEXT NOT NULL,
  mechanism TEXT NOT NULL,
  market_scope TEXT NOT NULL,
  required_data_json TEXT NOT NULL,
  falsifier TEXT NOT NULL,
  evidence_quality INTEGER NOT NULL,
  reproducibility INTEGER NOT NULL,
  ohlcv_transferability INTEGER NOT NULL,
  novelty INTEGER NOT NULL,
  falsifiability INTEGER NOT NULL,
  total_score INTEGER NOT NULL CHECK(total_score BETWEEN 0 AND 100),
  state TEXT NOT NULL,
  candidate_path TEXT,
  candidate_sha256 TEXT,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE hypothesis_sources (
  hypothesis_id TEXT NOT NULL REFERENCES hypotheses(id),
  source_id TEXT NOT NULL REFERENCES sources(id),
  stance TEXT NOT NULL CHECK(stance IN ('SUPPORT', 'CONTRADICT')),
  note TEXT NOT NULL,
  PRIMARY KEY(hypothesis_id, source_id, stance)
);

CREATE TABLE experiments (
  id TEXT PRIMARY KEY,
  cycle_id TEXT NOT NULL REFERENCES cycles(id),
  hypothesis_id TEXT NOT NULL REFERENCES hypotheses(id),
  parent_strategy TEXT NOT NULL,
  parent_sha256 TEXT NOT NULL,
  changed_variable TEXT NOT NULL,
  config_path TEXT NOT NULL,
  config_sha256 TEXT NOT NULL,
  pairs_json TEXT NOT NULL,
  timeframes_json TEXT NOT NULL,
  timeframe_detail TEXT NOT NULL,
  snapshot_path TEXT NOT NULL,
  snapshot_sha256 TEXT NOT NULL,
  policy_path TEXT NOT NULL,
  policy_sha256 TEXT NOT NULL,
  strategy_name TEXT NOT NULL,
  strategy_path TEXT NOT NULL,
  start_at TEXT NOT NULL,
  end_at TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE runs (
  id TEXT PRIMARY KEY,
  experiment_id TEXT NOT NULL REFERENCES experiments(id),
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  verdict TEXT,
  metrics_json TEXT NOT NULL,
  artifact_manifest_json TEXT NOT NULL,
  error_code TEXT,
  created_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE TABLE state_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  from_state TEXT,
  to_state TEXT NOT NULL,
  actor TEXT NOT NULL,
  reason TEXT NOT NULL,
  cycle_id TEXT NOT NULL REFERENCES cycles(id),
  run_id TEXT REFERENCES runs(id),
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
```

- [ ] **Step 4: Implement legal transitions and append-only events**

Within one transaction: read current hypothesis state, validate the edge, append `state_events`, then update `hypotheses.state`. Reject a missing actor or reason. Review events accept only `local_user` as actor in version 1.

- [ ] **Step 5: Run store and existing SQLite tests**

Run: `uv run pytest tests/test_research_store.py tests/test_runtime_protections.py -v`

Expected: PASS.

- [ ] **Step 6: Commit the store**

```bash
git add research_runtime/store.py tests/test_research_store.py
git commit -m "feat: add SQLite research store"
```

### Task 3: Typed JSON-lines runtime boundary

**Files:**
- Create: `research_runtime/service.py`
- Create: `research_runtime/cli.py`
- Create: `tests/test_research_cli.py`

**Interfaces:**
- Consumes: `ResearchStore` and domain primitives.
- Produces: `ResearchService(store: ResearchStore, artifact_root: Path, collectors: dict | None = None, validator: Callable | None = None)`, `ResearchService.call(tool: str, payload: dict) -> dict`, and `python -m research_runtime.cli` accepting one JSON object per stdin line.

- [ ] **Step 1: Write failing CLI contract tests**

```python
def test_cli_returns_one_structured_response_per_request(tmp_path):
    request = {"tool": "start_or_resume_cycle", "payload": {"now": "2026-09-11T08:00:00Z"}}
    result = run_cli(tmp_path, request)
    assert result["ok"] is True
    assert result["cycle"]["status"] == "RUNNING"


def test_cli_rejects_unknown_fields(tmp_path):
    result = run_cli(tmp_path, {"tool": "start_or_resume_cycle", "payload": {"extra": 1}})
    assert result == {"ok": False, "error": {"code": "validation_error", "details": ["unknown fields: extra"]}}
```

Also test malformed JSON, unknown operations, missing required fields, and non-zero process exit only for transport failure. Domain rejections return `ok: false` JSON so Pi receives the precise reason.
Add proposal tests proving missing source IDs or falsifier are rejected, unsupported required data transitions to `BACKLOG`, and a normalized duplicate mechanism attaches new evidence to the existing hypothesis without consuming another hypothesis-budget slot.

- [ ] **Step 2: Run the CLI tests and confirm failure**

Run: `uv run pytest tests/test_research_cli.py -v`

Expected: FAIL because the service and CLI do not exist.

- [ ] **Step 3: Implement an explicit operation registry**

```python
OPERATIONS = {
    "start_or_resume_cycle": service.start_or_resume_cycle,
    "load_context": service.load_context,
    "record_source_assessment": service.record_source_assessment,
    "propose_hypothesis": service.propose_hypothesis,
    "record_interpretation": service.record_interpretation,
    "finalize_cycle": service.finalize_cycle,
}
```

Each handler declares its exact allowed and required keys with small sets; reject unknown keys before calling the store. Later plans add `collect_sources`, `write_candidate`, and `start_validation` to this same registry.

- [ ] **Step 4: Run CLI and store tests**

Run: `uv run pytest tests/test_research_cli.py tests/test_research_store.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the typed runtime**

```bash
git add research_runtime/service.py research_runtime/cli.py tests/test_research_cli.py
git commit -m "feat: add typed research runtime"
```

### Task 4: Legacy importer and migration report

**Files:**
- Create: `research_runtime/migrate_legacy.py`
- Create: `tests/test_research_migration.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `ResearchStore` plus a source root and artifact destination.
- Produces: `import_legacy(source_root, store, artifact_root) -> MigrationReport` and CLI flags `--source`, `--db`, `--artifacts`, `--report`, `--backup`, and `--verify-only`.

- [ ] **Step 1: Write failing importer tests with a miniature SMC/RSI tree**

```python
def make_legacy_fixture(tmp_path):
    root = tmp_path / ".research"
    for family, suffix in (("smc", "001"), ("rsi", "002")):
        base = root / family
        (base / "hypotheses").mkdir(parents=True)
        (base / "experiments").mkdir()
        (base / "runs").mkdir()
        (base / "hypotheses" / f"H-{suffix}.md").write_text(f"# H-{suffix}\nEvidence body\n")
        (base / "experiments" / f"EXP-{suffix}.md").write_text(
            f"# EXP-{suffix}\nHypothesis: H-{suffix}\n"
        )
        (base / "runs" / f"run-{suffix}.json").write_text('{"verdict":"PASS"}\n')
    return root


def test_importer_preserves_bodies_and_artifact_hashes(tmp_path):
    legacy = make_legacy_fixture(tmp_path)
    report = import_legacy(legacy, ResearchStore(tmp_path / "research.sqlite"), tmp_path / "artifacts")
    assert report.hypotheses == 2
    assert report.experiments == 2
    assert report.artifacts == 2
    assert report.unresolved_links == ()
    assert report.hash_mismatches == ()
```

Add an idempotency test and a test that an unresolved hypothesis/experiment link makes verification fail without deleting the source tree.

- [ ] **Step 2: Run migration tests and confirm failure**

Run: `uv run pytest tests/test_research_migration.py -v`

Expected: FAIL because the importer is missing.

- [ ] **Step 3: Implement deterministic legacy mapping**

- Strategy family is the first directory below `.research`.
- Hypothesis/experiment IDs come from filename stems.
- Preserve the complete Markdown body in the record metadata.
- Resolve experiment links from explicit `H...` references first, then matching normalized numeric suffix; report ambiguity rather than guessing.
- Copy candidate, run, JSON, ZIP, CSV, and text evidence into `research-artifacts/legacy/<family>/...` with original relative paths.
- Hash before and after copy and store the manifest in a legacy run record.
- Re-running the importer updates nothing when fingerprints and hashes already exist.

- [ ] **Step 4: Ignore local runtime data**

Add:

```gitignore
user_data/research.sqlite*
user_data/research-artifacts/
user_data/research-backups/
```

- [ ] **Step 5: Run the importer tests and a non-destructive real import**

Run:

```bash
uv run pytest tests/test_research_migration.py -v
uv run python -m research_runtime.migrate_legacy \
  --source .research \
  --db user_data/research.sqlite \
  --artifacts user_data/research-artifacts \
  --report user_data/research-migration.json
```

Expected: tests PASS; the command reports zero unresolved links and zero hash mismatches without changing `.research/`.

- [ ] **Step 6: Verify the real database and report**

Run:

```bash
uv run python -m research_runtime.migrate_legacy \
  --source .research \
  --db user_data/research.sqlite \
  --artifacts user_data/research-artifacts \
  --report user_data/research-migration.json \
  --verify-only
```

Expected: verify-only reports `integrity_check: ok`, an empty `foreign_key_errors` list, and no count/hash/link mismatch. The command performs both PRAGMAs through Python's standard-library `sqlite3` module.

- [ ] **Step 7: Commit the importer before deleting legacy files**

```bash
git add research_runtime/migrate_legacy.py tests/test_research_migration.py .gitignore
git commit -m "feat: import legacy research into SQLite"
```

### Task 5: Move active identity and retire `.research`

**Files:**
- Create: `config/approved-baseline-identity.json`
- Modify: `Makefile`
- Modify: `README.md`
- Delete: `.research/`
- Test: `tests/test_validation_manifest.py`

**Interfaces:**
- Consumes: verified `user_data/research.sqlite`, migration report, and current approved identity.
- Produces: existing validation targets with no `.research` path dependency.

- [ ] **Step 1: Add a failing path regression test**

Add a test that reads `Makefile` and `README.md` and asserts neither active validation command points into `.research/`, while the default approved identity is `config/approved-baseline-identity.json` and run output is under `user_data/research-artifacts/validation`.

- [ ] **Step 2: Run the regression test and confirm failure**

Run: `uv run pytest tests/test_validation_manifest.py -v`

Expected: FAIL on the old `.research/smc_fvg_pinbar/...` paths.

- [ ] **Step 3: Copy the current approved identity and update commands**

Create `config/approved-baseline-identity.json` with the exact contents of the current active identity; the old tracked copy is removed with `.research/` only after backup verification. Change:

```make
APPROVED_IDENTITY ?= config/approved-baseline-identity.json
RESEARCH_RUNS_DIR ?= user_data/research-artifacts/validation
```

Pass `--runs-dir $(RESEARCH_RUNS_DIR)` from `validate-snapshot`. Update README source-of-truth and validation examples to point to SQLite/dashboard and the new identity path.

- [ ] **Step 4: Create a recoverable SQLite backup**

Run:

```bash
uv run python -m research_runtime.migrate_legacy \
  --db user_data/research.sqlite \
  --backup user_data/research-backups/pre-research-retirement.sqlite \
  --verify-only
```

Expected: the importer creates the backup parent, copies with `sqlite3.Connection.backup`, verifies both databases, and reports `integrity_check: ok` for each.

- [ ] **Step 5: Remove the verified legacy tree and run the full suite**

Run:

```bash
git rm -r .research
uv run pytest -q
```

Expected: all tests PASS and no tracked runtime command requires `.research/`.

- [ ] **Step 6: Commit legacy retirement**

```bash
git add config/approved-baseline-identity.json Makefile README.md tests/test_validation_manifest.py
git commit -m "refactor: move research state to SQLite"
```
