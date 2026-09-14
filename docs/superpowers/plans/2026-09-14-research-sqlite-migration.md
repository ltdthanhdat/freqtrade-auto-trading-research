# Research SQLite Namespace and Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move research, validation-state, and Airflow SQLite files into project-namespaced persistent directories with explicit path configuration, integrity-checked migration, and a tested rollback procedure.

**Architecture:** Add one small path module that resolves explicit environment overrides and defaults to `~/workspace/iac/sqlite/freqtrade-auto-trading-research/`. Use a standard-library SQLite backup/audit utility for research and validation-state files, while Airflow keeps its runtime volume but stores `airflow.db` in `~/workspace/iac/sqlite/airflow/`. Update mounts and operator commands only after copied databases pass logical and integrity checks.

**Tech Stack:** Python 3.11, `sqlite3.Connection.backup`, SQLite PRAGMAs, Make, Docker Compose, Node contract tests, POSIX permissions.

**Spec:** `docs/superpowers/specs/2026-09-14-daily-research-orchestration-storage-design.md`

## Global Constraints

- Canonical research state is `research.sqlite`; validation control state is `validation-state.sqlite`; Airflow metadata is `airflow.db`.
- No single shared SQLite file is used across services/projects.
- Research code/config/policy/snapshots remain read-only in the research runner; only the dedicated state directory and artifact root are writable.
- SQLite migration is performed only while writers are stopped and always creates a rollback backup.
- `PRAGMA integrity_check` and `PRAGMA foreign_key_check` must pass before and after migration.
- Do not migrate Freqtrade trade databases, modify strategy semantics, or touch `data-opportunity-lab`.
- Do not touch unrelated untracked `iac/portainer/` or `iac/docs/issues/` content.

---

### Task 1: Introduce explicit project state path resolution

**Files:**
- Create: `research_runtime/paths.py`
- Modify: `research_runtime/cli.py`
- Modify: `research_runtime/dashboard.py`
- Modify: `scripts/research_loop.py`
- Modify: `scripts/validation_core.py` only where a default state path is constructed
- Modify: `Makefile`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Test: `tests/test_research_cli.py`
- Test: `tests/test_research_loop.py`
- Test: `tests/test_runtime_paths.py`

**Interfaces:**
- `default_state_dir() -> Path` returns the expanded `RESEARCH_STATE_DIR` when set, otherwise `Path.home() / "workspace/iac/sqlite/freqtrade-auto-trading-research"`; an explicitly empty override raises `ValueError`.
- `research_db_path() -> Path` returns the expanded `RESEARCH_DB` when set, otherwise `default_state_dir() / "research.sqlite"`.
- `validation_state_db_path() -> Path` returns the expanded `VALIDATION_STATE_DB` when set, otherwise `default_state_dir() / "validation-state.sqlite"`.
- `research_artifact_root() -> Path` returns the expanded `RESEARCH_ARTIFACT_ROOT` when set, otherwise `Path("user_data/research-artifacts")`.
- Empty environment values are rejected with `ValueError`; returned paths are expanded but not required to exist.

- [ ] **Step 1: Write failing path-resolution tests**

Create `tests/test_runtime_paths.py`:

