# Airflow Daily Research DAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one DAG-only daily workflow that prepares a verified snapshot, runs the pinned one-shot research container, reconciles failures, and publishes a machine-readable report without embedding research logic in Airflow.

**Architecture:** Add a single `freqtrade_strategy_research_daily` DAG to `~/workspace/airflow-dags`. It uses DockerOperator for repository-owned preparation, research, and reconciliation commands; a small Airflow task builds only the run key/date parameters; and a final report task reads JSON rather than querying research SQLite. The existing Airflow runtime in `~/workspace/iac/airflow` remains responsible for git-sync, the restricted Docker socket, and Airflow metadata storage.

**Tech Stack:** Airflow 3.3.1, `apache-airflow-providers-docker==4.5.9`, DockerOperator, pendulum, Python 3.11, Node contract tests, git-sync.

**Spec:** `docs/superpowers/specs/2026-09-14-daily-research-orchestration-storage-design.md`

## Global Constraints

- DAG ID is `freqtrade_strategy_research_daily`; initial schedule is `15 7 * * *` in `Asia/Bangkok`.
- `max_active_runs=1`, `max_active_tasks=1`, and `catchup=False`.
- Airflow performs orchestration only; no direct research SQL, candidate generation, Freqtrade strategy logic, or Pi prompt duplication.
- Data preparation runs before research and fails closed before Pi/OOS when coverage is insufficient.
- Research image is pinned by `RESEARCH_IMAGE`; no daily image build or blind pull is performed.
- Research containers are one-shot, bridge-networked, read-only except dedicated state/artifact mounts, with no worker/dry-run/live process.
- Conclusive validation `FAIL`/`PASS` is not treated as an infrastructure retry; `PASS` remains review-gated.
- At most one infrastructure recovery is allowed; OOS partitions remain exactly-once.
- Do not modify `data-opportunity-lab` or the existing manual Docker smoke DAG.

---

### Task 1: Define the daily run context and DAG task graph

**Files:**
- Create: `/home/datlt/workspace/airflow-dags/dags/freqtrade_strategy_research_daily.py`
- Modify: `/home/datlt/workspace/airflow-dags/README.md`
- Test: `/home/datlt/workspace/airflow-dags/test/airflow-dags.test.js`
- Test: `/home/datlt/workspace/airflow-dags/test/daily-research-context.test.py`

**Interfaces:**
- `build_run_context(logical_date: pendulum.DateTime, run_id: str, history_days: int = 240) -> dict[str, str]` returns `run_key`, `dataset`, `timerange`, and `manifest_relative_path`.
- `safe_run_key(run_id: str) -> str` replaces characters outside `[A-Za-z0-9_.-]` with `-` and rejects an empty result.
- The DAG task IDs are exactly `build_run_context`, `reconcile_stale_cycles`, `prepare_snapshot`, `run_research`, `reconcile_current`, and `publish_report_and_alert`.

- [ ] **Step 1: Write failing DAG contract tests**

Extend `airflow-dags/test/airflow-dags.test.js`:

```javascript
test('defines the bounded daily Freqtrade research DAG', () => {
  const dag = fs.readFileSync('dags/freqtrade_strategy_research_daily.py', 'utf8');

  assert.match(dag, /dag_id="freqtrade_strategy_research_daily"/);
  assert.match(dag, /schedule="15 7 \* \* \*"/);
  assert.match(dag, /catchup=False/);
  assert.match(dag, /max_active_runs=1/);
  assert.match(dag, /max_active_tasks=1/);
  for (const task of [
    'build_run_context',
    'reconcile_stale_cycles',
    'prepare_snapshot',
    'run_research',
    'reconcile_current',
    'publish_report_and_alert',
  ]) {
    assert.match(dag, new RegExp(task));
  }
  assert.match(dag, /trigger_rule=TriggerRule\.ALL_DONE/);
  assert.doesNotMatch(dag, /sqlite3|SELECT .* FROM|INSERT INTO/i);
  assert.doesNotMatch(dag, /freqtrade-(demo|live)|dry-run|compose-live/i);
});
```

Add `test/daily-research-context.test.py` using the standard library test runner so it has no dependency beyond the Airflow image's installed `pendulum`:

