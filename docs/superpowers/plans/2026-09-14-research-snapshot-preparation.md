# Research Snapshot Preparation and Container Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make daily OHLCV preparation a repository-owned, policy-driven, staging-and-sealing pipeline that proves data sufficiency before Pi or OOS validation can run.

**Architecture:** Extend the existing Freqtrade downloader to accept an explicit data root, then make `prepare_research_data` seed a unique staging dataset, run the existing `inspect_snapshot` and `build_oos_folds` checks, hash every data file, write a readiness manifest, and atomically publish the dataset. Airflow will invoke the data-prep runner with a narrow writable staging/snapshot mount; the research runner will mount only sealed snapshots read-only.

**Tech Stack:** Python 3.11, pandas, Freqtrade download-data, Feather OHLCV files, SHA-256, atomic filesystem rename, pytest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-14-daily-research-orchestration-storage-design.md`

## Global Constraints

- Required seeded timeframes are `30m`, `1h`, and `1m`.
- Required OHLCV columns are `date`, `open`, `high`, `low`, `close`, and `volume`.
- Accepted pairs and required OOS fold count come from `config/validation.baseline.json`.
- A snapshot is usable only when every accepted pair/timeframe has valid, chronological, gap-free common coverage and at least `required_folds` can be built.
- A staging failure never mutates an already sealed snapshot and never starts Pi or consumes OOS.
- Each independent daily run has a new snapshot identity; a retry of the same Airflow run may reuse only a matching sealed snapshot.
- Do not expand pairs, change strategy semantics, tune parameters, or start worker/dry-run/live processes.
- Keep standard Freqtrade data paths and include `1m` for detailed exit timing.

---

### Task 1: Add an explicit Freqtrade data-root boundary

**Files:**
- Modify: `scripts/seed_freqtrade_data.py:DEFAULT_DATA_ROOT, resolve_datadir, build_command, parse_args`
- Test: `tests/test_seed_freqtrade_data.py`
- Modify: `scripts/prepare_research_data.py` to pass the data root

**Interfaces:**
- `resolve_datadir(args: argparse.Namespace, data_root: Path = DEFAULT_DATA_ROOT) -> Path` returns the standard Freqtrade dataset path below the supplied root.
- The CLI accepts `--data-root PATH`; the default remains the repository's `user_data/data` for local compatibility.
- `build_command` emits `--datadir` under the supplied data root and still emits all requested timeframes.

- [ ] **Step 1: Write the failing data-root tests**

Add:

```python
import argparse
from pathlib import Path

import pytest

from scripts.seed_freqtrade_data import build_command, parse_args, resolve_datadir


def test_resolve_datadir_uses_explicit_data_root(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "sys.argv",
        ["seed", "--config", "config.json", "--dataset", "snapshots/run-1", "--pairs", "BTC/USDT:USDT", "--days", "10"],
    )
    args = parse_args()

    assert resolve_datadir(args, tmp_path) == tmp_path / "snapshots" / "run-1"


def test_download_command_keeps_all_required_timeframes(tmp_path: Path):
    args = argparse.Namespace(
        config="config.json",
        dataset="snapshots/run-1",
        timeframes=["30m", "1h", "1m"],
        days=10,
        timerange=None,
        erase=False,
    )

    command = build_command(args, ["BTC/USDT:USDT"], data_root=tmp_path)

    assert command[command.index("--datadir") + 1] == str(tmp_path / "snapshots" / "run-1")
    assert command[command.index("--timeframes") + 1 : command.index("--pairs")] == ["30m", "1h", "1m"]