```python
from pathlib import Path

import pytest

from research_runtime import paths


def test_default_paths_use_project_namespace(monkeypatch):
    monkeypatch.delenv("RESEARCH_STATE_DIR", raising=False)
    monkeypatch.delenv("RESEARCH_DB", raising=False)
    monkeypatch.delenv("VALIDATION_STATE_DB", raising=False)
    monkeypatch.delenv("RESEARCH_ARTIFACT_ROOT", raising=False)

    assert paths.research_db_path() == Path.home() / "workspace/iac/sqlite/freqtrade-auto-trading-research/research.sqlite"
    assert paths.validation_state_db_path() == Path.home() / "workspace/iac/sqlite/freqtrade-auto-trading-research/validation-state.sqlite"
    assert paths.research_artifact_root() == Path("user_data/research-artifacts")


def test_explicit_file_overrides_win(monkeypatch, tmp_path):
    research = tmp_path / "research.sqlite"
    validation = tmp_path / "validation.sqlite"
    monkeypatch.setenv("RESEARCH_DB", str(research))
    monkeypatch.setenv("VALIDATION_STATE_DB", str(validation))

    assert paths.research_db_path() == research
    assert paths.validation_state_db_path() == validation


@pytest.mark.parametrize("name", ["RESEARCH_STATE_DIR", "RESEARCH_DB", "VALIDATION_STATE_DB", "RESEARCH_ARTIFACT_ROOT"])
def test_empty_path_override_is_rejected(monkeypatch, name):
    monkeypatch.setenv(name, "")

    with pytest.raises(ValueError, match=name):
        getattr(paths, {
            "RESEARCH_STATE_DIR": "default_state_dir",
            "RESEARCH_DB": "research_db_path",
            "VALIDATION_STATE_DB": "validation_state_db_path",
            "RESEARCH_ARTIFACT_ROOT": "research_artifact_root",
        }[name])()
```

Update existing CLI/default tests to assert that an explicit `--db` still wins over the default. Add a dashboard/default test that the read model receives the resolved database path, not a hardcoded repo-local path.

- [ ] **Step 2: Run focused tests and verify failure**

```bash
uv run pytest tests/test_runtime_paths.py tests/test_research_cli.py tests/test_research_loop.py -q
```

Expected: FAIL because the path module and env-aware defaults do not exist.

- [ ] **Step 3: Implement the path module**

Use a private `_env_path(name: str) -> Path | None` that distinguishes an unset variable from an empty one, expands `~`, and returns a resolved lexical path without creating it. Keep artifact/data roots separate from SQLite state. Update default arguments in `research_runtime.cli.main`, `research_runtime.dashboard.main`, and `scripts.research_loop.parse_args` to call the functions at parse time rather than binding a mutable global path.

- [ ] **Step 4: Update Make and operator documentation**

Replace the active Make defaults with:

```make
RESEARCH_STATE_DIR ?= $(HOME)/workspace/iac/sqlite/freqtrade-auto-trading-research
RESEARCH_DB ?= $(RESEARCH_STATE_DIR)/research.sqlite
VALIDATION_STATE_DB ?= $(RESEARCH_STATE_DIR)/validation-state.sqlite
RESEARCH_ARTIFACT_ROOT ?= user_data/research-artifacts
```

Pass `RESEARCH_ARTIFACT_ROOT` to the dashboard and supervisor. Update README and `AGENTS.md` source-of-truth sections to name the central files. Leave historical design/plan documents that describe old migrations unchanged; active commands and instructions must no longer default to `user_data/research.sqlite`.

- [ ] **Step 5: Run focused tests and commit**

```bash
uv run pytest tests/test_runtime_paths.py tests/test_research_cli.py tests/test_research_loop.py tests/test_research_dashboard.py -q
```

Expected: PASS.

```bash
git add research_runtime/paths.py research_runtime/cli.py research_runtime/dashboard.py scripts/research_loop.py Makefile README.md AGENTS.md tests/test_runtime_paths.py tests/test_research_cli.py tests/test_research_loop.py tests/test_research_dashboard.py
git commit -m "feat: namespace research state paths"
```

---

### Task 2: Add integrity-checked SQLite backup and migration tooling

**Files:**
- Create: `scripts/migrate_sqlite_state.py`
- Create: `tests/test_sqlite_state_migration.py`
- Modify: `Makefile` with `state-audit`, `state-backup`, and `state-migrate` targets
- Create: `/home/datlt/workspace/iac/sqlite/.gitignore` during the operational setup step

