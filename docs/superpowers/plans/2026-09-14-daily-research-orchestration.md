# Daily Research Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved daily Freqtrade research pipeline across the research repository, the DAG repository, and the Airflow runtime while preserving research safety and trading boundaries.

**Architecture:** Execute four independently testable implementation plans in dependency order: runtime contracts/lifecycle, data snapshot preparation, SQLite namespace migration, and Airflow DAG wiring. The final integration uses Airflow only for scheduling and Docker task orchestration, a pinned one-shot research image, sealed read-only snapshots, project-namespaced SQLite state, all-done reconciliation, and a terminal run summary.

**Tech Stack:** Python 3.11, Freqtrade, SQLite, pandas/Feather, Docker Compose, Airflow 3.3.1, DockerOperator, TypeScript Pi extension, pytest, Node test runner, git-sync.

**Spec:** `docs/superpowers/specs/2026-09-14-daily-research-orchestration-storage-design.md`

## Global Constraints

- No alpha tuning, hyperopt, parameter sweeps, pair expansion, post-OOS tuning, dry-run/live trading, or automatic promotion.
- Maximum 100 sources, 3 hypotheses, and 1 candidate per cycle; `required_data` is exactly `["OHLCV"]` for identity-bound plans.
- A complete plan, sealed ranking, claim-level provenance, candidate identity, Freqtrade preflight, and exactly-once OOS accounting are mandatory.
- Only one infrastructure recovery may reuse a cycle; conclusive validation outcomes are not infrastructure retries.
- Research containers are one-shot, `read_only`, bridge-networked, `stdin_open=false`, `tty=false`, and never start worker/demo/live processes.
- Only dedicated research state and artifact paths are writable; source/config/policy/sealed snapshots/credentials are read-only.
- Active SQLite files are under `~/workspace/iac/sqlite/`; historical docs may mention prior paths but active defaults may not.
- Preserve `src/strategies/`, `config/`, current Freqtrade paths, and strategy entry/stop/ROI/time/trailing/regime semantics.
- Do not touch `data-opportunity-lab`, `/home/datlt/workspace/iac/portainer/`, or `/home/datlt/workspace/iac/docs/issues/`.

## Child plans

1. `docs/superpowers/plans/2026-09-14-research-runtime-contracts.md`
2. `docs/superpowers/plans/2026-09-14-research-snapshot-preparation.md`
3. `docs/superpowers/plans/2026-09-14-research-sqlite-migration.md`
4. `docs/superpowers/plans/2026-09-14-airflow-daily-research-dag.md`

Each child plan contains its file map, interfaces, failing tests, implementation steps, verification commands, and commit boundary. Do not start a later child plan until its dependency gate below is green.

---

### Task 1: Create isolated execution workspaces before editing code

**Files:**
- No source files modified.
- Worktree: `.worktrees/daily-research-orchestration` in the research repository.

**Interfaces:**
- Research implementation changes are made from a clean branch/worktree based on `master` at the commit containing these implementation plans; record the exact `git rev-parse HEAD` before creating it.
- Airflow DAG changes are made in the existing clean `master` checkout at `/home/datlt/workspace/airflow-dags`.
- Airflow runtime changes are made in `/home/datlt/workspace/iac/airflow` without staging unrelated untracked paths.

- [ ] **Step 1: Verify the current baselines**

```bash
cd /home/datlt/workspace/freqtrade-auto-trading-research
git status --short --branch
cd /home/datlt/workspace/airflow-dags
git status --short --branch
cd /home/datlt/workspace/iac
git status --short --branch
```

Expected: research repository is clean at `master` ahead of `origin/master` only by approved commits; Airflow DAG repository is clean; the IaC repository still contains only the known untracked `portainer/` and `docs/issues/` directories.

- [ ] **Step 2: Create the research worktree using the required location**

```bash
cd /home/datlt/workspace/freqtrade-auto-trading-research
git worktree add .worktrees/daily-research-orchestration -b daily-research-orchestration master
```

Expected: the new worktree is clean and does not contain uncommitted source changes.

- [ ] **Step 3: Record the dependency order in the worktree**

```bash
cd /home/datlt/workspace/freqtrade-auto-trading-research/.worktrees/daily-research-orchestration
printf '%s\n' 'runtime-contracts -> snapshot-preparation -> sqlite-migration -> airflow-dag -> integration' > /tmp/daily-research-plan-order
```