```python
import unittest

import pendulum

from dags.freqtrade_strategy_research_daily import build_run_context


class DailyResearchContextTest(unittest.TestCase):
    def test_safe_run_key_and_daily_timerange(self):
        context = build_run_context(
            pendulum.datetime(2026, 9, 15, 7, 15, tz="Asia/Bangkok"),
            "scheduled__2026-09-15T07:15:00+00:00",
        )

        self.assertEqual(context["run_key"], "scheduled__2026-09-15T07-15-00-00-00")
        self.assertEqual(context["dataset"], "snapshots/daily/scheduled__2026-09-15T07-15-00-00-00")
        self.assertEqual(context["timerange"], "20260118-20260915")
        self.assertTrue(context["manifest_relative_path"].endswith("snapshot-readiness.json"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run DAG tests and verify failure**

```bash
cd /home/datlt/workspace/airflow-dags
npm test
```

Expected: FAIL because the daily DAG file does not exist.

- [ ] **Step 3: Implement context generation**

Use `pendulum.DateTime.subtract(days=history_days)` and format both dates as `YYYYMMDD`. Read `RESEARCH_HISTORY_DAYS` from the runtime environment with default `240`; reject values below `210` because the current policy needs 120 in-sample days plus three 30-day OOS folds. Keep that arithmetic in the DAG as a scheduling window parameter; pair/timeframe/fold sufficiency remains repository-owned.

Return:

```python
{
    "run_key": safe_run_key(run_id),
    "dataset": f"snapshots/daily/{safe_run_key(run_id)}",
    "timerange": f"{start.format('YYYYMMDD')}-{logical_date.format('YYYYMMDD')}",
    "manifest_relative_path": f"runs/{safe_run_key(run_id)}/snapshot-readiness.json",
}
```

- [ ] **Step 4: Implement the DAG shell with dependencies only**

Use the existing Airflow provider and set:

```python
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator
from airflow.utils.trigger_rule import TriggerRule


def build_run_context_task(**context):
    logical_date = context["logical_date"]
    run_id = context["dag_run"].run_id
    return build_run_context(logical_date, run_id)


with DAG(
    dag_id="freqtrade_strategy_research_daily",
    schedule="15 7 * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Bangkok"),
    catchup=False,
    max_active_runs=1,
    max_active_tasks=1,
    tags=["freqtrade", "research", "acceptance"],
) as dag:
    build = PythonOperator(
        task_id="build_run_context",
        python_callable=build_run_context_task,
    )
    reconcile_stale_cycles = EmptyOperator(task_id="reconcile_stale_cycles")
    prepare_snapshot = EmptyOperator(task_id="prepare_snapshot")
    run_research = EmptyOperator(task_id="run_research")
    reconcile_current = EmptyOperator(
        task_id="reconcile_current",
        trigger_rule=TriggerRule.ALL_DONE,
    )
    publish_report_and_alert = EmptyOperator(
        task_id="publish_report_and_alert",
        trigger_rule=TriggerRule.ALL_DONE,
    )
    build >> reconcile_stale_cycles >> prepare_snapshot >> run_research >> reconcile_current >> publish_report_and_alert