**Interfaces:**
- `audit_database(path: Path) -> dict[str, object]` returns `path`, `integrity_check`, `foreign_key_errors`, `user_version`, and sorted per-table row counts.
- `backup_database(source: Path, destination: Path) -> dict[str, object]` uses `sqlite3.Connection.backup`, creates a mode-`0600` destination, and returns source/destination audits plus logical row-count comparison.
- `migrate_database(source: Path, destination: Path, backup_root: Path) -> dict[str, object]` refuses a missing source, same source/destination, or existing destination unless `--replace` is explicit; it backs up the source first, copies through SQLite backup API, audits both copies, and writes a JSON migration report.
- CLI options are `--source`, `--destination`, `--backup-root`, `--report`, `--replace`, and `--verify-only`.

- [ ] **Step 1: Write failing migration tests**

Create a generic database fixture with two tables, one foreign key, and rows. Add:

```python
def test_backup_uses_sqlite_backup_and_preserves_logical_state(tmp_path):
    source = make_sqlite_fixture(tmp_path / "source.sqlite")
    destination = tmp_path / "state" / "research.sqlite"

    result = backup_database(source, destination)

    assert result["destination"]["integrity_check"] == "ok"
    assert result["destination"]["foreign_key_errors"] == []
    assert result["source"]["table_counts"] == result["destination"]["table_counts"]
    assert destination.stat().st_mode & 0o777 == 0o600


def test_migration_refuses_existing_destination_without_replace(tmp_path):
    source = make_sqlite_fixture(tmp_path / "source.sqlite")
    destination = make_sqlite_fixture(tmp_path / "destination.sqlite")

    with pytest.raises(FileExistsError):
        migrate_database(source, destination, tmp_path / "backups")


def test_verify_reports_corrupt_or_foreign_key_invalid_database(tmp_path):
    path = make_sqlite_fixture(tmp_path / "state.sqlite")
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("INSERT INTO child(parent_id) VALUES (999)")

    audit = audit_database(path)

    assert audit["foreign_key_errors"]
```

- [ ] **Step 2: Run migration tests and verify failure**

```bash
uv run pytest tests/test_sqlite_state_migration.py -q
```

Expected: FAIL because the migration module does not exist.

- [ ] **Step 3: Implement auditable backup/migration**

Open source and destination connections with row factories, run `PRAGMA integrity_check` and `PRAGMA foreign_key_check`, count only user tables, and reject a source whose checks fail. Use a timestamped backup filename below `backup_root`, call `source_connection.backup(destination_connection)`, set destination permissions to `0600`, and compare table counts after copy. Write reports with canonical sorted JSON and an ending newline; never delete or modify the source.

- [ ] **Step 4: Add safe Make targets and ignore runtime files**

Add targets that require explicit variables:

```make
state-audit:
	$(PYTHON) -m scripts.migrate_sqlite_state --source "$(RESEARCH_DB)" --verify-only

state-backup:
	@test -n "$(BACKUP_ROOT)" || { echo "BACKUP_ROOT is required" >&2; exit 1; }
	$(PYTHON) -m scripts.migrate_sqlite_state --source "$(RESEARCH_DB)" --destination "$(BACKUP_ROOT)/research.sqlite" --backup-root "$(BACKUP_ROOT)"

state-migrate:
	@test -n "$(SOURCE_DB)" || { echo "SOURCE_DB is required" >&2; exit 1; }
	@test -n "$(DESTINATION_DB)" || { echo "DESTINATION_DB is required" >&2; exit 1; }
	@test -n "$(BACKUP_ROOT)" || { echo "BACKUP_ROOT is required" >&2; exit 1; }
	$(PYTHON) -m scripts.migrate_sqlite_state --source "$(SOURCE_DB)" --destination "$(DESTINATION_DB)" --backup-root "$(BACKUP_ROOT)" --report "$(REPORT)"
```

Create `~/workspace/iac/sqlite/.gitignore` with:

```gitignore
*
!.gitignore
```

Do not create or stage live `.sqlite` files in Git.

- [ ] **Step 5: Run migration tests and commit**

```bash
uv run pytest tests/test_sqlite_state_migration.py tests/test_research_migration.py -q
```

Expected: PASS.

```bash
git add scripts/migrate_sqlite_state.py tests/test_sqlite_state_migration.py Makefile
git commit -m "feat: add audited sqlite migration tooling"
```

