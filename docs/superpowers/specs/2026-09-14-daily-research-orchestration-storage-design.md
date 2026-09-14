# Daily Freqtrade Research Orchestration and Storage Design

## Status

Approved architectural design for the daily Freqtrade research workflow. This document describes the target boundaries and rollout; implementation has not started.

## Goal

Standardize one daily, bounded Freqtrade strategy-research run without depending on a repo-local Pi skill. Airflow owns scheduling and task orchestration, the Freqtrade repository owns research logic and validation, Docker provides one-shot isolation, and project-namespaced SQLite files provide durable state under `~/workspace/iac/sqlite/`.

The design preserves the current Freqtrade strategy/configuration paths and strategy entry, stop, ROI, time, trailing, and regime semantics. It does not authorize dry-run/live trading or automatic promotion.

## Scope

### In scope

- `~/workspace/freqtrade-auto-trading-research`
- `~/workspace/airflow-dags`
- `~/workspace/iac/airflow`
- `~/workspace/iac/sqlite/airflow/`
- `~/workspace/iac/sqlite/freqtrade-auto-trading-research/`
- A daily Airflow DAG that launches one bounded research run.
- Moving active SQLite state out of the Freqtrade repository.
- External stale-cycle reconciliation and guaranteed terminal reporting.
- Removing the repo-local `freqtrade-strategy-research-loop` skill after its rules are migrated into runtime, prompt, tests, and runner contracts.
- Audit-driven cleanup of legacy research files and generated state.

### Out of scope

- `data-opportunity-lab` and its data, code, databases, or workflows.
- Adding PostgreSQL or another database service.
- Changes to trading strategy semantics, pair expansion, hyperopt, parameter sweeps, post-OOS tuning, dry-run, live trading, or automatic promotion.
- Terraform, cloud provisioning, or a new IaC Git remote.
- Replacing Freqtrade's trade database with the research database.

## Design principles

1. **Runtime over prompt:** policy and safety rules are enforced by typed Python runtime operations and database state transitions. The Pi prompt guides reasoning but is not a safety boundary.
2. **One bounded unit:** one daily DAG run creates or resumes only the governed cycle associated with that run, writes at most one candidate, and starts validation once.
3. **Fresh evaluation inputs:** a new independent cycle requires a newly sealed snapshot and new OOS partitions. Previous metrics are not tuning input.
4. **Durable checkpoints:** every important operation commits its state and artifact identity separately. A process kill cannot create partially committed database rows.
5. **External reconciliation:** a dead process cannot update its own state. Airflow and a stale-cycle watchdog reconcile committed `RUNNING` state after container failure or lease expiry.
6. **Fail closed:** missing data, identity, artifacts, lease, plan, or approval never becomes a performance claim or trading authorization.
7. **Stable external contracts:** keep `src/strategies/`, `config/`, `research_runtime/`, and executable module paths stable unless a compatibility test proves a move safe.

## Repository ownership and target layout

```text
freqtrade-auto-trading-research/
├── config/
├── src/
│   ├── strategies/                 # Freqtrade strategy contract; path stays stable
│   └── smc_risk.py
├── research_runtime/               # canonical research state and validation backend
├── scripts/                        # executable data/research/validation adapters
├── prompts/
│   └── strategy-research.md        # canonical versioned Pi prompt
├── .pi/extensions/
│   └── strategy-research.ts        # one Pi runtime-tool adapter
├── dashboard/                      # local evidence review asset
├── tests/
├── docs/
├── Dockerfile.research
├── compose.yaml                    # research container only
└── Makefile

~/workspace/airflow-dags/
└── dags/
    └── freqtrade_strategy_research_daily.py

~/workspace/iac/airflow/
├── compose.yaml                    # Airflow runtime, git-sync, socket proxy
├── Dockerfile.airflow
├── airflow/init.sh
└── test/

~/workspace/iac/sqlite/
├── airflow/
│   └── airflow.db
├── freqtrade-auto-trading-research/
│   ├── research.sqlite
│   └── validation-state.sqlite
└── backups/
```