```

Import `argparse` in the test module. Add a `prepare` test that passes `data_root=tmp_path / "data"` and confirms the downloader command targets that root instead of the repository's `user_data/data`.

- [ ] **Step 2: Run the focused tests and verify failure**

```bash
uv run pytest tests/test_seed_freqtrade_data.py tests/test_prepare_research_data.py -q
```

Expected: FAIL because `--data-root` and the new `build_command` parameter do not exist.

- [ ] **Step 3: Implement the data-root parameter**

Add `--data-root` to `parse_args`, thread `Path(args.data_root)` through `resolve_datadir` and `build_command`, and keep dataset traversal protection (`absolute` and `..` paths). Update `prepare_research_data.prepare` to accept `data_root: Path | None = None` and pass it into both the final inspection path and `build_command`.

- [ ] **Step 4: Run the focused tests and commit**

```bash
uv run pytest tests/test_seed_freqtrade_data.py tests/test_prepare_research_data.py -q
```

Expected: PASS.

```bash
git add scripts/seed_freqtrade_data.py scripts/prepare_research_data.py tests/test_seed_freqtrade_data.py tests/test_prepare_research_data.py
git commit -m "feat: parameterize research data root"
```

---

### Task 2: Build and seal a verified snapshot manifest

**Files:**
- Create: `research_runtime/snapshots.py`
- Modify: `scripts/prepare_research_data.py:prepare, parse_args, main`
- Modify: `scripts/validate_baseline.py` to expose the directory hash helper
- Test: `tests/test_prepare_research_data.py`
- Create: `tests/test_research_snapshots.py`

**Interfaces:**
- `directory_sha256(datadir: Path) -> str` hashes sorted relative file names and file bytes; it excludes no OHLCV file below the dataset directory.
- `atomic_write_json(path: Path, payload: Mapping[str, object]) -> str` writes canonical sorted JSON with a newline and returns the written file's SHA-256.
- `publish_snapshot(staging_datadir: Path, final_datadir: Path) -> None` renames a complete staging directory into an absent final directory and rejects an existing final directory.
- `prepare(*, config: Path, policy_path: Path, dataset: str, timerange: str, data_root: Path | None = None, staging_root: Path | None = None, manifest_path: Path | None = None, snapshot_id: str | None = None, run_key: str | None = None, summary_root: Path | None = None) -> dict[str, object]` returns `status="READY"`, `snapshot_sha256`, `manifest_path`, effective coverage, fold list, and `reused`; when `run_key` and `summary_root` are supplied, a preparation failure writes the terminal `INCOMPLETE` run summary.
- The manifest has `schema_version=1`, `status="SEALED"`, `dataset`, `datadir`, `requested_timerange`, `effective_start`, `effective_end`, `accepted_pairs`, `timeframes`, `folds`, `policy_sha256`, `snapshot_sha256`, and `sealed_at`.

- [ ] **Step 1: Write failing hash, atomic publish, and readiness tests**

Add:

```python
import json
from pathlib import Path

import pytest

from research_runtime.snapshots import atomic_write_json, directory_sha256, publish_snapshot


def test_directory_hash_is_order_independent(tmp_path: Path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "b.feather").write_bytes(b"b")
    (dataset / "a.feather").write_bytes(b"a")

    first = directory_sha256(dataset)
    (dataset / "a.feather").touch()

    assert directory_sha256(dataset) == first


def test_publish_snapshot_never_overwrites_existing_final(tmp_path: Path):
    staging = tmp_path / "staging"
    final = tmp_path / "final"
    staging.mkdir()
    (staging / "BTC-1m-futures.feather").write_bytes(b"data")
    final.mkdir()

    with pytest.raises(FileExistsError):
        publish_snapshot(staging, final)


def test_atomic_manifest_has_sealed_status(tmp_path: Path):
    path = tmp_path / "snapshot-readiness.json"
    digest = atomic_write_json(path, {"schema_version": 1, "status": "SEALED"})

    payload = json.loads(path.read_text())
    assert payload["status"] == "SEALED"
    assert len(digest) == 64
    assert not list(tmp_path.glob("*.tmp"))