Create the ignored `iac/sqlite/.gitignore` as an operational file in the separate `iac` repository; do not stage unrelated untracked directories.

---

### Task 3: Update the research Compose boundary and local commands

**Files:**
- Modify: `compose.yaml`
- Modify: `Dockerfile.research` default command only if required by the explicit state path
- Modify: `Makefile`
- Modify: `tests/test_research_docker.py`
- Modify: `README.md`

**Interfaces:**
- `RESEARCH_STATE_DIR` is the host directory containing `research.sqlite` and SQLite sidecars; it mounts at `/state/research`.
- The research service invokes `--db /state/research/research.sqlite` and `--artifacts /workspace/user_data/research-artifacts`.
- The sealed snapshot root mounts read-only; the artifact root mounts read/write; the state directory mounts read/write; the repository source mount remains read-only.
- Demo/live services keep their existing full-workspace mounts and trade DB URLs; this task does not change their behavior.

- [ ] **Step 1: Write failing Compose path tests**

Extend `tests/test_research_docker.py`:

```python
def test_research_uses_namespaced_state_and_not_repo_local_database():
    compose = Path("compose.yaml").read_text()
    research = compose[compose.index("  research:") :]

    assert "RESEARCH_STATE_DIR" in research
    assert "/state/research" in research
    assert "--db" in research
    assert "/state/research/research.sqlite" in research
    assert "./user_data/research.sqlite" not in research
    assert "./user_data:/" not in research
```

- [ ] **Step 2: Run the Docker tests and verify failure**

```bash
uv run pytest tests/test_research_docker.py -q
```

Expected: FAIL because Compose currently binds `./user_data/research.sqlite`.

- [ ] **Step 3: Update Compose and Make paths**

Add environment values for `RESEARCH_STATE_DIR`, `RESEARCH_SNAPSHOT_ROOT`, and `RESEARCH_ARTIFACT_ROOT`. Mount the state directory at `/state/research`, snapshot root at `/workspace/user_data/data/snapshots:ro`, and artifact root at `/workspace/user_data/research-artifacts`. Keep the parent `user_data` tmpfs so unmounted worker data remains hidden. Set `RESEARCH_DB=/state/research/research.sqlite` and pass the same path explicitly in the command. This task owns the namespaced state/artifact mount; the snapshot plan owns only the prep/work-root bind and the sealed-snapshot read-only contract.

Update `compose-research` and the local `research-loop` target to use `$(RESEARCH_DB)` and `$(RESEARCH_ARTIFACT_ROOT)`. Add `SNAPSHOT_MANIFEST` to the loop command; the snapshot plan supplies its value.

- [ ] **Step 4: Render and run tests**

```bash
docker compose --profile research config --quiet
uv run pytest tests/test_research_docker.py tests/test_validation_manifest.py -q
```

Expected: PASS. Do not start a worker or trading service.

- [ ] **Step 5: Commit the research storage boundary**

```bash
git add compose.yaml Dockerfile.research Makefile README.md tests/test_research_docker.py tests/test_validation_manifest.py
git commit -m "fix: mount research state outside user data"
```

---

### Task 4: Move Airflow's metadata database to its namespace

**Files:**
- Modify: `/home/datlt/workspace/iac/airflow/compose.yaml`
- Modify: `/home/datlt/workspace/iac/airflow/.env.example`
- Modify: `/home/datlt/workspace/iac/airflow/README.md`
- Modify: `/home/datlt/workspace/iac/airflow/test/airflow-compose.test.js`
- Modify: `/home/datlt/workspace/iac/airflow/Makefile` with `db-audit` and `db-backup`

**Interfaces:**
- Airflow continues to use its existing `airflow_data` volume for password/runtime files.
- `AIRFLOW_SQLITE_DIR` mounts at `/opt/airflow/sqlite` and `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN` is `sqlite:////opt/airflow/sqlite/airflow.db`.
- The host directory is created with permissions allowing the Airflow container's `airflow` user to read/write the database while remaining inaccessible to unrelated containers.

