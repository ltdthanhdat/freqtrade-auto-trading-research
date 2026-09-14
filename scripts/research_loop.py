"""Run a bounded, resumable Pi research supervisor."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from threading import Thread
from typing import Callable, Type

from research_runtime.prompt import load_research_prompt, render_research_prompt
from research_runtime.store import ResearchStore


CommandRunner = Callable[..., object]
StoreFactory = Type[ResearchStore]
DEFAULT_LOG_PATH = Path("user_data/research-artifacts/research-supervisor.log")


def _validation_prompt_context(
    *, dataset: str, timerange: str, cycle: dict[str, object]
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
) -> str:
    if template is None:
        template, _ = load_research_prompt()
    identity = _validation_prompt_context(dataset=dataset, timerange=timerange, cycle=cycle)
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
) -> dict[str, object]:
    if not isinstance(max_cycles, int) or isinstance(max_cycles, bool) or not 1 <= max_cycles <= 10:
        raise ValueError("max_cycles must be between 1 and 10")
    if not isinstance(cycle_timeout, int) or isinstance(cycle_timeout, bool) or not 30 <= cycle_timeout <= 3600:
        raise ValueError("cycle_timeout must be between 30 and 3600 seconds")
    prompt_template, prompt_sha256 = load_research_prompt()
    store = store_factory(db_path)
    log_path = log_path or DEFAULT_LOG_PATH
    env = {**os.environ, "RESEARCH_DATASET": dataset, "RESEARCH_TIMERANGE": timerange}
    model = env.get("RESEARCH_MODEL", "openai-codex/gpt-5.6-luna")
    policy_path = Path("config/validation.baseline.json")
    policy_sha256 = hashlib.sha256(policy_path.read_bytes()).hexdigest() if policy_path.is_file() else None
    started = 0
    stopped_reason = "max_cycles"
    for _ in range(max_cycles):
        started_cycle = store.start_or_resume_cycle(
            {
                "dataset": dataset,
                "requested_timerange": timerange,
                "policy_sha256": policy_sha256,
                "prompt_sha256": prompt_sha256,
                "search_cohort": "openalex|arxiv|crossref",
            }
        )
        if started_cycle.get("acquired") is False:
            stopped_reason = "lease_not_acquired"
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
                cycle=started_cycle["cycle"],
                dataset=dataset,
                timerange=timerange,
                template=prompt_template,
            ),
        ]
        _append_log(log_path, f"\n[supervisor] starting cycle {started_cycle['cycle']['id']} with model {model}")
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
                started_cycle["cycle"]["id"],
                "INCOMPLETE",
                f"supervisor timeout; see {log_path}",
            )
            stopped_reason = "timeout"
            break
        except KeyboardInterrupt:
            store.set_cycle_status(started_cycle["cycle"]["id"], "INCOMPLETE", "supervisor interrupted")
            stopped_reason = "interrupted"
            break
        cycles = store.list_cycles(limit=1)
        if not cycles:
            stopped_reason = "no_cycle"
            break
        status = str(cycles[0]["status"])
        if status in {"NEEDS_REVIEW", "COMPLETED", "FAILED"}:
            stopped_reason = status
            break
        if getattr(result, "returncode", 1) != 0 and status not in {"INCOMPLETE", "INTERRUPTED", "RUNNING"}:
            stopped_reason = "command_failed"
            break
        if getattr(result, "returncode", 1) != 0 and status == "RUNNING":
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
                cycles[0]["id"], "INCOMPLETE", f"Pi exited before finalizing cycle: {detail}"
            )
            stopped_reason = "command_failed"
            break
    return {"cycles_started": started, "stopped_reason": stopped_reason}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", dest="db_path", type=Path, default=Path("user_data/research.sqlite"))
    parser.add_argument("--dataset", default=os.environ.get("RESEARCH_DATASET", "accepted_6pair_2026q3_full"))
    parser.add_argument("--timerange", default=os.environ.get("RESEARCH_TIMERANGE", "20260124-20260911"))
    parser.add_argument("--max-cycles", type=int, default=1)
    parser.add_argument("--cycle-timeout", type=int, default=300)
    return parser.parse_args()


def main() -> int:
    result = run_research_loop(**vars(parse_args()))
    print(f"research supervisor: {result['cycles_started']} cycle(s), stopped={result['stopped_reason']}")
    return 0 if result["stopped_reason"] in {"NEEDS_REVIEW", "COMPLETED", "max_cycles"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
