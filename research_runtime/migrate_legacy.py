from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core import HypothesisState
from .store import ResearchStore


_ARTIFACT_SUFFIXES = {".csv", ".feather", ".json", ".py", ".txt", ".zip"}
_DEFAULT_TIME = "1970-01-01T00:00:00Z"


@dataclass(frozen=True)
class MigrationReport:
    hypotheses: int
    experiments: int
    artifacts: int
    unresolved_links: tuple[str, ...]
    hash_mismatches: tuple[str, ...]
    integrity_check: str
    foreign_key_errors: tuple[tuple[Any, ...], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "hypotheses": self.hypotheses,
            "experiments": self.experiments,
            "artifacts": self.artifacts,
            "unresolved_links": list(self.unresolved_links),
            "hash_mismatches": list(self.hash_mismatches),
            "integrity_check": self.integrity_check,
            "foreign_key_errors": [list(error) for error in self.foreign_key_errors],
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "legacy"


def _legacy_files(source_root: Path, family: str) -> list[Path]:
    family_root = source_root / family
    files = []
    for path in family_root.rglob("*"):
        relative_parts = path.relative_to(family_root).parts
        if path.is_file() and "__pycache__" not in relative_parts:
            if "runs" in relative_parts or "candidates" in relative_parts or path.suffix.lower() in _ARTIFACT_SUFFIXES:
                files.append(path)
    return sorted(files)


def _copy_artifacts(
    source_root: Path, artifact_root: Path, families: list[str]
) -> tuple[int, tuple[str, ...]]:
    count = 0
    mismatches: list[str] = []
    for family in families:
        family_root = source_root / family
        for source in _legacy_files(source_root, family):
            relative = source.relative_to(family_root)
            destination = artifact_root / "legacy" / family / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            source_hash = _sha256(source)
            if not destination.exists():
                shutil.copyfile(source, destination)
            if _sha256(destination) != source_hash:
                mismatches.append(str(relative))
            count += 1
    return count, tuple(sorted(set(mismatches)))


def _conclusion_state(body: str) -> HypothesisState:
    conclusion = body.lower().split("## conclusion", 1)[-1]
    if "discard" in conclusion or "reject" in conclusion:
        return HypothesisState.REJECTED
    if "keep" in conclusion:
        return HypothesisState.NEEDS_REVIEW
    return HypothesisState.SCORED


def _hypothesis_id_map(source_root: Path, families: list[str]):
    records: list[tuple[str, Path, str, str]] = []
    used: set[str] = set()
    aliases: dict[str, list[str]] = {}
    for family in families:
        for path in sorted((source_root / family / "hypotheses").glob("*.md")):
            stem = path.stem
            record_id = stem if stem not in used else f"{family}--{stem}"
            used.add(record_id)
            records.append((family, path, stem, record_id))
            for alias in {stem, stem.split("_", 1)[0]}:
                aliases.setdefault(alias.casefold(), []).append(record_id)
    return records, aliases


def _resolve_experiment_hypothesis(
    body: str,
    stem: str,
    aliases: dict[str, list[str]],
) -> tuple[str | None, str | None]:
    explicit_tokens = re.findall(r"\b(?:H(?:-[A-Za-z0-9_]+)+|H\d+)\b", body, re.IGNORECASE)
    if explicit_tokens:
        unknown: list[str] = []
        for token in explicit_tokens:
            ids = aliases.get(token.casefold())
            if ids:
                if len(set(ids)) == 1:
                    return ids[0], None
                return None, f"ambiguous experiment link {stem}: {sorted(set(ids))}"
            unknown.append(token)
        return None, f"unresolved experiment link {stem}: {unknown}"
    numbers = set(re.findall(r"\d+", stem))
    if numbers:
        candidates = {
            record_id
            for alias, ids in aliases.items()
            if numbers.intersection(re.findall(r"\d+", alias))
            for record_id in ids
        }
        if len(candidates) == 1:
            return next(iter(candidates)), None
    return None, f"unresolved experiment link {stem}"


def _experiment_payload(
    family: str,
    path: Path,
    body: str,
    hypothesis: dict[str, Any],
    source_root: Path,
) -> dict[str, Any]:
    experiment_id = path.stem
    digest = _sha256(path)
    relative = path.relative_to(source_root).as_posix()
    return {
        "id": experiment_id,
        "cycle_id": hypothesis["cycle_id"],
        "hypothesis_id": hypothesis["id"],
        "parent_strategy": "legacy-import",
        "parent_sha256": digest,
        "changed_variable": "legacy-import",
        "config_path": f"legacy/{family}/unknown-config",
        "config_sha256": digest,
        "pairs": [],
        "timeframes": ["1m", "30m", "1h"],
        "timeframe_detail": "1m",
        "snapshot_path": f"legacy/{family}/unknown-snapshot",
        "snapshot_sha256": digest,
        "policy_path": f"legacy/{family}/unknown-policy",
        "policy_sha256": digest,
        "strategy_name": "legacy-import",
        "strategy_path": f"legacy/{family}/candidates",
        "start_at": _DEFAULT_TIME,
        "end_at": _DEFAULT_TIME,
        "status": "IMPORTED",
        "metadata": {"legacy_path": relative, "legacy_body": body},
    }


def _run_groups(source_root: Path, family: str) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = {}
    runs_root = source_root / family / "runs"
    if not runs_root.exists():
        return groups
    for path in sorted(runs_root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.relative_to(runs_root).parts:
            continue
        relative = path.relative_to(runs_root)
        group = relative.parts[0] if len(relative.parts) > 1 else relative.name
        groups.setdefault(group, []).append(path)
    return groups


def import_legacy(source_root: str | Path, store: ResearchStore, artifact_root: str | Path) -> MigrationReport:
    source = Path(source_root).resolve()
    artifacts = Path(artifact_root).resolve()
    if not source.is_dir():
        raise ValueError(f"legacy source directory does not exist: {source}")
    families = sorted(path.name for path in source.iterdir() if path.is_dir() and path.name != "__pycache__")
    hypothesis_records, aliases = _hypothesis_id_map(source, families)
    imported_hypotheses: dict[str, dict[str, Any]] = {}
    for family, path, _stem, hypothesis_id in hypothesis_records:
        body = path.read_text(encoding="utf-8", errors="replace")
        cycle_id = f"legacy-{_slug(family)}-{_slug(hypothesis_id)}"
        store.ensure_cycle(cycle_id)
        hypothesis = store.insert_hypothesis(
            cycle_id,
            {
                "id": hypothesis_id,
                "thesis": body.splitlines()[0].lstrip("# ") or hypothesis_id,
                "mechanism": hypothesis_id,
                "market_scope": "legacy research",
                "required_data": ["OHLCV"],
                "falsifier": "legacy result requires re-validation",
                "scores": {
                    "evidence_quality": 20,
                    "reproducibility": 20,
                    "ohlcv_transferability": 15,
                    "novelty": 5,
                    "falsifiability": 10,
                },
                "state": _conclusion_state(body),
                "metadata": {
                    "family": family,
                    "legacy_path": path.relative_to(source).as_posix(),
                    "legacy_body": body,
                },
            },
        )
        imported_hypotheses[hypothesis_id] = hypothesis

    experiments = 0
    unresolved: list[str] = []
    experiment_by_family: dict[str, list[str]] = {family: [] for family in families}
    for family in families:
        for path in sorted((source / family / "experiments").glob("*.md")):
            body = path.read_text(encoding="utf-8", errors="replace")
            hypothesis_id, error = _resolve_experiment_hypothesis(body, path.stem, aliases)
            if error:
                unresolved.append(f"{family}/{path.name}: {error}")
                continue
            hypothesis = imported_hypotheses[hypothesis_id]
            payload = _experiment_payload(family, path, body, hypothesis, source)
            store.insert_experiment(payload)
            experiment_by_family[family].append(payload["id"])
            experiments += 1

    artifact_count, hash_mismatches = _copy_artifacts(source, artifacts, families)
    for family in families:
        experiment_id = experiment_by_family[family][0] if experiment_by_family[family] else None
        if experiment_id is None:
            continue
        for group, paths in _run_groups(source, family).items():
            manifest = []
            for path in paths:
                relative = path.relative_to(source).as_posix()
                manifest.append({"path": f"legacy/{relative}", "size": path.stat().st_size, "sha256": _sha256(path)})
            run_id = f"legacy-run-{_slug(family)}-{_slug(group)}"
            if any(run["id"] == run_id for run in store.list_runs(experiment_id)):
                continue
            store.record_run(
                {
                    "id": run_id,
                    "experiment_id": experiment_id,
                    "kind": "legacy",
                    "status": "IMPORTED",
                    "verdict": None,
                    "metrics": {},
                    "artifact_manifest": manifest,
                    "created_at": _DEFAULT_TIME,
                    "completed_at": _DEFAULT_TIME,
                }
            )
    integrity = store.integrity_report()
    return MigrationReport(
        hypotheses=len(hypothesis_records),
        experiments=experiments,
        artifacts=artifact_count,
        unresolved_links=tuple(sorted(unresolved)),
        hash_mismatches=hash_mismatches,
        integrity_check=integrity["integrity_check"],
        foreign_key_errors=tuple(tuple(error) for error in integrity["foreign_key_errors"]),
    )


def _backup_database(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(source)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
        destination_connection.commit()
    finally:
        destination_connection.close()
        source_connection.close()


def _write_report(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import and verify legacy research")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, default=Path("user_data/research-artifacts"))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    store = ResearchStore(args.db)
    if args.backup:
        _backup_database(args.db, args.backup)
    if args.source:
        report = import_legacy(args.source, store, args.artifacts)
    else:
        integrity = store.integrity_report()
        report = MigrationReport(0, 0, 0, (), (), integrity["integrity_check"], tuple(tuple(e) for e in integrity["foreign_key_errors"]))
    payload = report.as_dict()
    _write_report(args.report, payload)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 2 if report.unresolved_links or report.hash_mismatches or report.integrity_check != "ok" or report.foreign_key_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