The storage directory is persistent runtime state, not source code and not a Git-tracked artifact. It must be ignored, permission-restricted, backed up, and checked for integrity during migrations.

`research.sqlite` owns `ResearchStore` state: cycles, hypotheses, experiments, runs, validation windows, OOS consumption, and research state events. `validation-state.sqlite` owns `ValidationStateStore` state: the execution gate's current state and audit events. `airflow.db` owns only Airflow metadata. Freqtrade demo/live trade databases remain separate.

SQLite files are mounted through dedicated project state directories rather than as single bind-mounted files, so SQLite journal/WAL sidecar files have a controlled location. The research process receives `/state/research/research.sqlite`; it does not receive the parent `user_data` directory.

## Daily Airflow workflow

The initial daily schedule is `15 7 * * *` in `Asia/Bangkok`, matching the existing Airflow runtime timezone convention. The schedule is an Airflow-owned operational setting and can be changed without changing research policy.

The DAG uses `max_active_runs=1`, `max_active_tasks=1`, and `catchup=False`. It does not use generic retries for a conclusive validation failure. A single infrastructure recovery is allowed only when the runtime confirms that no conclusive validation result or OOS consumption exists.

```text
freqtrade_strategy_research_daily
│
├─ reconcile_stale_cycles
│  └─ call typed runtime reconciliation for expired leases
│
├─ prepare_snapshot
│  ├─ seed into a run-specific staging directory
│  ├─ verify policy pairs, 30m/1h/1m coverage, OHLCV columns, and dates
│  ├─ calculate common interval and required OOS folds
│  ├─ compute snapshot hash
│  └─ atomically publish a snapshot-readiness manifest and sealed snapshot
│
├─ run_research
│  └─ DockerOperator launches the pinned research image
│     └─ scripts.research_loop --max-cycles 1
│
├─ reconcile_current [trigger_rule=all_done]
│  └─ finalize a conclusive result or mark stale/incomplete state
│
└─ publish_report_and_alert
   ├─ verify run-summary and validation artifact references
   └─ publish Airflow logs/alert without changing research verdicts
```

Airflow DAG code contains task dependencies and runner parameters only. It does not contain research logic, direct SQL, candidate generation, or Freqtrade strategy rules.

### Cycle selection rules

- A cycle with an unexpired lease is active; the DAG does not start a second one.
- An `INCOMPLETE` cycle may be resumed once for an infrastructure-only recovery under the same identity and snapshot. It is not a new experiment.
- A `FAILED` cycle may be followed on a later day by a new cycle, but only with a newly sealed snapshot and OOS partitions.
- A `NEEDS_REVIEW` cycle blocks automatic creation of another candidate until an explicit review decision is recorded.
- A `PASS` never directly authorizes dry-run/live; the runtime maps it to `NEEDS_REVIEW`.

## Data preparation and readiness contract

Data preparation belongs to the Freqtrade research repository, not to Airflow's business logic. Airflow invokes the repository's data-preparation command in a separate controlled task/container.

The data-prep runner may write only to a run-specific staging snapshot path. The research runner receives only the successfully sealed final snapshot as read-only input. This prevents Pi from reading a partially seeded dataset.

The readiness check is implemented by the existing research code path and must remain policy-driven:

- `ValidationPolicy.from_path(config/validation.baseline.json)` supplies accepted pairs and required fold count.
- `scripts.validate_baseline.inspect_snapshot` checks the required futures files for every accepted pair and required timeframe.
- The required seeded timeframes are `30m`, `1h`, and `1m`.
- Each file must contain non-empty `date`, `open`, `high`, `low`, `close`, and `volume` columns with valid numeric/date values.
- The common interval across all required pair/timeframe files must cover the requested research window.
- `scripts.validation_core.build_oos_folds` must produce at least the policy's `required_folds`.
- The sealed snapshot manifest records the dataset identity, requested/effective timerange, accepted pairs, timeframes, fold intervals, and `snapshot_sha256`.

