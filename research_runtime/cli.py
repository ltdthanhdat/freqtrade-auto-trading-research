from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import paths
from .service import ResearchService
from .store import ResearchStore


def _error(code: str, *details: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "details": list(details)}}


def _response(service: ResearchService, request: Any) -> dict[str, Any]:
    if not isinstance(request, dict):
        return _error("invalid_json", "request must be a JSON object")
    tool = request.get("tool")
    payload = request.get("payload", {})
    if not isinstance(tool, str):
        return _error("validation_error", "tool is required")
    try:
        result = service.call(tool, payload)
    except KeyError:
        return _error("unknown_operation", f"unknown operation: {tool}")
    except ValueError as exc:
        return _error("validation_error", str(exc))
    except Exception as exc:  # pragma: no cover - protects the JSON transport boundary
        return _error("runtime_error", str(exc))
    return {"ok": True, **result}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="JSON-lines research runtime")
    parser.add_argument("--db", type=Path, default=paths.research_db_path())
    parser.add_argument("--artifacts", type=Path, default=paths.research_artifact_root())
    args = parser.parse_args(argv)
    service = ResearchService(ResearchStore(args.db), args.artifacts)
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            result = _error("invalid_json", "request must be a JSON object")
        else:
            result = _response(service, request)
        sys.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
