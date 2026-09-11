from __future__ import annotations

import ast
import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path


_STRATEGY_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,79}$")


@dataclass(frozen=True)
class CandidateIdentity:
    path: Path
    sha256: str
    strategy_name: str


def write_candidate(
    artifact_root: str | Path,
    cycle_id: str,
    strategy_name: str,
    source: str,
) -> CandidateIdentity:
    if not isinstance(strategy_name, str) or not _STRATEGY_NAME.fullmatch(strategy_name):
        raise ValueError("invalid strategy name")
    if not isinstance(source, str):
        raise ValueError("candidate source must be text")
    try:
        tree = ast.parse(source, filename=f"{strategy_name}.py")
    except SyntaxError as exc:
        raise ValueError(f"candidate syntax is invalid: {exc.msg}") from exc
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    if len(classes) != 1 or classes[0].name != strategy_name:
        raise ValueError("candidate must contain exactly one class with the strategy name")

    artifact_dir = Path(artifact_root).resolve()
    cycle_dir = (artifact_dir / cycle_id).resolve()
    if artifact_dir not in cycle_dir.parents:
        raise ValueError("cycle path escapes artifact root")
    candidate_dir = (cycle_dir / "candidate").resolve()
    path = (candidate_dir / f"{strategy_name}.py").resolve()
    if path.parent != candidate_dir:
        raise ValueError("candidate path escapes cycle directory")
    candidate_dir.mkdir(parents=True, exist_ok=True)
    siblings = [item for item in candidate_dir.glob("*.py") if item.is_file()]
    digest = hashlib.sha256(source.encode()).hexdigest()
    if siblings and path not in siblings:
        raise ValueError("candidate budget exhausted")
    if path.exists():
        if path.read_text() != source:
            raise ValueError("candidate already exists with different content")
        return CandidateIdentity(path, digest, strategy_name)

    handle, temporary_name = tempfile.mkstemp(prefix=f".{strategy_name}.", suffix=".tmp", dir=candidate_dir)
    try:
        with os.fdopen(handle, "w") as temporary:
            temporary.write(source)
            temporary.flush()
            os.fsync(temporary.fileno())
        Path(temporary_name).replace(path)
    finally:
        temporary_path = Path(temporary_name)
        if temporary_path.exists():
            temporary_path.unlink()
    return CandidateIdentity(path, digest, strategy_name)
