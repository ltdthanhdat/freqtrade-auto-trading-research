from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from collections.abc import Mapping
from uuid import uuid4


def directory_sha256(datadir: Path) -> str:
    root = Path(datadir)
    if not root.is_dir():
        raise FileNotFoundError(f"snapshot directory is missing: {root}")
    digest = hashlib.sha256()
    for path in sorted(path for path in root.rglob("*") if path.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: Mapping[str, object]) -> str:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(destination)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def publish_snapshot(staging_datadir: Path, final_datadir: Path) -> None:
    staging = Path(staging_datadir)
    final = Path(final_datadir)
    if not staging.is_dir():
        raise FileNotFoundError(f"staging snapshot directory is missing: {staging}")
    if final.exists():
        raise FileExistsError(f"sealed snapshot already exists: {final}")
    final.parent.mkdir(parents=True, exist_ok=True)
    if staging.parent.stat().st_dev != final.parent.stat().st_dev:
        raise OSError("snapshot staging and final directories must share a filesystem")
    staging.rename(final)
