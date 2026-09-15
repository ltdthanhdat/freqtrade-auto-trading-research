"""Run a bounded, resumable Pi research supervisor."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from threading import Thread
from typing import Callable, Type

from research_runtime import paths
from research_runtime.prompt import load_research_prompt, render_research_prompt
from research_runtime.store import ResearchStore
from scripts.run_summary import write_run_summary


CommandRunner = Callable[..., object]
StoreFactory = Type[ResearchStore]
DEFAULT_LOG_PATH = Path("user_data/research-artifacts/research-supervisor.log")


def _validation_prompt_context(
    *,
    dataset: str,
    timerange: str,
    cycle: dict[str, object],
    snapshot_manifest: Path | None = None,
) -> str:
    """Describe immutable validation identities already present in the workspace."""
    dataset_path = Path(dataset)
    if dataset_path.parts[:1] != ("snapshots",):
        dataset_path = Path("snapshots") / dataset_path
    datadir = Path("user_data/data") / dataset_path
    context = [
        f"dataset={dataset_path.as_posix()}",
        f"requested_timerange={timerange}",
        "parent_strategy='SMC_FVG_Context30m_Freqtrade'",
        "timeframe_detail='1m'",
        "Do not include hypothesis_id in propose_hypothesis payload",
        "config_path=config/config.futures.json",
        "policy_path=config/validation.baseline.json",
        f"snapshot_path=user_data/data/{dataset_path.as_posix()}",
    ]
    if snapshot_manifest is not None:
        context.append(f"snapshot_manifest={snapshot_manifest}")
        try:
            manifest = json.loads(snapshot_manifest.read_text(encoding="utf-8"))
            if isinstance(manifest, dict) and manifest.get("snapshot_sha256"):
                context.append(f"sealed_snapshot_sha256={manifest['snapshot_sha256']}")
        except (OSError, json.JSONDecodeError):
            context.append("sealed_snapshot_sha256=unavailable")
    try:
        import pandas as pd

        from scripts.validate_baseline import collect_identity
        from scripts.validation_core import ValidationPolicy, build_oos_folds

        config_path = Path("config/config.futures.json")
        policy_path = Path("config/validation.baseline.json")
        strategy_path = Path("src/strategies")
        strategy_file = strategy_path / "SMC_FVG_Context30m_Freqtrade.py"
        if not all(path.is_file() for path in (config_path, policy_path, strategy_file)) or not datadir.is_dir():
            return "\n".join(context)
        identity = collect_identity(
            config_path,
            strategy_file,
            datadir,
            policy_path,
            "SMC_FVG_Context30m_Freqtrade",
            strategy_path,
        )
        holdout_start = str(cycle.get("holdout_start") or "")
        if holdout_start:
            validation_end = pd.Timestamp(holdout_start)
            if validation_end.tzinfo is None:
                validation_end = validation_end.tz_localize("UTC")
            else:
                validation_end = validation_end.tz_convert("UTC")
        else:
            validation_end = pd.Timestamp(timerange.split("-", 1)[1], tz="UTC")
        validation_start = pd.Timestamp(timerange.split("-", 1)[0], tz="UTC")
        policy = ValidationPolicy.from_path(policy_path)
        folds = build_oos_folds(validation_start, validation_end, policy)
        partitions = [
            {
                "kind": "WFO_OOS",
                "start_at": fold.oos_start.isoformat(),
                "end_at": fold.oos_end.isoformat(),
            }
            for fold in folds
        ]
        context.extend(
            [
                f"parent_sha256={identity.strategy_sha256}",
                f"config_sha256={identity.config_sha256}",
                f"policy_sha256={identity.policy_sha256}",
                f"snapshot_sha256={identity.snapshot_sha256}",
                f"parent_strategy_path={identity.strategy_path}",
                f"pairs={json.dumps(list(identity.accepted_pairs), separators=(',', ':'))}",
                'timeframes=["30m","1h"]',
                "timeframe_detail='1m'",
                f"start_at={validation_start.isoformat()}",
                f"end_at={validation_end.isoformat()}",
                f"oos_partitions={json.dumps(partitions, separators=(',', ':'))}",
            ]
        )
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        # The runtime remains authoritative; an unavailable local identity only
        # makes the eventual validation fail closed.
        pass
    return "\n".join(context)


def _research_prompt(
    *,
    cycle: dict[str, object],
    dataset: str,
    timerange: str,
    template: str | None = None,
    snapshot_manifest: Path | None = None,
) -> str:
    if template is None:
        template, _ = load_research_prompt()
    identity = _validation_prompt_context(
        dataset=dataset,
        timerange=timerange,
        cycle=cycle,
        snapshot_manifest=snapshot_manifest,
    )
    return render_research_prompt(
        template,
        cycle_id=str(cycle["id"]),
        validation_context=identity,
    )


def _append_log(log_path: Path, text: str) -> None:
    if not text:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as stream:
        stream.write(text)
        if not text.endswith("\n"):
            stream.write("\n")


def _stream_command(
    command: list[str], *, env: dict[str, str], timeout: int, log_path: Path
) -> subprocess.CompletedProcess[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
        stdin=subprocess.DEVNULL,
    )
    output: list[str] = []

    def consume() -> None:
        assert process.stdout is not None
        with log_path.open("a", encoding="utf-8") as stream:
            for line in process.stdout:
                output.append(line)
                stream.write(line)
                stream.flush()
                print(line, end="", flush=True)

    reader = Thread(target=consume, daemon=True)
    reader.start()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.wait()
        reader.join(timeout=2)
        _append_log(log_path, f"[supervisor] timeout after {timeout}s")
        raise subprocess.TimeoutExpired(
            command, timeout, output="".join(output), stderr=""
        ) from exc
    reader.join()
    return subprocess.CompletedProcess(command, process.returncode, "".join(output), "")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _snapshot_identity(snapshot_manifest: Path | None) -> str | None:
    if snapshot_manifest is None:
        return None
    if not snapshot_manifest.is_file():
        raise ValueError(f"snapshot manifest is missing: {snapshot_manifest}")
    try:
        payload = json.loads(snapshot_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"snapshot manifest is unreadable: {snapshot_manifest}") from exc
    if not isinstance(payload, dict) or not payload.get("snapshot_sha256"):
        raise ValueError(f"snapshot manifest has no snapshot_sha256: {snapshot_manifest}")
    return str(payload["snapshot_sha256"])


def _cycle_for(store: ResearchStore, cycle_id: str | None) -> dict[str, object] | None:
    if cycle_id:
        getter = getattr(store, "get_cycle", None)
        if callable(getter):
            cycle = getter(cycle_id)
            if cycle is not None:
                return cycle
    cycles = store.list_cycles(limit=1)
    return cycles[0] if cycles else None


def _persist_terminal_summary(
    *,
    summary_root: Path | None,
    run_key: str | None,
    started_at: str,
    cycle: dict[str, object] | None,
    stopped_reason: str,
    error: str | None = None,
    snapshot_sha256: str | None = None,
    snapshot_manifest: Path | None = None,
    returncode: int | None = None,
    log_path: Path | None = None,
) -> None:
    if summary_root is None or not run_key:
        return
    cycle_status = str(cycle.get("status")) if cycle else "INCOMPLETE"
    status = cycle_status if cycle_status in {"COMPLETED", "NEEDS_REVIEW", "FAILED", "INCOMPLETE"} else "INCOMPLETE"
    payload: dict[str, object] = {
        "status": status,
        "phase": "finalize_cycle" if cycle_status in {"COMPLETED", "NEEDS_REVIEW", "FAILED"} else "research",
        "started_at": started_at,
        "completed_at": _now(),
        "stopped_reason": stopped_reason,
        "cycle_status": cycle_status,
        "last_phase": cycle.get("stage") if cycle else "acquire_cycle",
        "returncode": returncode,
        "snapshot_sha256": snapshot_sha256,
        "snapshot_manifest_path": str(snapshot_manifest) if snapshot_manifest else None,
    }
    if cycle:
        payload.update(
            {
                "cycle_id": cycle.get("id"),
                "snapshot_sha256": cycle.get("snapshot_sha256") or snapshot_sha256,
                "snapshot_manifest_path": cycle.get("snapshot_manifest_path") or (
                    str(snapshot_manifest) if snapshot_manifest else None
                ),
            }
        )
    if error:
        payload["error"] = error
    try:
        write_run_summary(summary_root, run_key, payload)
    except (OSError, ValueError) as exc:
        # A reporting failure must not replace the research result. Keep it in
        # the supervisor log when one is available and let the caller retain
        # the persisted cycle status.
        _append_log(log_path or DEFAULT_LOG_PATH, f"[supervisor] run summary write failed: {exc}")


def run_research_loop(
    *,
    db_path: Path,
    dataset: str,
    timerange: str,
    max_cycles: int = 1,
    cycle_timeout: int = 300,
    command_runner: CommandRunner | None = None,
    store_factory: StoreFactory = ResearchStore,
    log_path: Path | None = None,
    run_key: str | None = None,
    summary_root: Path | None = None,
    snapshot_manifest: Path | None = None,
) -> dict[str, object]:
    if not isinstance(max_cycles, int) or isinstance(max_cycles, bool) or not 1 <= max_cycles <= 10:
        raise ValueError("max_cycles must be between 1 and 10")
    if not isinstance(cycle_timeout, int) or isinstance(cycle_timeout, bool) or not 30 <= cycle_timeout <= 3600:
        raise ValueError("cycle_timeout must be between 30 and 3600 seconds")
    if summary_root is not None:
        summary_root = Path(summary_root)
    if snapshot_manifest is not None:
        snapshot_manifest = Path(snapshot_manifest)
    run_started_at = _now()
    snapshot_sha256 = _snapshot_identity(snapshot_manifest)
    prompt_template, prompt_sha256 = load_research_prompt()
    store = store_factory(db_path)
    log_path = log_path or (paths.research_artifact_root() / "research-supervisor.log")
    env = {**os.environ, "RESEARCH_DATASET": dataset, "RESEARCH_TIMERANGE": timerange}
    if run_key:
        env["RESEARCH_RUN_KEY"] = run_key
    if snapshot_manifest is not None:
        env["RESEARCH_SNAPSHOT_MANIFEST"] = str(snapshot_manifest)
    model = env.get("RESEARCH_MODEL", "openai-codex/gpt-5.6-luna")
    policy_path = Path("config/validation.baseline.json")
    policy_sha256 = hashlib.sha256(policy_path.read_bytes()).hexdigest() if policy_path.is_file() else None
    started = 0
    stopped_reason = "max_cycles"
    last_cycle: dict[str, object] | None = None
    error: str | None = None
    returncode: int | None = None
    for _ in range(max_cycles):
        identity: dict[str, object] = {
            "dataset": dataset,
            "requested_timerange": timerange,
            "policy_sha256": policy_sha256,
            "prompt_sha256": prompt_sha256,
            "search_cohort": "openalex|arxiv|crossref",
            "lease_owner": run_key or "runtime-local",
        }
        if run_key:
            identity["airflow_run_key"] = run_key
        if snapshot_manifest is not None:
            identity["snapshot_manifest_path"] = str(snapshot_manifest)
            identity["snapshot_sha256"] = snapshot_sha256
        try:
            started_cycle = store.start_or_resume_cycle(identity)
        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            stopped_reason = "acquire_error"
            error = str(exc)
            break
        candidate_cycle = started_cycle.get("cycle")
        if isinstance(candidate_cycle, dict):
            last_cycle = candidate_cycle
        if started_cycle.get("acquired") is False:
            if isinstance(candidate_cycle, dict):
                last_cycle = {**candidate_cycle, "status": "INCOMPLETE"}
            stopped_reason = "lease_not_acquired"
            break
        if not isinstance(candidate_cycle, dict) or not candidate_cycle.get("id"):
            stopped_reason = "no_cycle"
            break
        started += 1
        command = [
            "pi",
            "-p",
            "--mode",
            "json",
            "--no-extensions",
            "--extension",
            ".pi/extensions/strategy-research.ts",
            "--approve",
            "--model",
            model,
            "--thinking",
            "max",
            "--no-builtin-tools",
            "--",
            _research_prompt(
                cycle=candidate_cycle,
                dataset=dataset,
                timerange=timerange,
                template=prompt_template,
                snapshot_manifest=snapshot_manifest,
            ),
        ]
        _append_log(log_path, f"\n[supervisor] starting cycle {candidate_cycle['id']} with model {model}")
        try:
            if command_runner is None:
                result = _stream_command(
                    command, env=env, timeout=cycle_timeout, log_path=log_path
                )
            else:
                result = command_runner(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=cycle_timeout,
                )
                _append_log(log_path, getattr(result, "stdout", ""))
                _append_log(log_path, getattr(result, "stderr", ""))
        except subprocess.TimeoutExpired:
            store.set_cycle_status(
                candidate_cycle["id"],
                "INCOMPLETE",
                f"supervisor timeout; see {log_path}",
            )
            last_cycle = _cycle_for(store, str(candidate_cycle["id"])) or {
                **candidate_cycle,
                "status": "INCOMPLETE",
            }
            stopped_reason = "timeout"
            break
        except KeyboardInterrupt:
            store.set_cycle_status(candidate_cycle["id"], "INCOMPLETE", "supervisor interrupted")
            last_cycle = _cycle_for(store, str(candidate_cycle["id"])) or {
                **candidate_cycle,
                "status": "INCOMPLETE",
            }
            stopped_reason = "interrupted"
            break
        current = _cycle_for(store, str(candidate_cycle["id"]))
        if current is None:
            stopped_reason = "no_cycle"
            break
        last_cycle = current
        status = str(current["status"])
        if status in {"NEEDS_REVIEW", "COMPLETED", "FAILED"}:
            stopped_reason = status
            break
        returncode = getattr(result, "returncode", 1)
        if returncode != 0 and status not in {"INCOMPLETE", "INTERRUPTED", "RUNNING"}:
            stopped_reason = "command_failed"
            break
        if returncode != 0 and status == "RUNNING":
            output = "\n".join(
                value
                for value in (
                    getattr(result, "stdout", ""),
                    getattr(result, "stderr", ""),
                )
                if value
            ).strip()
            detail = output[-500:] if output else "no output"
            store.set_cycle_status(
                current["id"], "INCOMPLETE", f"Pi exited before finalizing cycle: {detail}"
            )
            last_cycle = _cycle_for(store, str(current["id"])) or {
                **current,
                "status": "INCOMPLETE",
            }
            stopped_reason = "command_failed"
            error = detail
            break
    if last_cycle is None:
        last_cycle = _cycle_for(store, None)
    cycle_status = str(last_cycle["status"]) if last_cycle and last_cycle.get("status") else "INCOMPLETE"
    result = {
        "cycles_started": started,
        "stopped_reason": stopped_reason,
        "cycle_status": cycle_status,
    }
    _persist_terminal_summary(
        summary_root=summary_root,
        run_key=run_key,
        started_at=run_started_at,
        cycle=last_cycle,
        stopped_reason=stopped_reason,
        error=error,
        snapshot_sha256=snapshot_sha256,
        snapshot_manifest=snapshot_manifest,
        returncode=returncode,
        log_path=log_path,
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", dest="db_path", type=Path, default=paths.research_db_path())
    parser.add_argument("--dataset", default=os.environ.get("RESEARCH_DATASET", "accepted_6pair_2026q3_full"))
    parser.add_argument("--timerange", default=os.environ.get("RESEARCH_TIMERANGE", "20260124-20260911"))
    parser.add_argument("--max-cycles", type=int, default=1)
    parser.add_argument("--cycle-timeout", type=int, default=300)
    parser.add_argument("--run-key", default=os.environ.get("RESEARCH_RUN_KEY"))
    parser.add_argument(
        "--artifacts",
        dest="summary_root",
        type=Path,
        default=paths.research_artifact_root(),
    )
    parser.add_argument(
        "--snapshot-manifest",
        type=Path,
        default=Path(os.environ["RESEARCH_SNAPSHOT_MANIFEST"])
        if os.environ.get("RESEARCH_SNAPSHOT_MANIFEST")
        else None,
    )
    return parser.parse_args()


def main() -> int:
    result = run_research_loop(**vars(parse_args()))
    print(f"research supervisor: {result['cycles_started']} cycle(s), stopped={result['stopped_reason']}")
    return 0 if result.get("cycle_status") in {"NEEDS_REVIEW", "COMPLETED", "FAILED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