No repository file is changed by this step; the order is an execution guard for the child plans.

---

### Task 2: Execute the runtime contract/lifecycle plan

**Files:**
- Follow: `docs/superpowers/plans/2026-09-14-research-runtime-contracts.md`
- Primary boundaries: `research_runtime/store.py`, `research_runtime/service.py`, `research_runtime/validation.py`, `scripts/research_loop.py`, `.pi/extensions/strategy-research.ts`, `prompts/strategy-research.md`.

**Interfaces:**
- Schema v4 lifecycle columns and `ResearchStore.heartbeat_cycle`/`reconcile_cycle` exist.
- `ResearchService` dispatches `heartbeat_cycle` and `reconcile_cycle` with unknown/missing field rejection.
- Candidate preflight rejects missing Freqtrade callbacks before OOS consumption.
- Prompt loading returns raw template SHA-256 and renders only the cycle/validation placeholders.
- Terminal run summaries are written under the sanitized Airflow run-key subdirectory of `user_data/research-artifacts/runs/`, including preparation failures before a cycle exists.

- [ ] **Step 1: Complete Tasks 1–3 of the runtime child plan**

Run the focused prompt, lifecycle, summary, and CLI tests after each task:

```bash
cd /home/datlt/workspace/freqtrade-auto-trading-research/.worktrees/daily-research-orchestration
uv run pytest tests/test_research_loop.py tests/test_research_store.py tests/test_research_service.py tests/test_research_reconciliation.py tests/test_research_run_summary.py tests/test_research_cli.py -q
```

Expected: PASS before candidate preflight or skill removal is attempted.

- [ ] **Step 2: Complete Task 4 of the runtime child plan (defer cleanup)**

```bash
cd /home/datlt/workspace/freqtrade-auto-trading-research/.worktrees/daily-research-orchestration
uv run pytest tests/test_research_validation.py tests/test_research_candidates.py tests/test_validation_regressions.py -q
node --test tests/pi-strategy-research-contract.mjs
```

Expected: the missing-`populate_exit_trend` regression is covered and active runtime code no longer depends on the repo-local research skill. Do not execute the runtime child plan's deferred Task 5 yet; the skill and `.research/` cleanup belongs to master Task 7 after integration.

- [ ] **Step 3: Run the runtime plan's full gate**

```bash
cd /home/datlt/workspace/freqtrade-auto-trading-research/.worktrees/daily-research-orchestration
uv run pytest -q
uv run ruff check .
uv run python -m compileall -q research_runtime scripts src tests
```

Expected: PASS. Review the diff and confirm no strategy semantics or Freqtrade path was changed.

---

### Task 3: Execute the snapshot preparation/container plan

**Files:**
- Follow: `docs/superpowers/plans/2026-09-14-research-snapshot-preparation.md`
- Primary boundaries: `scripts/seed_freqtrade_data.py`, `scripts/prepare_research_data.py`, `research_runtime/snapshots.py`, `compose.yaml`, `Makefile`.

**Interfaces:**
- `prepare` produces a sealed, hashed readiness manifest before the research runner starts.
- Every accepted pair has valid `30m`, `1h`, and `1m` OHLCV data with common coverage and enough folds.
- Data prep can write staging data; research can read only sealed snapshots.

- [ ] **Step 1: Complete the data-root and snapshot-manifest tasks**

```bash
cd /home/datlt/workspace/freqtrade-auto-trading-research/.worktrees/daily-research-orchestration
uv run pytest tests/test_seed_freqtrade_data.py tests/test_prepare_research_data.py tests/test_research_snapshots.py tests/test_validate_baseline.py -q
```

Expected: PASS, including failed-seed cleanup, no-overwrite, matching-manifest reuse, and insufficient-coverage cases.

- [ ] **Step 2: Complete the Docker separation task**

```bash
cd /home/datlt/workspace/freqtrade-auto-trading-research/.worktrees/daily-research-orchestration
docker compose --profile research config --quiet
uv run pytest tests/test_research_docker.py tests/test_validation_manifest.py -q
```

Expected: PASS. Inspect rendered mounts and verify no host-wide `user_data` mount is introduced.

- [ ] **Step 3: Run the combined research repository gate**

```bash
cd /home/datlt/workspace/freqtrade-auto-trading-research/.worktrees/daily-research-orchestration
uv run pytest -q
uv run ruff check .
```

Expected: PASS after both runtime and snapshot child plans are applied.

