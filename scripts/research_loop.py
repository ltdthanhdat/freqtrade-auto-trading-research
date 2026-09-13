"""Run a bounded, resumable Pi research supervisor."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
from typing import Callable, Type

from research_runtime.store import ResearchStore


CommandRunner = Callable[..., object]
StoreFactory = Type[ResearchStore]


def run_research_loop(
    *,
    db_path: Path,
    dataset: str,
    timerange: str,
    max_cycles: int = 1,
    cycle_timeout: int = 300,
    command_runner: CommandRunner = subprocess.run,
    store_factory: StoreFactory = ResearchStore,
) -> dict[str, object]:
    if not isinstance(max_cycles, int) or isinstance(max_cycles, bool) or not 1 <= max_cycles <= 10:
        raise ValueError("max_cycles must be between 1 and 10")
    if not isinstance(cycle_timeout, int) or isinstance(cycle_timeout, bool) or not 30 <= cycle_timeout <= 3600:
        raise ValueError("cycle_timeout must be between 30 and 3600 seconds")
    store = store_factory(db_path)
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
                "search_cohort": "openalex|arxiv|crossref",
            }
        )
        if started_cycle.get("acquired") is False:
            stopped_reason = "lease_not_acquired"
            break
        started += 1
        try:
            result = command_runner(
                [
                    "pi",
                    "-p",
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
                    "Use the strategy_research_runtime extension to run exactly one bounded research cycle. Load the current cycle context, collect and assess sources, propose up to three hypotheses with required_data exactly [OHLCV], write and validate one candidate with WFO plus Monte Carlo evidence, record interpretation, finalize, then stop. Do not trade or modify the parent strategy/config/policy.",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
                timeout=cycle_timeout,
            )
        except subprocess.TimeoutExpired:
            store.set_cycle_status(started_cycle["cycle"]["id"], "INCOMPLETE", "supervisor timeout")
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
