from __future__ import annotations

import ast
import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path


AST_POLICY_VERSION = "ast-policy-v1"
_STRATEGY_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,79}$")
_BLOCKED_IMPORT_ROOTS = {
    "asyncio",
    "ctypes",
    "ftplib",
    "glob",
    "http",
    "importlib",
    "multiprocessing",
    "os",
    "pathlib",
    "pickle",
    "requests",
    "shutil",
    "socket",
    "sqlite3",
    "subprocess",
    "sys",
    "urllib",
}
_BLOCKED_CALL_NAMES = {
    "__import__",
    "compile",
    "eval",
    "exec",
    "getattr",
    "setattr",
    "delattr",
    "open",
    "input",
    "help",
}
_BLOCKED_ATTRIBUTE_NAMES = {
    "cursor",
    "execute",
    "executemany",
    "executescript",
    "getenv",
    "environ",
    "read_csv",
    "read_feather",
    "read_json",
    "read_parquet",
    "read_pickle",
    "read_sql",
    "read_sql_query",
    "read_sql_table",
    "to_csv",
    "to_excel",
    "to_feather",
    "to_json",
    "to_parquet",
    "to_pickle",
    "unlink",
    "remove",
    "rename",
    "replace",
    "mkdir",
    "makedirs",
    "rmdir",
    "write_text",
    "write_bytes",
}


@dataclass(frozen=True)
class CandidateIdentity:
    path: Path
    sha256: str
    strategy_name: str
    candidate_sha256: str | None = None
    ast_policy_version: str = AST_POLICY_VERSION
    class_identity: str = ""
    dependency_hashes: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.candidate_sha256 is None:
            object.__setattr__(self, "candidate_sha256", self.sha256)

    @property
    def dependency_sha256(self) -> str:
        encoded = "\n".join(f"{path}\0{digest}" for path, digest in self.dependency_hashes)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _module_root(value: str) -> str:
    return value.split(".", 1)[0].casefold()


def _class_identity(tree: ast.Module, strategy_name: str, *, identity_bound: bool) -> str:
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    if len(classes) != 1 or classes[0].name != strategy_name:
        raise ValueError("candidate must contain exactly one class with the strategy name")
    candidate = classes[0]
    bases = []
    for base in candidate.bases:
        if isinstance(base, ast.Name):
            bases.append(base.id)
        elif isinstance(base, ast.Attribute):
            bases.append(base.attr)
        else:
            bases.append(ast.dump(base, annotate_fields=False))
    if identity_bound and "IStrategy" not in bases:
        raise ValueError("identity-bound candidate must inherit from IStrategy")
    return f"{candidate.name}({','.join(bases)})"


def validate_candidate_source(
    source: str,
    strategy_name: str,
    *,
    identity_bound: bool,
) -> ast.Module:
    if not isinstance(source, str):
        raise ValueError("candidate source must be text")
    if not isinstance(strategy_name, str) or not _STRATEGY_NAME.fullmatch(strategy_name):
        raise ValueError("invalid strategy name")
    try:
        tree = ast.parse(source, filename=f"{strategy_name}.py")
    except SyntaxError as exc:
        raise ValueError(f"candidate syntax is invalid: {exc.msg}") from exc

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""]
        else:
            modules = []
        for module in modules:
            if _module_root(module) in _BLOCKED_IMPORT_ROOTS:
                raise ValueError(f"candidate policy {AST_POLICY_VERSION} rejects import {module}")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _BLOCKED_CALL_NAMES:
                raise ValueError(
                    f"candidate policy {AST_POLICY_VERSION} rejects call {node.func.id}"
                )
            if isinstance(node.func, ast.Attribute) and node.func.attr in _BLOCKED_ATTRIBUTE_NAMES:
                raise ValueError(
                    f"candidate policy {AST_POLICY_VERSION} rejects attribute {node.func.attr}"
                )
        if isinstance(node, ast.Name) and node.id in {"__builtins__", "environ"}:
            raise ValueError(
                f"candidate policy {AST_POLICY_VERSION} rejects environment or builtin access"
            )

    _class_identity(tree, strategy_name, identity_bound=identity_bound)
    return tree


def _identity(path: Path, digest: str, strategy_name: str, tree: ast.Module) -> CandidateIdentity:
    return CandidateIdentity(
        path=path,
        sha256=digest,
        strategy_name=strategy_name,
        candidate_sha256=digest,
        ast_policy_version=AST_POLICY_VERSION,
        class_identity=_class_identity(tree, strategy_name, identity_bound=False),
    )


def write_candidate(
    artifact_root: str | Path,
    cycle_id: str,
    strategy_name: str,
    source: str,
) -> CandidateIdentity:
    if not isinstance(strategy_name, str) or not _STRATEGY_NAME.fullmatch(strategy_name):
        raise ValueError("invalid strategy name")
    tree = validate_candidate_source(source, strategy_name, identity_bound=False)

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
        return _identity(path, digest, strategy_name, tree)

    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{strategy_name}.", suffix=".tmp", dir=candidate_dir
    )
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
    return _identity(path, digest, strategy_name, tree)