---

### Task 4: Execute the SQLite namespace/migration plan

**Files:**
- Follow: `docs/superpowers/plans/2026-09-14-research-sqlite-migration.md`
- Primary boundaries: `research_runtime/paths.py`, `scripts/migrate_sqlite_state.py`, research Compose/Make/README/AGENTS, and `/home/datlt/workspace/iac/airflow/`.

**Interfaces:**
- `research_db_path()`, `validation_state_db_path()`, and `research_artifact_root()` resolve explicit environment overrides.
- Research and validation defaults point to `~/workspace/iac/sqlite/freqtrade-auto-trading-research/`.
- Airflow metadata uses `/opt/airflow/sqlite/airflow.db` backed by `AIRFLOW_SQLITE_DIR` while keeping `airflow_data` runtime files.
- Migration produces backups, audits integrity/foreign keys, compares logical table counts, and never deletes source state.

- [ ] **Step 1: Complete path and migration tooling tasks in the research worktree**

```bash
cd /home/datlt/workspace/freqtrade-auto-trading-research/.worktrees/daily-research-orchestration
uv run pytest tests/test_runtime_paths.py tests/test_sqlite_state_migration.py tests/test_research_migration.py -q
```

Expected: PASS with temporary database fixtures and no real state touched.

- [ ] **Step 2: Complete research Compose path changes**

```bash
cd /home/datlt/workspace/freqtrade-auto-trading-research/.worktrees/daily-research-orchestration
docker compose --profile research config --quiet
uv run pytest tests/test_research_docker.py tests/test_validation_manifest.py -q
```

Expected: PASS with `/state/research/research.sqlite` and no active `user_data/research.sqlite` bind.

- [ ] **Step 3: Prepare central directories without creating tracked database files**

```bash
mkdir -p /home/datlt/workspace/iac/sqlite/airflow
mkdir -p /home/datlt/workspace/iac/sqlite/freqtrade-auto-trading-research
mkdir -p /home/datlt/workspace/iac/sqlite/backups
cat > /home/datlt/workspace/iac/sqlite/.gitignore <<'EOF'
*
!.gitignore
EOF
```

Expected: directories exist, `.gitignore` is the only intended tracked file, and no live database is staged.

- [ ] **Step 4: Run the maintenance-window migration**

Stop Airflow and research writers. Use the child plan's SQLite tool for `research.sqlite` and `validation-state.sqlite`, then audit both destinations. Back up the current Airflow database from the stopped `airflow_data` volume and copy it to `~/workspace/iac/sqlite/airflow/airflow.db` through SQLite backup API.

Expected: source and destination audits pass; table counts match; artifact references and cycle IDs remain unchanged.

- [ ] **Step 5: Complete and test the Airflow Compose change**

```bash
cd /home/datlt/workspace/iac/airflow
node --test
docker compose config --quiet
```

Expected: Airflow Compose points to `/opt/airflow/sqlite/airflow.db`, the runtime volume still provides authentication files, and no unrelated IaC files are staged.

- [ ] **Step 6: Commit each repository's storage changes separately**

```bash
cd /home/datlt/workspace/freqtrade-auto-trading-research/.worktrees/daily-research-orchestration
git add research_runtime/paths.py scripts/migrate_sqlite_state.py tests/test_runtime_paths.py tests/test_sqlite_state_migration.py compose.yaml Makefile README.md AGENTS.md tests/test_research_docker.py tests/test_validation_manifest.py
git commit -m "feat: migrate research state namespace"

cd /home/datlt/workspace/iac
git add sqlite/.gitignore airflow/compose.yaml airflow/.env.example airflow/README.md airflow/Makefile airflow/test/airflow-compose.test.js
git commit -m "feat: centralize sqlite runtime paths"
```

Do not stage `/home/datlt/workspace/iac/portainer/` or `/home/datlt/workspace/iac/docs/issues/`; do not push.

---

### Task 5: Execute the Airflow DAG plan

**Files:**
- Follow: `docs/superpowers/plans/2026-09-14-airflow-daily-research-dag.md`
- Primary boundary: `/home/datlt/workspace/airflow-dags/dags/freqtrade_strategy_research_daily.py`.

**Interfaces:**
- DAG tasks are `build_run_context`, `reconcile_stale_cycles`, `prepare_snapshot`, `run_research`, `reconcile_current`, and `publish_report_and_alert`.
- `prepare_snapshot` calls repository-owned data preparation; `run_research` calls the pinned image; reconciliation/report tasks run under `ALL_DONE`.
- The DAG has no SQLite imports, direct SQL, candidate logic, or trading commands.