The sequence is therefore:

```text
requested window
  → seed/download to staging
  → inspect actual files
  → calculate effective common coverage
  → calculate OOS folds
  → hash and atomically seal
  → mount read-only for research
```

If any readiness check fails, the DAG produces a preflight `INCOMPLETE` report and does not start Pi, write a candidate, or consume OOS.

A daily retry of the same Airflow run reuses its sealed staging/final snapshot if the identity matches. A manually rerun daily schedule receives a new snapshot identity; it must not overwrite a snapshot whose OOS partitions were consumed.

## Research execution without the skill

The repo-local `.agents/skills/freqtrade-strategy-research-loop/` directory is removed only after migration verification.

The replacement is:

1. `prompts/strategy-research.md` becomes the only canonical research protocol prompt.
2. `scripts.research_loop` loads the canonical prompt and injects only the cycle/data identity context.
3. `.pi/extensions/strategy-research.ts` exposes the single `strategy_research_runtime` tool and no trading tools.
4. `research_runtime` validates every operation, state transition, identity, budget, plan, artifact, and OOS rule.
5. Contract tests assert the prompt and runtime restrictions, including no shell, SQL, TradingView, trading, sweep, and post-OOS tuning.
6. The prompt version/hash is recorded with each run for reproducibility.

The bounded research protocol remains unchanged in substance:

- maximum 100 collected sources, maximum 3 structured hypotheses, and maximum 1 candidate per cycle;
- hypotheses must be complete frozen plans covering entry, protective/profit/time/trailing/regime exits, precedence, sizing, costs, development protocol, acceptance policy, falsifiers, and role-specific claim-level evidence;
- `required_data` must be exactly `["OHLCV"]`; unsupported data is backlog, not an implicit input;
- source provenance, retrieval time, contradictions, and immutable collector metadata are preserved; `semantic_scholar` is not used and retryable provider errors are not blindly retried;
- ranking is sealed before candidate writing, validation starts once, and no tuning or plan change occurs after OOS begins;
- comparison OOS is unavailable until the sealed three-candidate cohort exists; only its selected winner may use the sealed holdout;
- validation stops at `NEEDS_REVIEW`, `INCONCLUSIVE`, `REJECTED`, `INCOMPLETE`, or `FAILED`, and no result automatically promotes to trading.

The interactive `make research-cycle` target may remain as a local debugging interface. The daily production path is non-interactive:

```text
Airflow → Docker research runner → scripts.research_loop → Pi + canonical prompt → strategy_research_runtime
```

Pi is not permitted to access the shell, SQL, arbitrary filesystem writes, worker processes, or live/dry-run commands during a bounded cycle.

## Runtime lifecycle, checkpointing, and reconciliation

At cycle acquisition, `start_or_resume_cycle` commits:

- `cycles.status=RUNNING`;
- the cycle lease and owner identity;
- the initial `state_events` row.

Each successful runtime operation commits its own checkpoint. Candidate writes use an atomic temporary-file replacement before the candidate hash is recorded. Validation uses `record_validation_bundle` so the run row, validation window, OOS consumption rows, hypothesis transition, and associated event are committed atomically.

A process kill during an open transaction rolls back only that transaction. Earlier committed checkpoints remain available. A hard kill after the `RUNNING` checkpoint cannot execute cleanup code, so it leaves a committed `RUNNING` state until an external reconciler observes the failure.

`research_runtime` gains a typed `reconcile_cycle` operation. The reconciliation algorithm is idempotent:

```text
load cycle by owner/cycle identity
  → re-read current state inside BEGIN IMMEDIATE
  → if terminal, return NO_OP
  → if conclusive run + verified manifest exists:
       FAIL → finalize FAILED
       PASS → finalize NEEDS_REVIEW
  → else if task/container failed or lease expired:
       RUNNING/INTERRUPTED → INCOMPLETE
       append state_events with reason and observed task/container data
  → else:
       return STILL_RUNNING
  → COMMIT
```

