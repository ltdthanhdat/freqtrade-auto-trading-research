from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4


def _connect_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)


def _table_counts(connection: sqlite3.Connection) -> dict[str, int]:
    names = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    counts: dict[str, int] = {}
    for name in names:
        escaped = name.replace('"', '""')
        counts[name] = int(connection.execute(f'SELECT COUNT(*) FROM "{escaped}"').fetchone()[0])
    return counts


def audit_database(path: Path) -> dict[str, object]:
    database = Path(path)
    if not database.is_file():
        raise FileNotFoundError(f"SQLite database is missing: {database}")
    result: dict[str, object] = {
        "path": str(database),
        "integrity_check": "error: unavailable",
        "foreign_key_errors": [],
        "user_version": None,
        "table_counts": {},
    }
    try:
        with _connect_readonly(database) as connection:
            integrity = [str(row[0]) for row in connection.execute("PRAGMA integrity_check")]
            result["integrity_check"] = "; ".join(integrity) if integrity else "error: no integrity result"
            result["foreign_key_errors"] = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]
            result["user_version"] = int(connection.execute("PRAGMA user_version").fetchone()[0])
            result["table_counts"] = _table_counts(connection)
    except sqlite3.DatabaseError as exc:
        result["integrity_check"] = f"error: {exc}"
    return result


def _assert_healthy(audit: dict[str, object], label: str) -> None:
    if audit.get("integrity_check") != "ok" or audit.get("foreign_key_errors"):
        raise RuntimeError(f"{label} database failed integrity checks: {audit}")


def backup_database(source: Path, destination: Path) -> dict[str, object]:
    source_path = Path(source)
    destination_path = Path(destination)
    source_audit = audit_database(source_path)
    _assert_healthy(source_audit, "source")
    if destination_path.exists():
        raise FileExistsError(f"SQLite destination already exists: {destination_path}")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.touch(mode=0o600, exist_ok=False)
    os.chmod(destination_path, 0o600)
    try:
        with _connect_readonly(source_path) as source_connection, sqlite3.connect(destination_path) as destination_connection:
            source_connection.backup(destination_connection)
            destination_connection.commit()
        os.chmod(destination_path, 0o600)
    except Exception:
        # Keep a failed destination for diagnosis, but never alter the source.
        raise
    destination_audit = audit_database(destination_path)
    _assert_healthy(destination_audit, "destination")
    equal = source_audit["table_counts"] == destination_audit["table_counts"]
    if not equal:
        raise RuntimeError("SQLite backup logical row counts differ")
    return {
        "source": source_audit,
        "destination": destination_audit,
        "logical_row_counts_equal": equal,
    }


def _write_report(path: Path, payload: dict[str, object]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False)
        + "\n"
    ).encode("utf-8")
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


def _remove_sqlite_file(path: Path) -> None:
    path.unlink()
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(f"{path}{suffix}")
        if sidecar.exists():
            sidecar.unlink()


def migrate_database(
    source: Path,
    destination: Path,
    backup_root: Path,
    *,
    replace: bool = False,
    report: Path | None = None,
) -> dict[str, object]:
    source_path = Path(source)
    destination_path = Path(destination)
    backup_directory = Path(backup_root)
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite source is missing: {source_path}")
    if source_path.resolve() == destination_path.resolve():
        raise ValueError("SQLite source and destination must differ")
    if destination_path.exists() and not replace:
        raise FileExistsError(f"SQLite destination already exists: {destination_path}")

    backup_directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    source_backup = backup_directory / f"source-{stamp}-{uuid4().hex[:8]}.sqlite"
    source_backup_result = backup_database(source_path, source_backup)

    if destination_path.exists():
        _remove_sqlite_file(destination_path)
    destination_result = backup_database(source_path, destination_path)
    result: dict[str, object] = {
        "source": destination_result["source"],
        "destination": destination_result["destination"],
        "source_backup": str(source_backup),
        "source_backup_audit": source_backup_result["destination"],
        "logical_row_counts_equal": destination_result["logical_row_counts_equal"],
    }
    _write_report(Path(report) if report is not None else backup_directory / "migration-report.json", result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit, back up, or migrate SQLite state")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.verify_only:
            result = audit_database(args.source)
            _assert_healthy(result, "source")
        else:
            if args.destination is None or args.backup_root is None:
                raise ValueError("--destination and --backup-root are required unless --verify-only is used")
            result = migrate_database(
                args.source,
                args.destination,
                args.backup_root,
                replace=args.replace,
                report=args.report,
            )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str))
        return 0
    except (OSError, RuntimeError, ValueError, sqlite3.DatabaseError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
