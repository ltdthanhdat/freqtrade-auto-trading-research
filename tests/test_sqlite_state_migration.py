from __future__ import annotations

import sqlite3

import pytest

from scripts.migrate_sqlite_state import audit_database, backup_database, migrate_database


def make_sqlite_fixture(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE parent (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE child (
                id INTEGER PRIMARY KEY,
                parent_id INTEGER NOT NULL REFERENCES parent(id)
            );
            INSERT INTO parent(id, name) VALUES (1, 'one');
            INSERT INTO child(id, parent_id) VALUES (1, 1);
            """
        )
    return path


def test_backup_uses_sqlite_backup_and_preserves_logical_state(tmp_path):
    source = make_sqlite_fixture(tmp_path / "source.sqlite")
    destination = tmp_path / "state" / "research.sqlite"

    result = backup_database(source, destination)

    assert result["destination"]["integrity_check"] == "ok"
    assert result["destination"]["foreign_key_errors"] == []
    assert result["source"]["table_counts"] == result["destination"]["table_counts"]
    assert destination.stat().st_mode & 0o777 == 0o600


def test_migration_refuses_existing_destination_without_replace(tmp_path):
    source = make_sqlite_fixture(tmp_path / "source.sqlite")
    destination = make_sqlite_fixture(tmp_path / "destination.sqlite")

    with pytest.raises(FileExistsError):
        migrate_database(source, destination, tmp_path / "backups")


def test_verify_reports_corrupt_or_foreign_key_invalid_database(tmp_path):
    path = make_sqlite_fixture(tmp_path / "state.sqlite")
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("INSERT INTO child(parent_id) VALUES (999)")

    audit = audit_database(path)

    assert audit["foreign_key_errors"]