```

Use `TriggerRule.ALL_DONE` for both `reconcile_current` and `publish_report_and_alert`. Keep all Docker tasks `retries=0` initially; the research runner's recovery accounting and the explicitly bounded Airflow retry policy are wired in Task 3 after result semantics are defined. Do not import or open SQLite in the DAG module.

- [ ] **Step 5: Run the DAG contract and syntax tests**

```bash
cd /home/datlt/workspace/airflow-dags
npm test
python3 -m py_compile dags/freqtrade_strategy_research_daily.py
python3 -m unittest test/daily-research-context.test.py
```

Expected: PASS for the DAG shell and context tests.

- [ ] **Step 6: Commit the DAG skeleton**

```bash
git add dags/freqtrade_strategy_research_daily.py README.md test/airflow-dags.test.js
git commit -m "feat: add daily research dag skeleton"
```

Do not push without explicit release approval.

---

### Task 2: Configure DockerOperator mounts and repository-owned commands

**Files:**
- Modify: `/home/datlt/workspace/airflow-dags/dags/freqtrade_strategy_research_daily.py`
- Modify: `/home/datlt/workspace/airflow-dags/test/airflow-dags.test.js`
- Modify: `/home/datlt/workspace/iac/airflow/.env.example`
- Modify: `/home/datlt/workspace/iac/airflow/README.md`

**Interfaces:**
- Required operational variables are `RESEARCH_IMAGE`, `RESEARCH_ROOT`, `RESEARCH_STATE_DIR`, `RESEARCH_SNAPSHOT_ROOT`, `RESEARCH_SNAPSHOT_WORK_ROOT`, `RESEARCH_ARTIFACT_ROOT`, `RESEARCH_CODEX_HOME`, `RESEARCH_PI_AGENT_DIR`, and `RESEARCH_WEB_SEARCH_CONFIG`.
- `research_mounts(read_only_snapshot: bool, include_credentials: bool = True) -> list[Mount]` mounts the image's code/config plus snapshot root at `/workspace/user_data/data/snapshots`, state at `/state/research`, and artifacts at `/workspace/user_data/research-artifacts`; credential mounts are added only when `include_credentials` is true.
- `prep_mounts() -> list[Mount]` mounts only `RESEARCH_SNAPSHOT_WORK_ROOT` at `/workspace/user_data/data` read/write and `RESEARCH_ARTIFACT_ROOT` at `/workspace/user_data/research-artifacts` read/write; it does not mount research state or Pi credentials. The work-root mount contains both `.staging/` and `snapshots/` on one filesystem so preparation can atomically rename a staged dataset.
- All DockerOperator tasks use `docker_url="tcp://docker-socket-proxy:2375"`, `mount_tmp_dir=False`, `auto_remove="force"`, `force_pull=False`, `network_mode="bridge"`, `read_only=True`, and `tty=False`; only explicitly listed state/artifact/prep binds are writable.

- [ ] **Step 1: Write failing mount/command contract tests**

Add assertions:

```javascript
test('uses the restricted pinned research container contract', () => {
  const dag = fs.readFileSync('dags/freqtrade_strategy_research_daily.py', 'utf8');

  assert.match(dag, /DockerOperator/);
  assert.match(dag, /RESEARCH_IMAGE/);
  assert.match(dag, /docker-socket-proxy:2375/);
  assert.match(dag, /network_mode="bridge"/);
  assert.match(dag, /mount_tmp_dir=False/);
  assert.match(dag, /auto_remove="force"/);
  assert.match(dag, /force_pull=False/);
  assert.match(dag, /tty=False/);
  assert.match(dag, /scripts\.prepare_research_data/);
  assert.match(dag, /scripts\.research_loop/);
  assert.match(dag, /scripts\.reconcile_research_cycle/);
  assert.doesNotMatch(dag, /mount.*user_data.*rw/i);
});
```

Test that prep task source does not reference `RESEARCH_CODEX_HOME`, `RESEARCH_PI_AGENT_DIR`, or `RESEARCH_WEB_SEARCH_CONFIG`, while research task does.

- [ ] **Step 2: Run the contract test and verify failure**

```bash
cd /home/datlt/workspace/airflow-dags
npm test
```

Expected: FAIL because the DAG has no DockerOperator task configuration.

- [ ] **Step 3: Implement shared mount and environment helpers**

Use `docker.types.Mount` with host sources from `os.environ` and container targets. Define the required environment helper and separate prep/research mount builders in the DAG module:

```python
import os

from airflow.exceptions import AirflowException
from docker.types import Mount


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise AirflowException(f"{name} is required")
    return value


def research_mounts(read_only_snapshot: bool, include_credentials: bool = True) -> list[Mount]:
    mounts = [
        Mount(source=required_env("RESEARCH_STATE_DIR"), target="/state/research", type="bind", read_only=False),
        Mount(source=required_env("RESEARCH_SNAPSHOT_ROOT"), target="/workspace/user_data/data/snapshots", type="bind", read_only=read_only_snapshot),
        Mount(source=required_env("RESEARCH_ARTIFACT_ROOT"), target="/workspace/user_data/research-artifacts", type="bind", read_only=False),
    ]
    if include_credentials:
        mounts.extend([
            Mount(source=required_env("RESEARCH_CODEX_HOME"), target="/home/ftuser/.codex", type="bind", read_only=True),
            Mount(source=required_env("RESEARCH_PI_AGENT_DIR"), target="/pi/agent-source", type="bind", read_only=True),
            Mount(source=required_env("RESEARCH_WEB_SEARCH_CONFIG"), target="/pi/web-search.json", type="bind", read_only=True),
        ])
    return mounts