- [ ] **Step 1: Complete DAG context and graph tasks**

```bash
cd /home/datlt/workspace/airflow-dags
npm test
python3 -m py_compile dags/*.py
```

Expected: PASS with the existing `airflow_smoke_test` still present and no `job_intelligence_daily.py` restored.

- [ ] **Step 2: Complete DockerOperator mount and command tasks**

```bash
cd /home/datlt/workspace/airflow-dags
npm test
python3 -m py_compile dags/freqtrade_strategy_research_daily.py
```

Expected: PASS; inspect the diff for `network_mode="bridge"`, restricted mounts, no Pi credentials on prep, and `mount_tmp_dir=False`.

- [ ] **Step 3: Complete all-done reconciliation/result tasks**

```bash
cd /home/datlt/workspace/airflow-dags
npm test
python3 -m py_compile dags/freqtrade_strategy_research_daily.py
```

Expected: PASS; conclusive `FAILED` is an exit-0 research result, while infrastructure/incomplete execution is eligible for one bounded retry and then reconciliation.

- [ ] **Step 4: Commit the DAG repository**

```bash
cd /home/datlt/workspace/airflow-dags
git add dags/freqtrade_strategy_research_daily.py README.md test/airflow-dags.test.js test/daily-research-dag.test.js
git commit -m "feat: orchestrate daily freqtrade research"
```

Do not push without explicit release approval.

---

### Task 6: Run the cross-repository integration gate before cleanup

**Files:**
- Modify only if a verification/documentation defect is found: `README.md`, test contract files, or Airflow runtime documentation.
- No strategy/config changes are permitted in this task.

**Interfaces:**
- The pinned research image contains the committed runtime/prompt code and can run with the repo-local skill absent after master Task 7.
- Central SQLite paths, sealed snapshot root, and artifact root are available to DockerOperator.
- A daily run produces a terminal `run-summary.json` even when preparation or research fails.

- [ ] **Step 1: Build and verify the research image from the reviewed commit**

```bash
cd /home/datlt/workspace/freqtrade-auto-trading-research/.worktrees/daily-research-orchestration
docker build -f Dockerfile.research -t freqtrade-research:daily-20260915 .
docker compose --profile research config --quiet
```

Expected: build succeeds without runtime npm installation, help/smoke checks pass, and the image does not require `.agents/skills/freqtrade-strategy-research-loop/`.

- [ ] **Step 2: Verify all repository tests**

```bash
cd /home/datlt/workspace/freqtrade-auto-trading-research/.worktrees/daily-research-orchestration
uv run pytest -q
uv run ruff check .
uv run python -m compileall -q research_runtime scripts src tests
node --test tests/pi-strategy-research-contract.mjs

cd /home/datlt/workspace/airflow-dags
npm test
python3 -m py_compile dags/*.py

cd /home/datlt/workspace/iac/airflow
node --test
docker compose config --quiet
```

Expected: every command passes.

- [ ] **Step 3: Verify git-sync and Airflow parsing**

Start/restart only the Airflow runtime after central DB permissions are set, wait for git-sync's `/opt/airflow/dags/current` link to publish the DAG commit, then run:

```bash
cd /home/datlt/workspace/iac/airflow
docker compose ps
docker compose exec -T airflow-api-server airflow dags list | grep freqtrade_strategy_research_daily
docker compose exec -T airflow-api-server airflow dags list | grep airflow_smoke_test
```

Expected: both DAGs parse; no live/demo Freqtrade service is started by Airflow.

- [ ] **Step 4: Run the existing no-network smoke check**

```bash
cd /home/datlt/workspace/iac/airflow
make smoke
```

Expected: the manual smoke DAG still uses `network_mode="none"` and succeeds. Do not trigger the daily research DAG with consumed historical OOS data.

- [ ] **Step 5: Run one disposable daily research failure test**

Use a new disposable state directory, snapshot root, artifact root, and new timerange/window. Trigger the daily DAG manually and force either an insufficient-data preparation result or a research-container failure. Verify:

```text
run-summary.json exists under the sanitized Airflow run-key directory below user_data/research-artifacts/runs/
summary.completed_at is non-null
no OOS consumption rows exist after preparation failure
an interrupted RUNNING cycle becomes INCOMPLETE after reconciliation
no worker/demo/live container exists
no dry-run/live command is present
```