```

Add preparation tests using the existing Feather fixture helper:

- missing one accepted pair/timeframe raises `RuntimeError` and leaves no final dataset;
- common history shorter than the requested range raises and leaves no final dataset;
- a valid fixture returns `status="READY"`, exactly the policy-required fold count or more, a 64-character snapshot hash, and a manifest whose hash matches the data directory;
- an existing sealed dataset with matching policy/timerange/hash is returned with `reused=True` and the downloader is not called;
- an existing final dataset with a mismatched identity is rejected instead of being modified.

- [ ] **Step 2: Run the snapshot tests and verify failure**

```bash
uv run pytest tests/test_research_snapshots.py tests/test_prepare_research_data.py -q
```

Expected: FAIL because the snapshot helper and staging/sealing behavior do not exist.

- [ ] **Step 3: Implement filesystem helpers**

In `research_runtime/snapshots.py`, use sorted `Path.rglob("*")` files, hash each relative POSIX path followed by its bytes, write JSON through a sibling temporary path with flush/fsync and `Path.replace`, and use `staging_datadir.rename(final_datadir)` only when the final path does not exist. Require staging and final parents to be on the same filesystem so the rename is atomic.

- [ ] **Step 4: Rewrite preparation around staging and a manifest**

Change `prepare` to:

1. Normalize `snapshot_id`/`dataset` as a relative path beginning with `snapshots/` and reject traversal.
2. Resolve `final_datadir = data_root / dataset_path` and a unique `staging_datadir = staging_root / dataset_path`; default `staging_root` is `data_root / ".staging"`, and both parents must be on the same filesystem. The local default `manifest_path` is a deterministic sibling readiness file, while Airflow always supplies the run-key artifact path.
3. If a sealed manifest exists, verify its policy hash, requested timerange, dataset, and directory hash; return it with `reused=True` only if all checks pass.
4. Create an empty unique staging directory and run `build_command` with `--data-root staging_root`, `--dataset dataset_path`, and `--timeframes 30m 1h 1m`.
5. Run `inspect_snapshot` on staging, reject any error, calculate the effective common interval, and call `build_oos_folds`; reject fewer than `policy.required_folds`.
6. Compute `snapshot_sha256`, build the manifest, publish the staged data atomically, then write the final `status="SEALED"` manifest through `atomic_write_json`. Treat the snapshot as usable only after both the final data directory and the manifest exist and the manifest hash re-verifies the final directory; a kill between the two publications remains unready and is never mounted for research.
7. Return the manifest fields plus `reused=False`.

Do not use `erase=False` against an existing final snapshot. A failed seed or verification removes only its unique staging directory and leaves sealed datasets unchanged. Move `_snapshot_sha256` in `scripts/validate_baseline.py` to the public `directory_sha256` implementation or delegate to it so validation and preparation use exactly one hash algorithm.

- [ ] **Step 5: Add the CLI contract**

Add these options to `prepare_research_data.parse_args`:

```text
--data-root PATH
--staging-root PATH
--manifest PATH
--snapshot-id TEXT
--run-key TEXT
--summary-root PATH
```

Require `--manifest`, `--snapshot-id`, `--run-key`, and `--summary-root` in the Airflow invocation; retain deterministic defaults for local `make research-data`. Print the complete readiness JSON as one line and return `1` for any preparation/verification error. On an error, if `--run-key` and `--summary-root` were supplied, call `write_run_summary` with `status="INCOMPLETE"`, `phase="prepare_snapshot"`, the original start timestamp, `completed_at`, and a bounded error string; if summary writing fails, preserve the preparation exit status.

- [ ] **Step 6: Run snapshot tests and commit**

```bash
uv run pytest tests/test_research_snapshots.py tests/test_prepare_research_data.py tests/test_validate_baseline.py -q
```

Expected: PASS.

```bash
git add research_runtime/snapshots.py scripts/prepare_research_data.py scripts/validate_baseline.py tests/test_research_snapshots.py tests/test_prepare_research_data.py
git commit -m "feat: seal verified research snapshots"
```

---

### Task 3: Separate data-prep and read-only research container mounts

**Files:**
- Modify: `compose.yaml`
- Modify: `Dockerfile.research` only if the prep command needs an image entrypoint change
- Modify: `Makefile`
- Modify: `tests/test_research_docker.py`
- Modify: `tests/test_validation_manifest.py`

**Interfaces:**
- Compose exposes a `research-data-prep` profile/service that invokes `python -m scripts.prepare_research_data`, mounts only a dedicated snapshot-work root at `/workspace/user_data/data` read/write plus the artifact root for readiness output, and has no Pi credentials or research-state mount.
- Compose `research` remains one-shot, `read_only: true`, `stdin_open: false`, `tty: false`, `network_mode: bridge`, and receives only the sealed snapshot root read-only; the SQLite state-path change is owned by the later SQLite plan.
- The research service never mounts all of `user_data` from the host. Its final state/artifact mount shape is completed by the SQLite plan without changing this data-preparation boundary.

- [ ] **Step 1: Write failing Compose contract tests**

Extend `tests/test_research_docker.py` with assertions equivalent to:

```python
def test_compose_separates_prep_write_mount_from_research_read_mount():
    compose = Path("compose.yaml").read_text()
    prep = compose[compose.index("research-data-prep:") :]
    research = compose[compose.index("  research:") :]

    assert "scripts.prepare_research_data" in prep
    assert "research-data-prep" in compose
    assert "read_only: true" in research
    assert "stdin_open: false" in research
    assert "tty: false" in research
    assert "network_mode: bridge" in research
    assert "./user_data:/" not in research
    assert "CODEX_HOME" not in prep
    assert "PI_AGENT_DIR" not in prep
    assert "RESEARCH_SNAPSHOT_WORK_ROOT" in prep
    assert "RESEARCH_ARTIFACT_ROOT" in prep