The transition is conditional on the state still being non-terminal and stale. If another process finalized the cycle first, the conditional update affects no row and reconciliation returns the newer state. If reconciliation itself is killed, its transaction rolls back and a later observer safely retries it.

The normal DAG includes `reconcile_current` with `trigger_rule=all_done`. A separate lightweight stale-cycle watchdog is optional for faster recovery when Airflow task execution is delayed; the next scheduled DAG must still reconcile stale leases as a fallback. The research image used for reconciliation does not require Pi credentials.

## Candidate validation preflight

Before OOS allocation, the runtime must verify that the candidate is a loadable Freqtrade strategy:

- exactly one permitted `IStrategy` class with the recorded name;
- import and strategy loading succeed in the pinned image;
- required Freqtrade callbacks required by the active Freqtrade version exist;
- no forbidden imports, shell, network, arbitrary writes, or dynamic execution are present;
- candidate file hash and path match the frozen hypothesis identity.

The recent candidate failure where Freqtrade reported `` `populate_exit_trend` must be implemented `` demonstrates why this preflight belongs before OOS consumption. A candidate contract failure is a conclusive `FAILED`/rejected candidate only when the runtime has performed the defined preflight; it must not consume OOS merely to discover a basic load error.

## Reports and durable evidence

Every Airflow DAG run must leave a terminal machine-readable summary, even when preparation or container execution fails:

```text
user_data/research-artifacts/<cycle-id>/run-summary.json
```

The summary records the Airflow DAG run identity, cycle identity, snapshot identity/hash, image identity, start/finish timestamps, last phase, observed container/task result, runtime status, and report references.

If validation starts, the existing validation evidence remains under:

```text
user_data/research-artifacts/validation/<experiment-id>/
├── manifest.json
├── report.md
├── fold-*/
├── lookahead.txt
└── recursive.txt
```

The supervisor log remains under `user_data/research-artifacts/research-supervisor.log`. SQLite stores the durable relational trace through `cycles`, `hypotheses`, `experiments`, `runs`, `validation_windows`, `oos_partition_consumptions`, and `state_events`.

A report can say `INCOMPLETE` without claiming strategy performance. A conclusive `FAIL` is recorded as rejected evidence. A conclusive `PASS` remains review-gated.

## Docker and cross-repository contract

`~/workspace/iac/airflow` uses the existing restricted Docker socket proxy and launches the approved research image through `DockerOperator`. The Airflow DAG does not run `docker compose` inside the Airflow container and does not build the research image on every daily run.

The research image is built and pinned separately from the daily schedule. Its runtime contract remains:

- root filesystem read-only;
- no worker/trading process;
- code/config/policy and sealed snapshots read-only;
- only the dedicated project research-state directory (containing `research.sqlite` and SQLite sidecars) and research artifact root writable;
- Pi credentials/configuration mounted read-only and copied to disposable container storage;
- no research connection to the trading/worker network;
- `stdin_open=false`, `tty=false`, and bounded child process stdin;
- one-shot process that exits after `finalize_cycle` or a bounded failure.

Because the selected storage backend remains SQLite, the research container does not need a database network connection. This preserves the current network isolation model. The SQLite host directories and research artifact path are supplied through ignored operational configuration in `~/workspace/iac/airflow/.env` and the research Compose environment; absolute host paths are never hardcoded into Python domain logic.

## Active, conditional, and legacy files

### Active

- `src/strategies/SMC_FVG_Context30m_Freqtrade.py`
- `src/strategies/SMC_FVG_Confirmation_Freqtrade.py` as a retained dependency/compatibility contract
- `src/smc_risk.py`
- `research_runtime/`
- data/research/validation scripts under `scripts/`
- `prompts/strategy-research.md`
- `.pi/extensions/strategy-research.ts`
- `dashboard/`
- `config/`, `Makefile`, `Dockerfile.research`, `compose.yaml`, and tests

### Conditional/manual

- `scripts/monitor_decay.py`: demo/live performance monitoring
- `scripts/test_binance_testnet_trade.py`: manual exchange diagnostic
- `research_runtime/dashboard.py`: local review server
- `make research-cycle`: local/manual debugging path

