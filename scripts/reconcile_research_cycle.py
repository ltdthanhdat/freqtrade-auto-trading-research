from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from research_runtime import paths
from research_runtime.service import ResearchService
from research_runtime.store import ResearchStore
from scripts.run_summary import read_run_summary, write_run_summary


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _write_terminal_summary(
    artifacts: Path,
    run_key: str,
    *,
    status: str,
    phase: str,
    cycle: dict[str, Any] | None = None,
    started_at: str | None = None,
    reason: str | None = None,
    action: str | None = None,
) -> Path:
    completed_at = _now()
    existing: dict[str, Any] = {}
    try:
        existing = read_run_summary(artifacts, run_key)
    except (FileNotFoundError, ValueError):
        pass
    payload: dict[str, Any] = {
        **existing,
        "status": status,
        "phase": phase,
        "started_at": existing.get("started_at") or started_at or completed_at,
        "completed_at": completed_at,
    }
    if cycle is not None:
        payload.update(
            {
                "cycle_id": cycle.get("id"),
                "snapshot_sha256": cycle.get("snapshot_sha256"),
            }
        )
    if reason:
        payload["reason"] = reason
    if action:
        payload["reconciliation_action"] = action
    return write_run_summary(artifacts, run_key, payload)


def _result_line(result: dict[str, Any], summary: Path | None = None) -> str:
    cycle = result.get("cycle")
    output: dict[str, Any] = {
        "action": result.get("action", "NO_OP"),
        "cycle_id": cycle.get("id") if isinstance(cycle, dict) else None,
        "status": cycle.get("status") if isinstance(cycle, dict) else None,
    }
    if summary is not None:
        output["summary_path"] = str(summary)
    return json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reconcile a persisted research cycle")
    parser.add_argument("--db", type=Path, default=paths.research_db_path())
    parser.add_argument("--artifacts", type=Path, default=paths.research_artifact_root())
    parser.add_argument("--cycle-id")
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--observed-status", default="FAILED")
    parser.add_argument("--reason", default="external research task reconciliation")
    parser.add_argument("--run-key")
    parser.add_argument("--task-id")
    parser.add_argument("--container-id")
    parser.add_argument("--lease-owner")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        service = ResearchService(ResearchStore(args.db), args.artifacts)
        cycle: dict[str, Any] | None = None
        if args.cycle_id:
            cycle = service.store.get_cycle(args.cycle_id)
        elif args.run_key:
            cycle = service.store.find_cycle_by_airflow_run_key(args.run_key)
        elif args.latest:
            cycles = service.store.list_cycles(limit=1)
            cycle = cycles[0] if cycles else None

        if cycle is None:
            result: dict[str, Any] = {"action": "NO_OP", "cycle": None}
            summary = None
            if args.run_key and str(args.observed_status).upper() in {"FAILED", "TIMEOUT", "MISSING"}:
                summary = _write_terminal_summary(
                    args.artifacts,
                    args.run_key,
                    status="INCOMPLETE",
                    phase="reconcile_cycle",
                    reason=args.reason,
                    action="NO_OP",
                )
            print(_result_line(result, summary))
            return 0

        result = service.call(
            "reconcile_cycle",
            {
                "cycle_id": cycle["id"],
                "observed_status": args.observed_status,
                "reason": args.reason,
                "observed_task_id": args.task_id,
                "observed_container_id": args.container_id,
                "lease_owner": args.lease_owner,
            },
        )
        summary = None
        reconciled_cycle = result.get("cycle")
        if args.run_key and isinstance(reconciled_cycle, dict) and reconciled_cycle.get("status") != "RUNNING":
            summary = _write_terminal_summary(
                args.artifacts,
                args.run_key,
                status=str(reconciled_cycle.get("status") or "INCOMPLETE"),
                phase="reconcile_cycle",
                cycle=reconciled_cycle,
                reason=args.reason,
                action=str(result.get("action") or "NO_OP"),
            )
        print(_result_line(result, summary))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(
            json.dumps(
                {"action": "ERROR", "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