def prep_mounts() -> list[Mount]:
    return [
        Mount(source=required_env("RESEARCH_SNAPSHOT_WORK_ROOT"), target="/workspace/user_data/data", type="bind", read_only=False),
        Mount(source=required_env("RESEARCH_ARTIFACT_ROOT"), target="/workspace/user_data/research-artifacts", type="bind", read_only=False),
    ]
```

For research only, add the three read-only credential/config mounts to `/home/ftuser/.codex`, `/pi/agent-source`, and `/pi/web-search.json`. Do not mount the host repository or all of `user_data`; the image contains the pinned source/config and the mount contract supplies only state, snapshots, artifacts, and credentials.

- [ ] **Step 4: Add the preparation DockerOperator**

Set its `entrypoint` to `/opt/research-venv/bin/python` and template its command from `build_run_context`:

```python
[
    "-m", "scripts.prepare_research_data",
    "--config", "/workspace/config/config.futures.json",
    "--policy", "/workspace/config/validation.baseline.json",
    "--data-root", "/workspace/user_data/data",
    "--staging-root", "/workspace/user_data/data/.staging/{{ ti.xcom_pull(task_ids='build_run_context')['run_key'] }}",
    "--dataset", "{{ ti.xcom_pull(task_ids='build_run_context')['dataset'] }}",
    "--snapshot-id", "{{ ti.xcom_pull(task_ids='build_run_context')['dataset'] }}",
    "--manifest", "/workspace/user_data/research-artifacts/{{ ti.xcom_pull(task_ids='build_run_context')['manifest_relative_path'] }}",
    "--run-key", "{{ ti.xcom_pull(task_ids='build_run_context')['run_key'] }}",
    "--summary-root", "/workspace/user_data/research-artifacts",
    "--timerange", "{{ ti.xcom_pull(task_ids='build_run_context')['timerange'] }}",
]
```

Use `prep_mounts()`, `read_only=True`, and a disposable `/tmp` tmpfs. The prep environment sets `PYTHONPATH=/workspace`, `TZ=Asia/Bangkok`, and no Pi/Codex variables. Its only writable binds are the dedicated snapshot-work root and artifact root; it has no research-state mount.

- [ ] **Step 5: Add the research DockerOperator**

Use the image's `/usr/local/bin/research-entrypoint`, `research_mounts(read_only_snapshot=True, include_credentials=True)`, and template:

```python
[
    "--db", "/state/research/research.sqlite",
    "--artifacts", "/workspace/user_data/research-artifacts",
    "--dataset", "{{ ti.xcom_pull(task_ids='build_run_context')['dataset'] }}",
    "--timerange", "{{ ti.xcom_pull(task_ids='build_run_context')['timerange'] }}",
    "--snapshot-manifest", "/workspace/user_data/research-artifacts/{{ ti.xcom_pull(task_ids='build_run_context')['manifest_relative_path'] }}",
    "--run-key", "{{ ti.xcom_pull(task_ids='build_run_context')['run_key'] }}",
    "--max-cycles", "1",
    "--cycle-timeout", "{{ var.value.get('RESEARCH_TIMEOUT', '2400') }}",
]
```

Set `RESEARCH_DATASET`, `RESEARCH_TIMERANGE`, `RESEARCH_DB=/state/research/research.sqlite`, `RESEARCH_ARTIFACT_ROOT`, and `RESEARCH_RUN_KEY` in the container environment as well as CLI arguments, so the extension/runtime subprocess sees the same identity. The `RESEARCH_RUN_KEY` owner is the sanitized Airflow run key; the retry keeps it unchanged.

- [ ] **Step 6: Document operational variables and run tests**

Add the variables to `/home/datlt/workspace/iac/airflow/.env.example` without secrets:

```dotenv
RESEARCH_IMAGE=freqtrade-research:daily-20260915
RESEARCH_ROOT=/home/datlt/workspace/freqtrade-auto-trading-research
RESEARCH_STATE_DIR=/home/datlt/workspace/iac/sqlite/freqtrade-auto-trading-research
RESEARCH_SNAPSHOT_ROOT=/home/datlt/workspace/freqtrade-auto-trading-research/user_data/data/snapshots
RESEARCH_SNAPSHOT_WORK_ROOT=/home/datlt/workspace/freqtrade-auto-trading-research/user_data/data
RESEARCH_ARTIFACT_ROOT=/home/datlt/workspace/freqtrade-auto-trading-research/user_data/research-artifacts
RESEARCH_CODEX_HOME=/home/datlt/.codex
RESEARCH_PI_AGENT_DIR=/home/datlt/.pi/agent
RESEARCH_WEB_SEARCH_CONFIG=/home/datlt/.pi/web-search.json
RESEARCH_HISTORY_DAYS=240
```

Document that `RESEARCH_IMAGE` must already exist on the Docker host and is built from a reviewed research commit; the DAG does not build it.

- [ ] **Step 7: Run DAG tests and commit**

```bash
cd /home/datlt/workspace/airflow-dags
npm test
python3 -m py_compile dags/freqtrade_strategy_research_daily.py
```

Expected: PASS.

```bash
git add dags/freqtrade_strategy_research_daily.py test/airflow-dags.test.js README.md
git commit -m "feat: run research stages through docker"
```

Commit the `.env.example` and README changes separately in `/home/datlt/workspace/iac`:

```bash
cd /home/datlt/workspace/iac
git add airflow/.env.example airflow/README.md
git commit -m "docs: configure daily research runner"
```

Do not push either repository in this task.

---

### Task 3: Add reconciliation, result semantics, and all-done reporting

**Files:**
- Modify: `/home/datlt/workspace/airflow-dags/dags/freqtrade_strategy_research_daily.py`
- Modify: `/home/datlt/workspace/airflow-dags/test/airflow-dags.test.js`
- Modify: `/home/datlt/workspace/freqtrade-auto-trading-research/scripts/research_loop.py`
- Modify: `/home/datlt/workspace/freqtrade-auto-trading-research/scripts/reconcile_research_cycle.py`
- Modify: `/home/datlt/workspace/freqtrade-auto-trading-research/scripts/run_summary.py`
- Modify: `/home/datlt/workspace/freqtrade-auto-trading-research/scripts/publish_research_report.py`
- Test: `/home/datlt/workspace/airflow-dags/test/daily-research-dag.test.js`
- Test: `/home/datlt/workspace/freqtrade-auto-trading-research/tests/test_research_run_summary.py`

**Interfaces:**
- `reconcile_stale_cycles` invokes the repository CLI without Pi credentials and is safe when no stale cycle exists.
- `reconcile_current` always runs after `prepare_snapshot`/`run_research` with `TriggerRule.ALL_DONE`, passes Airflow task/container state to `reconcile_cycle`, and never overwrites a terminal cycle.
- `publish_report_and_alert` reads `run-summary.json` from the sanitized Airflow run-key subdirectory under `user_data/research-artifacts/runs/`, logs the status, and raises only for missing/corrupt summary—not for a conclusive research `FAIL`.
- The research runner exits `0` for conclusive `FAILED`, `NEEDS_REVIEW`, or `COMPLETED` results; exits non-zero for infrastructure/incomplete failures so the single configured infrastructure retry can occur.

- [ ] **Step 1: Write failing DAG result tests**

Add:

```javascript
test('reconciliation and reporting always run after research', () => {
  const dag = fs.readFileSync('dags/freqtrade_strategy_research_daily.py', 'utf8');

  assert.match(dag, /task_id="reconcile_stale_cycles"/);
  assert.match(dag, /task_id="reconcile_current"/);
  assert.match(dag, /task_id="publish_report_and_alert"/);
  assert.match(dag, /TriggerRule\.ALL_DONE/);
  assert.match(dag, /reconcile_research_cycle/);
  assert.match(dag, /run-summary\.json/);
});
```

Add a Python runner test:

```python
def test_conclusive_research_failure_is_not_an_infrastructure_retry(tmp_path):
    summary = write_run_summary(
        tmp_path,
        "run-1",
        {
            "status": "FAILED",
            "phase": "finalize_cycle",
            "started_at": "2026-09-15T07:15:00Z",
            "completed_at": "2026-09-15T07:20:00Z",
            "stopped_reason": "FAILED",
        },
    )

    assert json.loads(summary.read_text())["status"] == "FAILED"