Expected: Airflow's `reconcile_current` and `publish_report_and_alert` run despite the upstream failure.

- [ ] **Step 6: Audit active references before final cleanup**

```bash
cd /home/datlt/workspace/freqtrade-auto-trading-research/.worktrees/daily-research-orchestration
rg -n -i 'user_data/research\.sqlite|freqtrade-strategy-research-loop|semantic_scholar|dry-run|compose-live|freqtrade-live|freqtrade-demo' \
  research_runtime scripts .pi prompts Dockerfile.research compose.yaml Makefile README.md AGENTS.md tests
```

Expected: only intentionally documented prohibitions/legacy migration notes remain; no active command defaults to the old database or requires the deleted skill.

- [ ] **Step 7: Verify clean Git boundaries**

```bash
cd /home/datlt/workspace/freqtrade-auto-trading-research/.worktrees/daily-research-orchestration
git status --short
cd /home/datlt/workspace/airflow-dags
git status --short
cd /home/datlt/workspace/iac
git status --short
```

Expected: no accidental generated files, database files, secrets, `portainer/`, or `docs/issues/` changes are staged.

---

### Task 7: Retire the repo-local skill and legacy research tree after integration

**Files:**
- Follow the deferred Task 5 in `docs/superpowers/plans/2026-09-14-research-runtime-contracts.md`.
- No changes to strategy/configuration semantics.

**Interfaces:**
- Central SQLite migration, DAG wiring, Docker isolation, and the disposable daily-run proof have already passed.
- The canonical prompt, runtime contracts, and report path are active before deleting legacy guidance.

- [ ] **Step 1: Re-run the deletion-gate tests and Docker proof**

```bash
cd /home/datlt/workspace/freqtrade-auto-trading-research/.worktrees/daily-research-orchestration
node --test tests/pi-strategy-research-contract.mjs
uv run pytest -q
uv run ruff check .
docker build -f Dockerfile.research -t freqtrade-research:skillless .
```

Expected: the active contract suite passes, the image builds, and no worker/demo/live service is started.

- [ ] **Step 2: Archive and remove only approved legacy paths**

```bash
cd /home/datlt/workspace/freqtrade-auto-trading-research/.worktrees/daily-research-orchestration
BACKUP_ROOT="$HOME/workspace/iac/sqlite/backups/legacy-research-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_ROOT"
find .research -type f -print0 | sort -z | xargs -0 sha256sum > "$BACKUP_ROOT/legacy-research.sha256"
rm -rf .agents/skills/freqtrade-strategy-research-loop .research
```

Before running the removal command, compare the archived file count/hashes with `user_data/research-migration.json` and confirm `research_runtime/migrate_legacy.py` remains. Do not remove system skills, `research_runtime/migrate_legacy.py`, migration evidence, or any path in `data-opportunity-lab`.

- [ ] **Step 3: Run the post-cleanup gate and commit the research cleanup**

```bash
cd /home/datlt/workspace/freqtrade-auto-trading-research/.worktrees/daily-research-orchestration
node --test tests/pi-strategy-research-contract.mjs
uv run pytest -q
uv run ruff check .
uv run python -m compileall -q research_runtime scripts src tests
git diff --check
git add -A -- .
git commit -m "refactor: retire repo-local research skill"
```

Expected: no active skill references, `.research/` is absent, migration utility remains importable, and all tests/lint/compile checks pass.

## Definition of done

- The four child plans are complete and their commits are independently testable.
- The daily DAG is available in the DAG repository and git-sync parses it.
- Data preparation proves actual sufficiency before Pi/OOS and seals snapshots atomically.
- Runtime lifecycle is schema-v4, lease-owned, heartbeat-aware, recovery-bounded, and externally reconciled.
- Research and validation SQLite files are namespaced under `~/workspace/iac/sqlite/freqtrade-auto-trading-research/`; Airflow metadata is under `~/workspace/iac/sqlite/airflow/`.
- Every daily run has a terminal run summary, including preflight/container failures.
- Candidate Freqtrade load errors are rejected before OOS allocation.
- The repo-local research skill is removed only after active-reference, full-test, and Docker proof gates pass.
- No automatic promotion, dry-run/live trading, worker process, parameter sweep, pair expansion, or post-OOS tuning is introduced.
