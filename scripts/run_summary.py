from __future__ import annotations

import json
import os
from pathlib import Path
import re
from collections.abc import Mapping
from uuid import uuid4


_RUN_KEY = re.compile(r"[^A-Za-z0-9_.-]")
def safe_run_key(run_key: str) -> str:
    raw = str(run_key or "").strip()
    safe = _RUN_KEY.sub("-", raw)
    if not safe or safe in {".", ".."}:
        raise ValueError("airflow run key is empty after sanitization")
    return safe


def summary_path(root: str | Path, run_key: str) -> Path:
    return Path(root) / "runs" / safe_run_key(run_key) / "run-summary.json"


def read_run_summary(root: str | Path, run_key: str) -> dict[str, object]:
    path = summary_path(root, run_key)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"run summary is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"run summary is corrupt: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"run summary must be an object: {path}")
    if payload.get("airflow_run_key") != str(run_key).strip():
        raise ValueError("run summary airflow_run_key does not match requested key")
    return payload


def write_run_summary(
    root: str | Path, run_key: str, payload: Mapping[str, object]
) -> Path:
    raw_run_key = str(run_key or "").strip()
    safe_run_key(raw_run_key)
    if not isinstance(payload, Mapping):
        raise ValueError("run summary payload must be an object")
    data = dict(payload)
    supplied_key = data.get("airflow_run_key")
    if supplied_key not in (None, raw_run_key):
        raise ValueError("airflow_run_key does not match requested run key")
    if "schema_version" in data and data["schema_version"] != 1:
        raise ValueError("unsupported run summary schema_version")
    data["schema_version"] = 1
    data["airflow_run_key"] = raw_run_key
    if "completed_at" not in data or data["completed_at"] in (None, ""):
        raise ValueError("run summary requires completed_at")
    for field in ("status", "phase", "started_at"):
        if field not in data or data[field] in (None, ""):
            raise ValueError(f"run summary requires {field}")
    if not isinstance(data["status"], str) or not data["status"].strip():
        raise ValueError("run summary requires status")
    if not isinstance(data["phase"], str) or not data["phase"].strip():
        raise ValueError("run summary requires phase")

    path = summary_path(root, raw_run_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"existing run summary is corrupt: {path}") from exc
        if not isinstance(existing, dict) or existing.get("airflow_run_key") != raw_run_key:
            raise ValueError("cannot overwrite run summary from another airflow_run_key")

    encoded = (
        json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False)
        + "\n"
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return path