- [ ] **Step 1: Write failing Airflow Compose assertions**

Extend the existing Node contract test:

```javascript
test('stores Airflow metadata in the central SQLite namespace', () => {
  const compose = fs.readFileSync('compose.yaml', 'utf8');

  assert.match(compose, /AIRFLOW_SQLITE_DIR/);
  assert.match(compose, /AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: sqlite:\/\/\/\/opt\/airflow\/sqlite\/airflow\.db/);
  assert.match(compose, /AIRFLOW_SQLITE_DIR[^\n]*:\/opt\/airflow\/sqlite/);
  assert.doesNotMatch(compose, /sqlite:\/\/\/\/opt\/airflow\/data\/airflow\.db/);
});
```

- [ ] **Step 2: Run the Airflow contract test and verify failure**

```bash
cd /home/datlt/workspace/iac/airflow
node --test test/airflow-compose.test.js
```

Expected: FAIL because the current connection points to `/opt/airflow/data/airflow.db`.

- [ ] **Step 3: Update Compose and environment documentation**

Add `AIRFLOW_SQLITE_DIR=/home/datlt/workspace/iac/sqlite/airflow` to `.env.example`, mount it at `/opt/airflow/sqlite`, and change the SQLAlchemy connection in the shared Airflow environment. Keep `airflow_data:/opt/airflow/data` for `simple_auth_manager_passwords.json`. Before startup, create the host directory and grant the image's `airflow` UID/GID write access; verify the UID from the pinned image rather than assuming the host user ID.

Add Make targets that stop Airflow before auditing/backing up and call the research repository's generic migration tool through an explicit `RESEARCH_REPO` path (never a copy of its SQL logic in this repository). Document restore order: stop services, replace the central DB from a verified backup, run `airflow db check`, then start `airflow-init` and services.

- [ ] **Step 4: Render, audit, and run the Airflow suite**

```bash
cd /home/datlt/workspace/iac/airflow
docker compose config --quiet
node --test
```

Expected: PASS. Do not delete the old Airflow volume until the first central-path startup and rollback check pass. The runtime keeps `airflow_data` for password/runtime files; only the metadata database moves to the central bind.

- [ ] **Step 5: Commit the Airflow storage path in the IaC repository**

```bash
cd /home/datlt/workspace/iac
git add airflow/compose.yaml airflow/.env.example airflow/README.md airflow/test/airflow-compose.test.js airflow/Makefile
git commit -m "feat: namespace airflow sqlite metadata"
```

Do not stage `portainer/` or `docs/issues/`.

## Migration and rollback verification

Run this sequence only during a maintenance window with writers stopped:

```bash
mkdir -p "$HOME/workspace/iac/sqlite/backups"
cd /home/datlt/workspace/freqtrade-auto-trading-research
uv run python -m scripts.migrate_sqlite_state \
  --source user_data/research.sqlite \
  --destination "$HOME/workspace/iac/sqlite/freqtrade-auto-trading-research/research.sqlite" \
  --backup-root "$HOME/workspace/iac/sqlite/backups/research-$(date -u +%Y%m%dT%H%M%SZ)" \
  --report "$HOME/workspace/iac/sqlite/backups/research-migration.json"
```

Repeat for `validation-state.sqlite` with its own backup directory. For Airflow, back up the database from the stopped `airflow_data` volume into `~/workspace/iac/sqlite/backups/airflow-$(date -u +%Y%m%dT%H%M%SZ)/`, copy it through the same tool, and run `airflow db check` against `/opt/airflow/sqlite/airflow.db`.

Rollback is:

1. stop all writers/services;
2. audit the central database and select the last verified backup;
3. copy the backup back to the old or central path using SQLite backup API, never an unverified byte copy;
4. restore the previous env/Compose path;
5. run integrity, foreign-key, row-count, and application smoke checks;
6. retain the failed central copy for diagnosis.

Do not delete the old database or volume until central-path startup, dashboard read-only access, research CLI access, Airflow startup, and rollback checks all pass.
