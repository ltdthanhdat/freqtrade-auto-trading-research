from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from research_runtime import paths
from scripts.run_summary import read_run_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish a terminal research run summary")
    parser.add_argument("--artifacts", type=Path, default=paths.research_artifact_root())
    parser.add_argument("--run-key", required=True)
    return parser


def _report_payload(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "airflow_run_key": summary.get("airflow_run_key"),
        "status": summary.get("status"),
        "cycle_id": summary.get("cycle_id"),
        "snapshot_sha256": summary.get("snapshot_sha256"),
        "manifest_path": summary.get("manifest_path") or summary.get("snapshot_manifest_path"),
        "report_path": summary.get("report_path"),
        "summary_path": summary.get("summary_path"),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = read_run_summary(args.artifacts, args.run_key)
        print(json.dumps(_report_payload(summary), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, sort_keys=True, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