```

Add a test that the prep command includes all three timeframes, `--manifest`, `--run-key`, and `--summary-root`, while the research command includes `--snapshot-manifest` and retains its existing state path until the SQLite plan changes it.

- [ ] **Step 2: Run the Docker contract tests and verify failure**

```bash
uv run pytest tests/test_research_docker.py tests/test_validation_manifest.py -q
```

Expected: FAIL because Compose currently has only one research service and binds the repo-local research DB.

- [ ] **Step 3: Add the prep service and narrow mounts**

Add a `research-data-prep` service under the `research` profile using the same pinned image, `read_only: true`, `network_mode: bridge`, a tmpfs for `/tmp`, and two narrow host binds: the configured snapshot-work root at `/workspace/user_data/data` with write access (so final and staging directories share one filesystem for `rename`) and the configured artifact root at `/workspace/user_data/research-artifacts` with write access for the readiness manifest. Override the image entrypoint with `/opt/research-venv/bin/python` and run:

```text
-m scripts.prepare_research_data
--config /workspace/config/config.futures.json
--policy /workspace/config/validation.baseline.json
--data-root /workspace/user_data/data
--staging-root /workspace/user_data/data/.staging/${RESEARCH_RUN_KEY}
--dataset ${RESEARCH_DATASET}
--snapshot-id ${RESEARCH_DATASET}
--manifest /workspace/user_data/research-artifacts/runs/${RESEARCH_RUN_KEY}/snapshot-readiness.json
--run-key ${RESEARCH_RUN_KEY}
--summary-root /workspace/user_data/research-artifacts
--timerange ${RESEARCH_TIMERANGE}
```

Use the Airflow-templated values in the production DAG; the Compose file's local defaults must be runnable with explicit `.env` overrides. Do not mount Pi/Codex credentials or the research-state directory into this service.

Change only the `research` service's snapshot bind in this task to the configured sealed snapshot root read-only and pass `--snapshot-manifest` to `scripts.research_loop`. Leave its database and artifact paths for the SQLite namespace plan; do not introduce a parent `user_data` bind.

- [ ] **Step 4: Update local Make targets**

Keep `research-data` as a local repository command but add `DATA_ROOT`, `STAGING_ROOT`, `SNAPSHOT_ID`, `SNAPSHOT_MANIFEST`, `RESEARCH_RUN_KEY`, and `RESEARCH_ARTIFACT_ROOT` variables. Make `research-loop` pass `--snapshot-manifest` and the same dataset/timerange used by `research-data`. Keep `compose-research` as the read-only research execution target; add `compose-research-data` for the prep service. Do not finalize the namespaced SQLite defaults here; the SQLite plan owns those Make/Compose edits.

- [ ] **Step 5: Render and test the container contract**

```bash
docker compose --profile research config --quiet
uv run pytest tests/test_research_docker.py tests/test_validation_manifest.py -q
```

Expected: PASS. Do not start demo/live services or a research cycle in this task.

- [ ] **Step 6: Commit the container boundary**

```bash
git add compose.yaml Dockerfile.research Makefile tests/test_research_docker.py tests/test_validation_manifest.py
git commit -m "feat: isolate research data preparation"
```

## Verification checklist

- Missing pair, timeframe, OHLCV column, gap, invalid candle, insufficient common range, and insufficient fold cases fail before Pi/OOS.
- A valid prepared dataset has a sealed manifest and deterministic directory hash.
- Re-running the same request is idempotent and never overwrites a sealed dataset.
- The prep container has write access only to its dedicated snapshot-work and readiness-artifact mounts and no Pi credentials or research-state mount.
- The research container sees sealed snapshots read-only and no parent `user_data` bind; the later SQLite plan supplies the dedicated state/artifact mounts.
- `1m` is always seeded and supplied as `timeframe_detail` for validation.