### Migration/history

- `research_runtime/migrate_legacy.py`: one-time legacy import utility
- `user_data/research-migration.json`: migration report/evidence until archived
- `docs/superpowers/`: design and implementation history
- `.research/`: legacy research source, removable only after integrity/archive verification

Generated caches, virtual environments, `node_modules`, Freqtrade data, trade databases, research database files, and research artifacts are runtime/local state and are not source structure.

## Migration and rollout

### Step 1: Freeze writers and capture backups

Stop Airflow writers, research runners, and any validation writer. Back up:

- `user_data/research.sqlite`;
- `user_data/validation-state.sqlite` or the exact current validation-state file;
- the Airflow named `airflow_data` volume and current `airflow.db`;
- the research artifact root and migration report.

Verify SQLite integrity, foreign keys, row counts, artifact hashes, and research state/event references.

### Step 2: Move SQLite files into namespaced storage

Use SQLite backup/copy while writers are stopped:

```text
user_data/research.sqlite
  → iac/sqlite/freqtrade-auto-trading-research/research.sqlite

user_data/validation-state.sqlite
  → iac/sqlite/freqtrade-auto-trading-research/validation-state.sqlite

Airflow volume airflow.db
  → iac/sqlite/airflow/airflow.db
```

Update only env/Compose mount paths and test fixtures. Keep the old files read-only until the new paths have passed integrity, dashboard, Airflow, Docker, and recovery checks.

### Step 3: Add lifecycle and data-prep contracts

Implement typed reconciliation, run summaries, canonical prompt loading, candidate preflight, snapshot staging/sealing, and deterministic result mapping. Add focused tests before each behavior.

### Step 4: Wire the DAG repository

Add `freqtrade_strategy_research_daily.py` and its DAG contract tests to `~/workspace/airflow-dags`. Configure the research image and host mount paths in the ignored Airflow environment. Keep the DAG repository DAG-only.

### Step 5: Verify in non-trading mode

Run:

- repository unit/contract tests;
- Airflow DAG parse and contract tests;
- Compose rendering and Docker isolation smoke tests;
- data readiness tests for missing pair/timeframe/coverage/fold cases;
- kill/reconcile tests at every research checkpoint;
- DB integrity and artifact hash checks;
- one manual Airflow-triggered research test with no worker, dry-run, or live service.

A conclusive validation failure is evidence that the candidate was rejected, not an Airflow infrastructure retry. An infrastructure failure is retried only under the one-recovery rule.

### Step 6: Retire old paths

After migration verification and at least one stable daily cycle:

- remove active references to `user_data/research.sqlite`;
- remove duplicate prompt text;
- remove the repo-local research skill;
- archive/remove `.research/` after migration counts and hashes are verified;
- retain the migration utility and documented backup/restore procedure.

## Acceptance criteria

- Airflow runs one bounded daily DAG with no overlapping research cycle.
- Data preparation is implemented in the research repository and Airflow only orchestrates it.
- Insufficient data stops before Pi and before OOS consumption.
- Each new cycle has a fresh sealed snapshot identity and independent artifact/report paths.
- Process/container kills leave committed checkpoints intact and are reconciled to `INCOMPLETE` or a deterministic terminal verdict.
- All validation results have a `manifest.json`, `report.md`, and relational run identity when validation starts; all DAG runs have `run-summary.json`.
- Candidate Freqtrade load/contract errors are rejected before OOS consumption.
- `research.sqlite`, `validation-state.sqlite`, and `airflow.db` are stored under their project namespaces in `~/workspace/iac/sqlite/`.
- No daily flow depends on `.agents/skills/freqtrade-strategy-research-loop/`.
- The current strategy paths and trading semantics remain unchanged.
- No dry-run, live, worker, promotion, parameter sweep, or post-OOS tuning is started automatically.
- Full tests, Docker isolation checks, Airflow DAG checks, migration checks, and clean-state verification pass before rollout.