```

- [ ] **Step 2: Run focused tests and verify failure**

```bash
cd /home/datlt/workspace/airflow-dags
npm test
cd /home/datlt/workspace/freqtrade-auto-trading-research
uv run pytest tests/test_research_run_summary.py -q
```

Expected: FAIL because reconciliation/report tasks and final status semantics are not wired.

- [ ] **Step 3: Add stale-cycle reconciliation task**

Configure `reconcile_stale_cycles` as a DockerOperator using the pinned image, `research_mounts(read_only_snapshot=True, include_credentials=False)`, no Pi credentials, and `/opt/research-venv/bin/python -m scripts.reconcile_research_cycle --db /state/research/research.sqlite --artifacts /workspace/user_data/research-artifacts --latest --observed-status WATCHDOG --reason "daily stale-cycle reconciliation"`. It should inspect the latest known cycle from the runtime and return success for `NO_OP`/`STILL_RUNNING`; a stale-cycle transition is recorded by the runtime, not by DAG SQL.

- [ ] **Step 4: Add all-done current reconciliation**

Configure `reconcile_current` with `trigger_rule=TriggerRule.ALL_DONE`, `retries=0`, the same state/artifact mounts without credentials, and the command `/opt/research-venv/bin/python -m scripts.reconcile_research_cycle --db /state/research/research.sqlite --artifacts /workspace/user_data/research-artifacts --run-key "{{ ti.xcom_pull(task_ids='build_run_context')['run_key'] }}" --observed-status FAILED --reason "daily research task completed"`. The CLI resolves the exact cycle by its stored `airflow_run_key`, never by an unrelated newest cycle; pass the Airflow task state and Docker container ID as optional templated arguments when available. Use `reconcile_cycle` to map an unfinalized conclusive run to `FAILED`/`NEEDS_REVIEW`, or a failed/expired execution with no conclusive run to `INCOMPLETE`.

- [ ] **Step 5: Wire bounded infrastructure retry semantics**

Set `run_research.retries=1` only after the runner returns `0` for conclusive research verdicts and non-zero for eligible infrastructure/incomplete outcomes. The first retry must reuse the same `run_key`, snapshot manifest, cycle identity, and state DB. A second infrastructure failure is not retried; `reconcile_current` marks the cycle `INCOMPLETE` and writes the terminal summary.

Update `scripts.research_loop.main` and the container entrypoint so the exit code is derived from the persisted cycle status, not merely loop exhaustion:

```python
return 0 if result.get("cycle_status") in {"NEEDS_REVIEW", "FAILED", "COMPLETED"} else 1
```

A `RUNNING`, `INTERRUPTED`, `INCOMPLETE`, lease-not-acquired, or `max_cycles` result is non-zero and is reconciled/retried under the one-recovery rule. The runtime's recovery counter remains authoritative; Airflow's retry count must not create a new cycle or new snapshot.

- [ ] **Step 6: Add report publishing task**

Use a DockerOperator with `TriggerRule.ALL_DONE`, `retries=0`, direct entrypoint `/opt/research-venv/bin/python`, the repository's `-m scripts.publish_research_report` command, and only the artifact-root bind read-only (no SQLite mount or Pi credentials). Pass the sanitized run key, log `status`, `cycle_id`, `snapshot_sha256`, and report references, and emit an alert through the existing Airflow logging/notification mechanism. It must not read SQLite or change a research verdict. Missing/corrupt JSON is an orchestration error and remains visible after reconciliation.

- [ ] **Step 7: Run focused tests and commit**

```bash
cd /home/datlt/workspace/airflow-dags
npm test
python3 -m py_compile dags/freqtrade_strategy_research_daily.py
cd /home/datlt/workspace/freqtrade-auto-trading-research
uv run pytest tests/test_research_run_summary.py tests/test_research_loop.py tests/test_research_reconciliation.py -q
```

Expected: PASS.

Commit DAG changes:

```bash
cd /home/datlt/workspace/airflow-dags
git add dags/freqtrade_strategy_research_daily.py test/airflow-dags.test.js test/daily-research-dag.test.js
git commit -m "feat: reconcile daily research runs"
```

Commit runner changes in the research repository using the runtime-contract plan's commit boundary.

---

### Task 4: Validate git-sync/runtime integration without trading

**Files:**
- Modify: `/home/datlt/workspace/airflow-dags/README.md` if verification instructions need correction
- Modify: `/home/datlt/workspace/iac/airflow/test/airflow-compose.test.js` only for the DAG/runtime contract
- Test: existing smoke DAG and Airflow runtime

**Interfaces:**
- git-sync publishes the DAG repository's `master` revision to `/opt/airflow/dags/current`.
- Airflow parses `freqtrade_strategy_research_daily` and leaves `airflow_smoke_test` intact.
- The Docker socket proxy remains restricted; no direct Docker socket mount is added.

- [ ] **Step 1: Run both repository test suites**

```bash
cd /home/datlt/workspace/airflow-dags
npm test
python3 -m py_compile dags/*.py
cd /home/datlt/workspace/iac/airflow
node --test
```

Expected: PASS.

- [ ] **Step 2: Validate Airflow Compose and git-sync**

```bash
cd /home/datlt/workspace/iac/airflow
docker compose config --quiet
docker compose ps
```

Wait for the git-sync link to contain the committed DAG, then check parsing:

```bash
docker compose exec -T airflow-api-server airflow dags list | grep freqtrade_strategy_research_daily
docker compose exec -T airflow-api-server airflow dags list | grep airflow_smoke_test
```

Expected: both DAG IDs are present and no worker/live Freqtrade service is created by Airflow.

- [ ] **Step 3: Run only the manual Docker smoke DAG**

```bash
make smoke
```

Use the existing `airflow_smoke_test` with `network_mode="none"`; do not trigger the daily research DAG until the pinned research image, central state paths, and snapshot staging are verified.

- [ ] **Step 4: Test a non-trading daily run against a disposable dataset/state directory**

Set `RESEARCH_STATE_DIR`, `RESEARCH_SNAPSHOT_ROOT`, `RESEARCH_SNAPSHOT_WORK_ROOT`, and `RESEARCH_ARTIFACT_ROOT` to disposable directories containing no worker/trade database. Use a fresh run-specific snapshot/work-root identity rather than the consumed historical snapshot. Trigger the daily DAG manually through the Airflow API/CLI, inspect `run-summary.json`, and verify:

```text
no freqtrade-demo container
no freqtrade-live container
no dry-run/live command
no OOS consumption when preparation fails
terminal summary after a forced container failure
```

Do not use consumed historical OOS windows for this test; use a new snapshot/window identity.

- [ ] **Step 5: Commit only verification/documentation corrections**

```bash
cd /home/datlt/workspace/airflow-dags
git status --short
cd /home/datlt/workspace/iac
git status --short
```

Expected: clean trees except intentionally ignored runtime state. Do not stage `portainer/` or `docs/issues/`, and do not push without release approval.

## Final acceptance checklist

- DAG source is only in `~/workspace/airflow-dags/dags/`.
- The DAG is daily, non-catching-up, single-run, and single-task bounded.
- Preparation is repository-owned and runs before Pi with a narrow write mount.
- Research sees only sealed snapshots read-only and uses the namespaced SQLite state mount.
- Reconciliation and report tasks run with `ALL_DONE` even after task failure.
- Conclusive validation `FAIL` is not retried as infrastructure.
- Only one infrastructure retry can reuse the same cycle/snapshot identity.
- A forced failure leaves a terminal `run-summary.json` and a reconciled SQLite cycle.
- Airflow tests, DAG parsing, Compose rendering, git-sync, and smoke checks pass.
- No worker, demo, live, dry-run, promotion, or automatic trading action occurs.
