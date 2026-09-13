from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from .core import (
    CycleStatus,
    HypothesisState,
    canonical_json,
    next_cycle_state_allowed,
    next_state_allowed,
    score_hypothesis,
)


SCHEMA_VERSION = 3
SOURCE_BUDGET = 100
HYPOTHESIS_BUDGET = 3
CANDIDATE_BUDGET = 1


SCHEMA = """
CREATE TABLE cycles (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  stage TEXT NOT NULL,
  source_count INTEGER NOT NULL DEFAULT 0 CHECK(source_count BETWEEN 0 AND 100),
  hypothesis_count INTEGER NOT NULL DEFAULT 0 CHECK(hypothesis_count BETWEEN 0 AND 3),
  candidate_count INTEGER NOT NULL DEFAULT 0 CHECK(candidate_count BETWEEN 0 AND 1),
  lease_until TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  dataset TEXT,
  requested_timerange TEXT,
  policy_sha256 TEXT,
  search_cohort TEXT,
  holdout_start TEXT,
  holdout_end TEXT
);

CREATE TABLE sources (
  id TEXT PRIMARY KEY,
  cycle_id TEXT NOT NULL REFERENCES cycles(id),
  provider TEXT NOT NULL,
  canonical_url TEXT,
  doi TEXT,
  title TEXT NOT NULL,
  excerpt TEXT NOT NULL,
  license TEXT,
  retrieved_at TEXT NOT NULL,
  fingerprint TEXT NOT NULL UNIQUE,
  metadata_json TEXT NOT NULL,
  UNIQUE(provider, canonical_url),
  UNIQUE(doi)
);

CREATE TABLE hypotheses (
  id TEXT PRIMARY KEY,
  cycle_id TEXT NOT NULL REFERENCES cycles(id),
  thesis TEXT NOT NULL,
  mechanism TEXT NOT NULL,
  market_scope TEXT NOT NULL,
  required_data_json TEXT NOT NULL,
  falsifier TEXT NOT NULL,
  evidence_quality INTEGER NOT NULL,
  reproducibility INTEGER NOT NULL,
  ohlcv_transferability INTEGER NOT NULL,
  novelty INTEGER NOT NULL,
  falsifiability INTEGER NOT NULL,
  total_score INTEGER NOT NULL CHECK(total_score BETWEEN 0 AND 100),
  state TEXT NOT NULL,
  candidate_path TEXT,
  candidate_sha256 TEXT,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE hypothesis_sources (
  hypothesis_id TEXT NOT NULL REFERENCES hypotheses(id),
  source_id TEXT NOT NULL REFERENCES sources(id),
  stance TEXT NOT NULL CHECK(stance IN ('SUPPORT', 'CONTRADICT')),
  note TEXT NOT NULL,
  PRIMARY KEY(hypothesis_id, source_id, stance)
);

CREATE TABLE experiments (
  id TEXT PRIMARY KEY,
  cycle_id TEXT NOT NULL REFERENCES cycles(id),
  hypothesis_id TEXT NOT NULL REFERENCES hypotheses(id),
  parent_strategy TEXT NOT NULL,
  parent_sha256 TEXT NOT NULL,
  changed_variable TEXT NOT NULL,
  config_path TEXT NOT NULL,
  config_sha256 TEXT NOT NULL,
  pairs_json TEXT NOT NULL,
  timeframes_json TEXT NOT NULL,
  timeframe_detail TEXT NOT NULL,
  snapshot_path TEXT NOT NULL,
  snapshot_sha256 TEXT NOT NULL,
  policy_path TEXT NOT NULL,
  policy_sha256 TEXT NOT NULL,
  strategy_name TEXT NOT NULL,
  strategy_path TEXT NOT NULL,
  start_at TEXT NOT NULL,
  end_at TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE runs (
  id TEXT PRIMARY KEY,
  experiment_id TEXT NOT NULL REFERENCES experiments(id),
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  verdict TEXT,
  metrics_json TEXT NOT NULL,
  artifact_manifest_json TEXT NOT NULL,
  error_code TEXT,
  created_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE TABLE state_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  from_state TEXT,
  to_state TEXT NOT NULL,
  actor TEXT NOT NULL,
  reason TEXT NOT NULL,
  cycle_id TEXT NOT NULL REFERENCES cycles(id),
  run_id TEXT REFERENCES runs(id),
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE validation_windows (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cycle_id TEXT NOT NULL REFERENCES cycles(id),
  dataset TEXT NOT NULL,
  requested_timerange TEXT NOT NULL,
  policy_sha256 TEXT NOT NULL,
  verdict TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(dataset, requested_timerange, policy_sha256, cycle_id)
);
"""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime | str | None) -> str:
    if value is None:
        value = _utc_now()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    parsed = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(parsed).astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    except ValueError as exc:
        raise ValueError(f"invalid timestamp: {value}") from exc


def _as_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _json_text(value: Any, field: str) -> str:
    try:
        return canonical_json(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid JSON field: {field}") from exc


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return None if row is None else dict(row)


def _normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    doi = value.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix) :]
    return doi


class ResearchStore:
    def __init__(self, path: str | Path, lease_seconds: int = 3600):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lease_seconds = lease_seconds
        with self.connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                connection.executescript(SCHEMA)
                self._migrate_v2(connection)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            elif version == 1:
                self._migrate_v1(connection)
                self._migrate_v2(connection)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            elif version == 2:
                self._migrate_v2(connection)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            elif version != SCHEMA_VERSION:
                raise RuntimeError(f"unsupported research schema version: {version}")
            self._reconcile_legacy_state(connection)

    @staticmethod
    def _migrate_v1(connection: sqlite3.Connection) -> None:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(cycles)")}
        for name in ("dataset", "requested_timerange", "policy_sha256", "search_cohort", "holdout_start", "holdout_end"):
            if name not in columns:
                connection.execute(f"ALTER TABLE cycles ADD COLUMN {name} TEXT")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS validation_windows (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              cycle_id TEXT NOT NULL REFERENCES cycles(id),
              dataset TEXT NOT NULL,
              requested_timerange TEXT NOT NULL,
              policy_sha256 TEXT NOT NULL,
              verdict TEXT NOT NULL,
              created_at TEXT NOT NULL,
              UNIQUE(dataset, requested_timerange, policy_sha256, cycle_id)
            )
            """
        )

    @staticmethod
    def _migrate_v2(connection: sqlite3.Connection) -> None:
        cycle_columns = {row[1] for row in connection.execute("PRAGMA table_info(cycles)")}
        for name in ("ranking_sealed_at", "ranking_json", "ranking_sha256"):
            if name not in cycle_columns:
                connection.execute(f"ALTER TABLE cycles ADD COLUMN {name} TEXT")

        hypothesis_columns = {row[1] for row in connection.execute("PRAGMA table_info(hypotheses)")}
        for name in ("family_id", "plan_json", "plan_sha256", "approval_blocked_reason"):
            if name not in hypothesis_columns:
                connection.execute(f"ALTER TABLE hypotheses ADD COLUMN {name} TEXT")

        experiment_columns = {row[1] for row in connection.execute("PRAGMA table_info(experiments)")}
        if "oos_partitions_json" not in experiment_columns:
            connection.execute("ALTER TABLE experiments ADD COLUMN oos_partitions_json TEXT NOT NULL DEFAULT '[]'")
        if "owner_id" not in experiment_columns:
            connection.execute("ALTER TABLE experiments ADD COLUMN owner_id TEXT")

        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS cycle_sources (
              cycle_id TEXT NOT NULL REFERENCES cycles(id),
              source_id TEXT NOT NULL REFERENCES sources(id),
              observed_at TEXT NOT NULL,
              PRIMARY KEY (cycle_id, source_id)
            );
            CREATE TABLE IF NOT EXISTS source_assessments (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              cycle_id TEXT NOT NULL,
              source_id TEXT NOT NULL,
              relevance TEXT,
              asset TEXT,
              timeframe TEXT,
              mechanism TEXT,
              assessment_json TEXT NOT NULL CHECK(json_valid(assessment_json)),
              actor TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY (cycle_id, source_id)
                REFERENCES cycle_sources(cycle_id, source_id)
            );
            CREATE TABLE IF NOT EXISTS legacy_evidence_quarantine (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              hypothesis_id TEXT,
              source_id TEXT,
              legacy_stance TEXT,
              legacy_note TEXT,
              reason TEXT NOT NULL,
              original_row_json TEXT NOT NULL CHECK(json_valid(original_row_json)),
              original_sha256 TEXT NOT NULL,
              quarantined_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS comparison_cohorts (
              id TEXT PRIMARY KEY,
              dataset TEXT NOT NULL,
              snapshot_sha256 TEXT NOT NULL,
              comparison_start_at TEXT NOT NULL,
              comparison_end_at TEXT NOT NULL,
              holdout_start_at TEXT NOT NULL,
              holdout_end_at TEXT NOT NULL,
              selection_rule_json TEXT NOT NULL CHECK(json_valid(selection_rule_json)),
              manifest_sha256 TEXT NOT NULL,
              status TEXT NOT NULL CHECK(status IN ('SEALED', 'SELECTED', 'CLOSED')),
              created_at TEXT NOT NULL,
              sealed_at TEXT NOT NULL,
              CHECK(comparison_start_at < comparison_end_at),
              CHECK(holdout_start_at < holdout_end_at)
            );
            CREATE TABLE IF NOT EXISTS comparison_cohort_members (
              cohort_id TEXT NOT NULL REFERENCES comparison_cohorts(id),
              cycle_id TEXT NOT NULL REFERENCES cycles(id),
              hypothesis_id TEXT NOT NULL REFERENCES hypotheses(id),
              candidate_sha256 TEXT NOT NULL,
              plan_sha256 TEXT NOT NULL,
              PRIMARY KEY (cohort_id, candidate_sha256),
              UNIQUE (cohort_id, cycle_id, hypothesis_id)
            );
            CREATE TABLE IF NOT EXISTS oos_partition_consumptions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              dataset TEXT NOT NULL,
              snapshot_sha256 TEXT NOT NULL,
              kind TEXT NOT NULL CHECK(kind IN ('WFO_OOS', 'HOLDOUT', 'COMPARISON_OOS')),
              start_at TEXT NOT NULL,
              end_at TEXT NOT NULL,
              owner_id TEXT NOT NULL,
              cycle_id TEXT NOT NULL REFERENCES cycles(id),
              experiment_id TEXT NOT NULL REFERENCES experiments(id),
              run_id TEXT NOT NULL REFERENCES runs(id),
              verdict TEXT NOT NULL,
              consumed_at TEXT NOT NULL,
              CHECK(start_at < end_at),
              UNIQUE(snapshot_sha256, kind, start_at, end_at, owner_id)
            );
            """
        )

        connection.execute(
            "INSERT OR IGNORE INTO cycle_sources (cycle_id, source_id, observed_at) "
            "SELECT cycle_id, id, retrieved_at FROM sources"
        )
        connection.execute(
            "UPDATE cycles SET source_count = "
            "(SELECT COUNT(*) FROM cycle_sources WHERE cycle_sources.cycle_id = cycles.id)"
        )

        source_link_columns = {row[1] for row in connection.execute("PRAGMA table_info(hypothesis_sources)")}
        legacy_table = "hypothesis_sources_legacy_v2"
        if "evidence_json" not in source_link_columns:
            if not any(row[0] == legacy_table for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")):
                connection.execute("ALTER TABLE hypothesis_sources RENAME TO hypothesis_sources_legacy_v2")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS hypothesis_sources (
                  hypothesis_id TEXT NOT NULL REFERENCES hypotheses(id),
                  source_id TEXT NOT NULL REFERENCES sources(id),
                  stance TEXT NOT NULL CHECK(stance IN ('SUPPORT', 'CONTRADICT')),
                  note TEXT NOT NULL,
                  evidence_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(evidence_json)),
                  PRIMARY KEY(hypothesis_id, source_id)
                )
                """
            )
            affected: set[str] = set()
            if any(row[0] == legacy_table for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")):
                legacy_rows = [
                    dict(row)
                    for row in connection.execute(f"SELECT rowid AS legacy_rowid, * FROM {legacy_table} ORDER BY rowid ASC")
                ]
                grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
                reasons: dict[int, str] = {}
                for original in legacy_rows:
                    hypothesis_id = original.get("hypothesis_id")
                    source_id = original.get("source_id")
                    hypothesis = connection.execute(
                        "SELECT cycle_id FROM hypotheses WHERE id = ?", (hypothesis_id,)
                    ).fetchone()
                    source = connection.execute(
                        "SELECT id FROM sources WHERE id = ?", (source_id,)
                    ).fetchone()
                    if hypothesis is None or source is None:
                        reasons[original["legacy_rowid"]] = "unknown hypothesis or source"
                    elif connection.execute(
                        "SELECT 1 FROM cycle_sources WHERE cycle_id = ? AND source_id = ?",
                        (hypothesis["cycle_id"], source_id),
                    ).fetchone() is None:
                        reasons[original["legacy_rowid"]] = "cross-cycle or missing cycle provenance"
                    elif original.get("stance") not in {"SUPPORT", "CONTRADICT"}:
                        reasons[original["legacy_rowid"]] = "invalid stance"
                    else:
                        grouped.setdefault((str(hypothesis_id), str(source_id)), []).append(original)
                for key, rows in grouped.items():
                    if len(rows) > 1:
                        for original in rows:
                            reasons[original["legacy_rowid"]] = "duplicate or conflicting stance"
                for original in legacy_rows:
                    hypothesis_id = original.get("hypothesis_id")
                    source_id = original.get("source_id")
                    reason = reasons.get(original["legacy_rowid"])
                    if reason is None:
                        connection.execute(
                            "INSERT INTO hypothesis_sources (hypothesis_id, source_id, stance, note, evidence_json) VALUES (?, ?, ?, ?, '{}')",
                            (hypothesis_id, source_id, original["stance"], str(original.get("note") or "")),
                        )
                        continue
                    if hypothesis_id:
                        affected.add(str(hypothesis_id))
                    original_json = canonical_json(original)
                    connection.execute(
                        "INSERT INTO legacy_evidence_quarantine (hypothesis_id, source_id, legacy_stance, legacy_note, reason, original_row_json, original_sha256, quarantined_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            hypothesis_id,
                            source_id,
                            original.get("stance"),
                            original.get("note"),
                            reason,
                            original_json,
                            hashlib.sha256(original_json.encode("utf-8")).hexdigest(),
                            _timestamp(None),
                        ),
                    )
                for hypothesis_id in affected:
                    connection.execute(
                        "UPDATE hypotheses SET approval_blocked_reason = COALESCE(approval_blocked_reason, ?) WHERE id = ?",
                        ("legacy evidence quarantined during schema migration", hypothesis_id),
                    )

        connection.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS immutable_sources_update
            BEFORE UPDATE ON sources
            BEGIN
              SELECT RAISE(ABORT, 'source facts are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS immutable_sources_delete
            BEFORE DELETE ON sources
            BEGIN
              SELECT RAISE(ABORT, 'source facts are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS immutable_source_assessments_update
            BEFORE UPDATE ON source_assessments
            BEGIN
              SELECT RAISE(ABORT, 'source assessments are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS immutable_source_assessments_delete
            BEFORE DELETE ON source_assessments
            BEGIN
              SELECT RAISE(ABORT, 'source assessments are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS immutable_oos_consumptions_update
            BEFORE UPDATE ON oos_partition_consumptions
            BEGIN
              SELECT RAISE(ABORT, 'OOS consumptions are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS immutable_oos_consumptions_delete
            BEFORE DELETE ON oos_partition_consumptions
            BEGIN
              SELECT RAISE(ABORT, 'OOS consumptions are append-only');
            END;
            """
        )

    @staticmethod
    def _reconcile_legacy_state(connection: sqlite3.Connection) -> None:
        connection.execute(
            "UPDATE cycles SET stage = CASE WHEN status = 'INCOMPLETE' THEN 'INTERRUPTED' WHEN status = 'NEEDS_REVIEW' THEN 'REVIEW' WHEN status IN ('COMPLETED', 'FAILED') THEN 'DONE' ELSE stage END WHERE status != 'RUNNING'"
        )
        for row in connection.execute(
            """
            SELECT c.id, e.snapshot_path, e.start_at, e.end_at, e.policy_sha256
            FROM cycles c JOIN experiments e ON e.cycle_id = c.id
            WHERE c.dataset IS NULL ORDER BY e.created_at ASC
            """
        ).fetchall():
            dataset = Path(str(row["snapshot_path"])).name
            start = str(row["start_at"])[:10].replace("-", "")
            end = str(row["end_at"])[:10].replace("-", "")
            connection.execute(
                "UPDATE cycles SET dataset = ?, requested_timerange = ?, policy_sha256 = ? WHERE id = ?",
                (dataset, f"{start}-{end}", row["policy_sha256"], row["id"]),
            )
        rows = connection.execute(
            """
            SELECT h.id, h.cycle_id
            FROM hypotheses h
            JOIN cycles c ON c.id = h.cycle_id
            WHERE h.state = 'TESTING' AND c.status IN ('INCOMPLETE', 'FAILED')
            """
        ).fetchall()
        for row in rows:
            connection.execute(
                "UPDATE hypotheses SET state = 'INCONCLUSIVE', updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP) WHERE id = ?",
                (row["id"],),
            )
            connection.execute(
                """
                INSERT INTO state_events
                    (entity_type, entity_id, from_state, to_state, actor, reason, cycle_id, run_id, payload_json, created_at)
                SELECT 'hypothesis', ?, 'TESTING', 'INCONCLUSIVE', 'migration',
                       'reconcile terminal cycle', ?, NULL, '{}',
                       COALESCE(updated_at, CURRENT_TIMESTAMP)
                FROM hypotheses WHERE id = ?
                """,
                (row["id"], row["cycle_id"], row["id"]),
            )
        for cycle in connection.execute("SELECT id, created_at, updated_at FROM cycles").fetchall():
            floor = max(_as_datetime(cycle["created_at"]), _as_datetime(cycle["updated_at"]))
            for event in connection.execute(
                "SELECT id, created_at FROM state_events WHERE cycle_id = ? ORDER BY id ASC",
                (cycle["id"],),
            ).fetchall():
                timestamp = _as_datetime(event["created_at"])
                if timestamp < floor:
                    value = _timestamp(floor)
                    connection.execute("UPDATE state_events SET created_at = ? WHERE id = ?", (value, event["id"]))
                    timestamp = floor
                floor = max(floor, timestamp)
            connection.execute("UPDATE cycles SET updated_at = ? WHERE id = ?", (_timestamp(floor), cycle["id"]))

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def start_or_resume_cycle(self, now: datetime | str | dict[str, Any] | None = None) -> dict[str, Any]:
        identity: dict[str, Any] = {}
        if isinstance(now, dict):
            identity = {
                key: now.get(key)
                for key in (
                    "dataset",
                    "requested_timerange",
                    "policy_sha256",
                    "search_cohort",
                    "holdout_start",
                    "holdout_end",
                )
                if now.get(key) not in (None, "")
            }
            now = now.get("now")
        current = _timestamp(now)
        lease_until = _timestamp(_as_datetime(current) + timedelta(seconds=self.lease_seconds))
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM cycles WHERE status IN ('RUNNING', 'INTERRUPTED', 'INCOMPLETE') ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if row is not None and row["status"] == CycleStatus.RUNNING:
                self._assert_cycle_identity(row, identity)
                self._merge_cycle_identity(connection, row, identity)
                active_lease = row["lease_until"] and _as_datetime(row["lease_until"]) > _as_datetime(current)
                if active_lease:
                    return {"cycle": dict(row), "acquired": False}
                self._append_event(
                    connection,
                    entity_type="cycle",
                    entity_id=row["id"],
                    from_state=row["status"],
                    to_state=CycleStatus.INTERRUPTED,
                    actor="runtime",
                    reason="lease expired",
                    cycle_id=row["id"],
                    created_at=current,
                )
                connection.execute(
                    "UPDATE cycles SET status = ?, lease_until = NULL, updated_at = ? WHERE id = ?",
                    (CycleStatus.INTERRUPTED, current, row["id"]),
                )
                row = connection.execute("SELECT * FROM cycles WHERE id = ?", (row["id"],)).fetchone()
            if row is not None and row["status"] in {CycleStatus.INTERRUPTED, CycleStatus.INCOMPLETE}:
                self._assert_cycle_identity(row, identity)
                self._merge_cycle_identity(connection, row, identity)
                self._append_event(
                    connection,
                    entity_type="cycle",
                    entity_id=row["id"],
                    from_state=row["status"],
                    to_state=CycleStatus.RUNNING,
                    actor="runtime",
                    reason="resume after interruption",
                    cycle_id=row["id"],
                    created_at=current,
                )
                connection.execute(
                    "UPDATE cycles SET status = ?, stage = 'COLLECTING', lease_until = ?, updated_at = ? WHERE id = ?",
                    (CycleStatus.RUNNING, lease_until, current, row["id"]),
                )
                updated = connection.execute("SELECT * FROM cycles WHERE id = ?", (row["id"],)).fetchone()
                return {"cycle": dict(updated), "acquired": True}

            cycle_id = f"C-{current.replace(':', '').replace('-', '')}-{uuid.uuid4().hex[:8]}"
            connection.execute(
                "INSERT INTO cycles (id, status, stage, source_count, hypothesis_count, candidate_count, lease_until, created_at, updated_at, dataset, requested_timerange, policy_sha256, search_cohort, holdout_start, holdout_end) VALUES (?, ?, ?, 0, 0, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    cycle_id,
                    CycleStatus.RUNNING,
                    "COLLECTING",
                    lease_until,
                    current,
                    current,
                    identity.get("dataset"),
                    identity.get("requested_timerange"),
                    identity.get("policy_sha256"),
                    identity.get("search_cohort"),
                    identity.get("holdout_start"),
                    identity.get("holdout_end"),
                ),
            )
            self._append_event(
                connection,
                entity_type="cycle",
                entity_id=cycle_id,
                from_state=None,
                to_state=CycleStatus.RUNNING,
                actor="runtime",
                reason="start cycle",
                cycle_id=cycle_id,
                created_at=current,
            )
            created = connection.execute("SELECT * FROM cycles WHERE id = ?", (cycle_id,)).fetchone()
            return {"cycle": dict(created), "acquired": True}

    @staticmethod
    def _assert_cycle_identity(row: sqlite3.Row, identity: dict[str, Any]) -> None:
        for key, value in identity.items():
            existing = row[key]
            if existing not in (None, "") and str(existing) != str(value):
                raise ValueError(f"cycle identity mismatch: {key}")

    @staticmethod
    def _merge_cycle_identity(
        connection: sqlite3.Connection, row: sqlite3.Row, identity: dict[str, Any]
    ) -> None:
        missing = {key: value for key, value in identity.items() if row[key] in (None, "")}
        if not missing:
            return
        assignments = ", ".join(f"{key} = ?" for key in missing)
        connection.execute(
            f"UPDATE cycles SET {assignments} WHERE id = ?",
            (*missing.values(), row["id"]),
        )

    def release_cycle_lease(self, cycle_id: str, now: datetime | str | None = None) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE cycles SET lease_until = NULL, updated_at = ? WHERE id = ?",
                (_timestamp(now), cycle_id),
            )

    def ensure_cycle(
        self,
        cycle_id: str,
        *,
        stage: str = "IMPORTED",
        status: CycleStatus | str = CycleStatus.COMPLETED,
        now: datetime | str | None = None,
    ) -> dict[str, Any]:
        timestamp = _timestamp(now)
        target = CycleStatus(status)
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO cycles (id, status, stage, source_count, hypothesis_count, candidate_count, lease_until, created_at, updated_at) VALUES (?, ?, ?, 0, 0, 0, NULL, ?, ?)",
                (cycle_id, target, stage, timestamp, timestamp),
            )
            if connection.execute(
                "SELECT COUNT(*) FROM state_events WHERE entity_type = 'cycle' AND entity_id = ?", (cycle_id,)
            ).fetchone()[0] == 0:
                self._append_event(
                    connection,
                    entity_type="cycle",
                    entity_id=cycle_id,
                    from_state=None,
                    to_state=target,
                    actor="migration",
                    reason="legacy import cycle",
                    cycle_id=cycle_id,
                    created_at=timestamp,
                )
            return dict(connection.execute("SELECT * FROM cycles WHERE id = ?", (cycle_id,)).fetchone())

    def integrity_report(self) -> dict[str, Any]:
        with self.connect() as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_key_errors = [
                tuple(row) for row in connection.execute("PRAGMA foreign_key_check")
            ]
            return {"integrity_check": integrity, "foreign_key_errors": foreign_key_errors}

    def insert_source(self, cycle_id: str, source: dict[str, Any] | Any) -> dict[str, Any]:
        data = source if isinstance(source, dict) else vars(source)
        doi = _normalize_doi(data.get("doi"))
        canonical_url = data.get("canonical_url") or None
        fingerprint = str(data.get("fingerprint") or "")
        if not fingerprint:
            fingerprint = hashlib.sha256(
                canonical_json(
                    [data.get("provider"), doi, canonical_url, data.get("title"), data.get("excerpt")]
                ).encode()
            ).hexdigest()
        retrieved_at = _timestamp(data.get("retrieved_at"))
        metadata_json = _json_text(data.get("metadata", {}), "metadata")
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cycle = connection.execute("SELECT * FROM cycles WHERE id = ?", (cycle_id,)).fetchone()
            if cycle is None:
                raise ValueError(f"unknown cycle: {cycle_id}")
            existing = connection.execute(
                "SELECT * FROM sources WHERE fingerprint = ? OR (? IS NOT NULL AND doi = ?) OR (? IS NOT NULL AND canonical_url = ?) LIMIT 1",
                (fingerprint, doi, doi, canonical_url, canonical_url),
            ).fetchone()
            if existing is not None:
                membership = connection.execute(
                    "SELECT 1 FROM cycle_sources WHERE cycle_id = ? AND source_id = ?",
                    (cycle_id, existing["id"]),
                ).fetchone()
                if membership is None:
                    if cycle["source_count"] >= SOURCE_BUDGET:
                        raise ValueError("source budget exhausted")
                    connection.execute(
                        "INSERT INTO cycle_sources (cycle_id, source_id, observed_at) VALUES (?, ?, ?)",
                        (cycle_id, existing["id"], retrieved_at),
                    )
                    connection.execute(
                        "UPDATE cycles SET source_count = source_count + 1, updated_at = ? WHERE id = ?",
                        (retrieved_at, cycle_id),
                    )
                return {"id": existing["id"], "inserted": False, "duplicate_of": existing["id"]}
            if cycle["source_count"] >= SOURCE_BUDGET:
                raise ValueError("source budget exhausted")
            source_id = f"S-{fingerprint[:24]}"
            try:
                connection.execute(
                    "INSERT INTO sources (id, cycle_id, provider, canonical_url, doi, title, excerpt, license, retrieved_at, fingerprint, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        source_id,
                        cycle_id,
                        str(data.get("provider") or ""),
                        canonical_url,
                        doi,
                        str(data.get("title") or ""),
                        str(data.get("excerpt") or ""),
                        data.get("license"),
                        retrieved_at,
                        fingerprint,
                        metadata_json,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                existing = connection.execute(
                    "SELECT * FROM sources WHERE fingerprint = ? OR (? IS NOT NULL AND doi = ?) OR (? IS NOT NULL AND canonical_url = ?) LIMIT 1",
                    (fingerprint, doi, doi, canonical_url, canonical_url),
                ).fetchone()
                if existing is not None:
                    membership = connection.execute(
                        "SELECT 1 FROM cycle_sources WHERE cycle_id = ? AND source_id = ?",
                        (cycle_id, existing["id"]),
                    ).fetchone()
                    if membership is None:
                        connection.execute(
                            "INSERT INTO cycle_sources (cycle_id, source_id, observed_at) VALUES (?, ?, ?)",
                            (cycle_id, existing["id"], retrieved_at),
                        )
                        connection.execute(
                            "UPDATE cycles SET source_count = source_count + 1, updated_at = ? WHERE id = ?",
                            (retrieved_at, cycle_id),
                        )
                    return {"id": existing["id"], "inserted": False, "duplicate_of": existing["id"]}
                raise ValueError("source violates uniqueness constraints") from exc
            connection.execute(
                "INSERT INTO cycle_sources (cycle_id, source_id, observed_at) VALUES (?, ?, ?)",
                (cycle_id, source_id, retrieved_at),
            )
            connection.execute(
                "UPDATE cycles SET source_count = source_count + 1, updated_at = ? WHERE id = ?",
                (retrieved_at, cycle_id),
            )
            return {"id": source_id, "inserted": True, "duplicate_of": None}

    def insert_source_assessment(
        self,
        cycle_id: str,
        source_id: str,
        assessment: dict[str, Any],
        *,
        actor: str,
        created_at: datetime | str | None = None,
    ) -> int:
        if not actor or not actor.strip():
            raise ValueError("actor is required")
        if not isinstance(assessment, dict):
            raise ValueError("assessment must be an object")
        assessment_json = _json_text(assessment, "assessment")
        timestamp = _timestamp(created_at)
        with self.connect() as connection:
            membership = connection.execute(
                "SELECT 1 FROM cycle_sources WHERE cycle_id = ? AND source_id = ?",
                (cycle_id, source_id),
            ).fetchone()
            if membership is None:
                raise ValueError("source is not observed by cycle")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(cycles)")}
            if "ranking_sealed_at" in columns and connection.execute(
                "SELECT ranking_sealed_at FROM cycles WHERE id = ?", (cycle_id,)
            ).fetchone()[0] is not None:
                raise ValueError("source assessment is blocked after ranking seal")
            cursor = connection.execute(
                """
                INSERT INTO source_assessments
                    (cycle_id, source_id, relevance, asset, timeframe, mechanism, assessment_json, actor, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cycle_id,
                    source_id,
                    assessment.get("relevance"),
                    assessment.get("asset"),
                    assessment.get("timeframe"),
                    assessment.get("mechanism"),
                    assessment_json,
                    actor.strip(),
                    timestamp,
                ),
            )
            return int(cursor.lastrowid)

    def insert_hypothesis(
        self,
        cycle_id: str,
        hypothesis: dict[str, Any],
        source_links: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        scores = hypothesis.get("scores", hypothesis)
        total_score = score_hypothesis(
            scores.get("evidence_quality"),
            scores.get("reproducibility"),
            scores.get("ohlcv_transferability"),
            scores.get("novelty"),
            scores.get("falsifiability"),
        )
        required_data = hypothesis.get("required_data", ["OHLCV"])
        if not isinstance(required_data, list) or not required_data:
            raise ValueError("required_data must be a non-empty list")
        now = (
            _timestamp(hypothesis["created_at"])
            if hypothesis.get("created_at") is not None
            else _utc_now().isoformat(timespec="microseconds").replace("+00:00", "Z")
        )
        state = HypothesisState(hypothesis.get("state", HypothesisState.SCORED))
        hypothesis_id = str(hypothesis.get("id") or f"H-{uuid.uuid4().hex[:12]}")
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT * FROM hypotheses WHERE id = ?", (hypothesis_id,)).fetchone()
            if existing is not None:
                return dict(existing)
            cycle = connection.execute("SELECT * FROM cycles WHERE id = ?", (cycle_id,)).fetchone()
            if cycle is None:
                raise ValueError(f"unknown cycle: {cycle_id}")
            if cycle["hypothesis_count"] >= HYPOTHESIS_BUDGET:
                raise ValueError("hypothesis budget exhausted")
            connection.execute(
                """
                INSERT INTO hypotheses (
                    id, cycle_id, thesis, mechanism, market_scope, required_data_json, falsifier,
                    evidence_quality, reproducibility, ohlcv_transferability, novelty, falsifiability,
                    total_score, state, candidate_path, candidate_sha256, metadata_json, created_at,
                    updated_at, family_id, plan_json, plan_sha256, approval_blocked_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hypothesis_id,
                    cycle_id,
                    str(hypothesis.get("thesis") or ""),
                    str(hypothesis.get("mechanism") or ""),
                    str(hypothesis.get("market_scope") or ""),
                    _json_text(required_data, "required_data"),
                    str(hypothesis.get("falsifier") or ""),
                    scores["evidence_quality"],
                    scores["reproducibility"],
                    scores["ohlcv_transferability"],
                    scores["novelty"],
                    scores["falsifiability"],
                    total_score,
                    state,
                    _json_text(hypothesis.get("metadata", {}), "metadata"),
                    now,
                    now,
                    hypothesis.get("family_id"),
                    hypothesis.get("plan_json"),
                    hypothesis.get("plan_sha256"),
                    hypothesis.get("approval_blocked_reason"),
                ),
            )
            connection.execute(
                "UPDATE cycles SET hypothesis_count = hypothesis_count + 1, updated_at = ? WHERE id = ?",
                (now, cycle_id),
            )
            for link in source_links or []:
                source_id = link["source_id"]
                stance = link["stance"]
                note = str(link.get("note") or "").strip()
                if stance not in {"SUPPORT", "CONTRADICT"} or not note:
                    raise ValueError("invalid hypothesis source link")
                if connection.execute(
                    "SELECT 1 FROM cycle_sources WHERE cycle_id = ? AND source_id = ?",
                    (cycle_id, source_id),
                ).fetchone() is None:
                    raise ValueError(f"source provenance missing: {source_id}")
                connection.execute(
                    "INSERT INTO hypothesis_sources (hypothesis_id, source_id, stance, note, evidence_json) VALUES (?, ?, ?, ?, ?)",
                    (
                        hypothesis_id,
                        source_id,
                        stance,
                        note,
                        _json_text(link.get("evidence", {}), "evidence"),
                    ),
                )
            return dict(connection.execute("SELECT * FROM hypotheses WHERE id = ?", (hypothesis_id,)).fetchone())

    def add_hypothesis_source(
        self,
        hypothesis_id: str,
        source_id: str,
        stance: str,
        note: str,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        if stance not in {"SUPPORT", "CONTRADICT"}:
            raise ValueError("invalid source stance")
        if not note.strip():
            raise ValueError("source note is required")
        with self.connect() as connection:
            hypothesis = connection.execute(
                "SELECT cycle_id FROM hypotheses WHERE id = ?", (hypothesis_id,)
            ).fetchone()
            if hypothesis is None:
                raise ValueError(f"unknown hypothesis: {hypothesis_id}")
            if connection.execute(
                "SELECT 1 FROM cycle_sources WHERE cycle_id = ? AND source_id = ?",
                (hypothesis["cycle_id"], source_id),
            ).fetchone() is None:
                raise ValueError(f"source provenance missing: {source_id}")
            existing = connection.execute(
                "SELECT stance FROM hypothesis_sources WHERE hypothesis_id = ? AND source_id = ?",
                (hypothesis_id, source_id),
            ).fetchone()
            if existing is not None:
                if existing["stance"] != stance:
                    raise ValueError("source stance overlap")
                return
            connection.execute(
                "INSERT INTO hypothesis_sources (hypothesis_id, source_id, stance, note, evidence_json) VALUES (?, ?, ?, ?, ?)",
                (hypothesis_id, source_id, stance, note.strip(), _json_text(evidence or {}, "evidence")),
            )

    def list_hypothesis_sources(self, hypothesis_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT s.*, hs.stance, hs.note, hs.evidence_json
                FROM hypothesis_sources hs
                JOIN sources s ON s.id = hs.source_id
                WHERE hs.hypothesis_id = ?
                ORDER BY s.retrieved_at ASC, s.id ASC
                """,
                (hypothesis_id,),
            )
            return [dict(row) for row in rows]

    def set_candidate(
        self,
        hypothesis_id: str,
        candidate_path: str | Path,
        candidate_sha256: str,
    ) -> dict[str, Any]:
        path = str(candidate_path)
        if not path or not candidate_sha256:
            raise ValueError("candidate identity is required")
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            hypothesis = connection.execute(
                "SELECT * FROM hypotheses WHERE id = ?", (hypothesis_id,)
            ).fetchone()
            if hypothesis is None:
                raise ValueError(f"unknown hypothesis: {hypothesis_id}")
            if hypothesis["candidate_path"] is not None:
                if (
                    hypothesis["candidate_path"] == path
                    and hypothesis["candidate_sha256"] == candidate_sha256
                ):
                    return dict(hypothesis)
                raise ValueError("candidate identity already exists")
            cycle = connection.execute(
                "SELECT * FROM cycles WHERE id = ?", (hypothesis["cycle_id"],)
            ).fetchone()
            if cycle["candidate_count"] >= CANDIDATE_BUDGET:
                raise ValueError("candidate budget exhausted")
            now = _timestamp(None)
            connection.execute(
                "UPDATE hypotheses SET candidate_path = ?, candidate_sha256 = ?, updated_at = ? WHERE id = ?",
                (path, candidate_sha256, now, hypothesis_id),
            )
            connection.execute(
                "UPDATE cycles SET candidate_count = candidate_count + 1, updated_at = ? WHERE id = ?",
                (now, hypothesis["cycle_id"]),
            )
            return dict(connection.execute("SELECT * FROM hypotheses WHERE id = ?", (hypothesis_id,)).fetchone())

    def insert_experiment(self, experiment: dict[str, Any]) -> dict[str, Any]:
        now = _timestamp(experiment.get("created_at"))
        experiment_id = str(experiment.get("id") or f"EXP-{uuid.uuid4().hex[:12]}")
        required = (
            "cycle_id", "hypothesis_id", "parent_strategy", "parent_sha256", "changed_variable",
            "config_path", "config_sha256", "pairs", "timeframes", "timeframe_detail",
            "snapshot_path", "snapshot_sha256", "policy_path", "policy_sha256", "strategy_name",
            "strategy_path", "start_at", "end_at", "status",
        )
        missing = [key for key in required if key not in experiment]
        if missing:
            raise ValueError(f"missing experiment fields: {', '.join(missing)}")
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO experiments (id, cycle_id, hypothesis_id, parent_strategy, parent_sha256, changed_variable, config_path, config_sha256, pairs_json, timeframes_json, timeframe_detail, snapshot_path, snapshot_sha256, policy_path, policy_sha256, strategy_name, strategy_path, start_at, end_at, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    experiment_id, experiment["cycle_id"], experiment["hypothesis_id"], experiment["parent_strategy"],
                    experiment["parent_sha256"], experiment["changed_variable"], experiment["config_path"],
                    experiment["config_sha256"], _json_text(experiment["pairs"], "pairs"),
                    _json_text(experiment["timeframes"], "timeframes"), experiment["timeframe_detail"],
                    experiment["snapshot_path"], experiment["snapshot_sha256"], experiment["policy_path"],
                    experiment["policy_sha256"], experiment["strategy_name"], experiment["strategy_path"],
                    _timestamp(experiment["start_at"]), _timestamp(experiment["end_at"]), experiment["status"], now,
                ),
            )
            return dict(connection.execute("SELECT * FROM experiments WHERE id = ?", (experiment_id,)).fetchone())

    def record_run(self, run: dict[str, Any]) -> dict[str, Any]:
        now = _timestamp(run.get("created_at"))
        run_id = str(run.get("id") or f"RUN-{uuid.uuid4().hex[:12]}")
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO runs (id, experiment_id, kind, status, verdict, metrics_json, artifact_manifest_json, error_code, created_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id, run["experiment_id"], run["kind"], run["status"], run.get("verdict"),
                    _json_text(run.get("metrics", {}), "metrics"),
                    _json_text(run.get("artifact_manifest", {}), "artifact_manifest"),
                    run.get("error_code"), now, _timestamp(run["completed_at"]) if run.get("completed_at") else None,
                ),
            )
            return dict(connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone())

    def get_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            return _row(connection.execute("SELECT * FROM experiments WHERE id = ?", (experiment_id,)).fetchone())

    def find_experiment(self, cycle_id: str, hypothesis_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            return _row(
                connection.execute(
                    "SELECT * FROM experiments WHERE cycle_id = ? AND hypothesis_id = ? ORDER BY created_at ASC LIMIT 1",
                    (cycle_id, hypothesis_id),
                ).fetchone()
            )

    def list_runs(self, experiment_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM runs WHERE experiment_id = ? ORDER BY created_at ASC, id ASC",
                    (experiment_id,),
                )
            ]

    def transition_hypothesis(
        self,
        hypothesis_id: str,
        target: HypothesisState | str,
        actor: str,
        reason: str,
        cycle_id: str | None = None,
        run_id: str | None = None,
        payload: dict[str, Any] | None = None,
        now: datetime | str | None = None,
    ) -> dict[str, Any]:
        if not actor or not actor.strip():
            raise ValueError("actor is required")
        if not reason or not reason.strip():
            raise ValueError("reason is required")
        target_state = HypothesisState(target)
        timestamp = _timestamp(now)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            hypothesis = connection.execute("SELECT * FROM hypotheses WHERE id = ?", (hypothesis_id,)).fetchone()
            if hypothesis is None:
                raise ValueError(f"unknown hypothesis: {hypothesis_id}")
            if cycle_id is not None and cycle_id != hypothesis["cycle_id"]:
                raise ValueError("cycle does not own hypothesis")
            current = HypothesisState(hypothesis["state"])
            if not next_state_allowed(current, target_state):
                raise ValueError(f"illegal transition: {current} -> {target_state}")
            if current == HypothesisState.NEEDS_REVIEW and actor != "local_user":
                raise ValueError("review transitions require actor local_user")
            cycle = connection.execute(
                "SELECT updated_at FROM cycles WHERE id = ?", (hypothesis["cycle_id"],)
            ).fetchone()
            timestamp = self._monotonic_timestamp(timestamp, cycle["updated_at"] if cycle else None)
            self._append_event(
                connection,
                entity_type="hypothesis",
                entity_id=hypothesis_id,
                from_state=current,
                to_state=target_state,
                actor=actor.strip(),
                reason=reason.strip(),
                cycle_id=hypothesis["cycle_id"],
                run_id=run_id,
                payload=payload or {},
                created_at=timestamp,
            )
            connection.execute(
                "UPDATE hypotheses SET state = ?, updated_at = ? WHERE id = ?",
                (target_state, timestamp, hypothesis_id),
            )
            connection.execute(
                "UPDATE cycles SET updated_at = ? WHERE id = ?",
                (timestamp, hypothesis["cycle_id"]),
            )
            return dict(connection.execute("SELECT * FROM hypotheses WHERE id = ?", (hypothesis_id,)).fetchone())

    def get_cycle(self, cycle_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            return _row(connection.execute("SELECT * FROM cycles WHERE id = ?", (cycle_id,)).fetchone())

    def get_hypothesis(self, hypothesis_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            return _row(connection.execute("SELECT * FROM hypotheses WHERE id = ?", (hypothesis_id,)).fetchone())

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            return _row(connection.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone())

    def get_source_assessment(self, cycle_id: str, source_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT assessment_json FROM source_assessments WHERE cycle_id = ? AND source_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                (cycle_id, source_id),
            ).fetchone()
            if row is None:
                return None
            try:
                value = json.loads(row["assessment_json"])
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid stored source assessment: {source_id}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"invalid stored source assessment: {source_id}")
            return value

    def list_source_views(
        self, cycle_id: str, *, limit: int = 25, after: str | None = None
    ) -> dict[str, Any]:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        cursor_values: tuple[str, str] | None = None
        if after:
            try:
                decoded = base64.urlsafe_b64decode(str(after).encode("ascii") + b"===").decode("utf-8")
                parsed = json.loads(decoded)
                if not isinstance(parsed, list) or len(parsed) != 2:
                    raise ValueError
                cursor_values = (str(parsed[0]), str(parsed[1]))
            except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError, base64.binascii.Error) as exc:
                raise ValueError("invalid source view cursor") from exc
        with self.connect() as connection:
            cycle = connection.execute("SELECT id FROM cycles WHERE id = ?", (cycle_id,)).fetchone()
            if cycle is None:
                raise ValueError(f"unknown cycle: {cycle_id}")
            query = """
                SELECT s.*, cs.observed_at AS cycle_observed_at
                FROM cycle_sources cs
                JOIN sources s ON s.id = cs.source_id
                WHERE cs.cycle_id = ?
            """
            args: list[Any] = [cycle_id]
            if cursor_values is not None:
                query += " AND (cs.observed_at > ? OR (cs.observed_at = ? AND s.id > ?))"
                args.extend([cursor_values[0], cursor_values[0], cursor_values[1]])
            query += " ORDER BY cs.observed_at ASC, s.id ASC LIMIT ?"
            args.append(limit)
            rows = connection.execute(query, args).fetchall()
            views: list[dict[str, Any]] = []
            for row in rows:
                try:
                    metadata = json.loads(row["metadata_json"])
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid stored source metadata: {row['id']}") from exc
                if not isinstance(metadata, dict):
                    raise ValueError(f"invalid stored source metadata: {row['id']}")
                assessment_rows = connection.execute(
                    "SELECT assessment_json FROM source_assessments WHERE cycle_id = ? AND source_id = ? ORDER BY created_at DESC, id DESC",
                    (cycle_id, row["id"]),
                ).fetchall()
                assessment = None
                if assessment_rows:
                    try:
                        assessment = json.loads(assessment_rows[0]["assessment_json"])
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"invalid stored source assessment: {row['id']}") from exc
                views.append(
                    {
                        "source_id": row["id"],
                        "id": row["id"],
                        "provider": row["provider"],
                        "title": row["title"],
                        "excerpt": row["excerpt"][:4000],
                        "canonical_url": row["canonical_url"],
                        "doi": row["doi"],
                        "retrieved_at": row["retrieved_at"],
                        "cycle_observed_at": row["cycle_observed_at"],
                        "collector_metadata": metadata,
                        "collector_metadata_sha256": hashlib.sha256(
                            row["metadata_json"].encode("utf-8")
                        ).hexdigest(),
                        "assessment": assessment,
                        "assessment_count": len(assessment_rows),
                    }
                )
            next_cursor = None
            if len(rows) == limit and rows:
                last = rows[-1]
                encoded = json.dumps(
                    [last["cycle_observed_at"], last["id"]], separators=(",", ":")
                ).encode("utf-8")
                next_cursor = base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")
            return {"sources": views, "next_cursor": next_cursor}

    def update_source_metadata(self, source_id: str, patch: dict[str, Any]) -> None:
        raise ValueError("source metadata is immutable; use source assessment")

    def find_hypothesis_by_mechanism(self, cycle_id: str, mechanism: str) -> dict[str, Any] | None:
        normalized = " ".join(mechanism.casefold().split())
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM hypotheses WHERE cycle_id = ? ORDER BY created_at ASC, id ASC", (cycle_id,)
            )
            for row in rows:
                if " ".join(row["mechanism"].casefold().split()) == normalized:
                    return dict(row)
        return None

    def append_cycle_event(
        self,
        cycle_id: str,
        *,
        to_state: CycleStatus | str,
        actor: str,
        reason: str,
        payload: dict[str, Any] | None = None,
        now: datetime | str | None = None,
    ) -> int:
        if not actor or not actor.strip():
            raise ValueError("actor is required")
        if not reason or not reason.strip():
            raise ValueError("reason is required")
        timestamp = _timestamp(now)
        with self.connect() as connection:
            cycle = connection.execute("SELECT status, updated_at FROM cycles WHERE id = ?", (cycle_id,)).fetchone()
            if cycle is None:
                raise ValueError(f"unknown cycle: {cycle_id}")
            try:
                target = CycleStatus(to_state)
            except ValueError as exc:
                raise ValueError("cycle audit event must use a valid cycle status") from exc
            if target != CycleStatus(cycle["status"]):
                raise ValueError("cycle audit event cannot change cycle status")
            timestamp = self._monotonic_timestamp(timestamp, cycle["updated_at"])
            self._append_event(
                connection,
                entity_type="cycle",
                entity_id=cycle_id,
                from_state=cycle["status"],
                to_state=target,
                actor=actor.strip(),
                reason=reason.strip(),
                cycle_id=cycle_id,
                payload=payload or {},
                created_at=timestamp,
            )
            connection.execute("UPDATE cycles SET updated_at = ? WHERE id = ?", (timestamp, cycle_id))
            return int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])

    def set_cycle_status(
        self, cycle_id: str, status: CycleStatus | str, reason: str, now: datetime | str | None = None
    ) -> dict[str, Any]:
        target = CycleStatus(status)
        timestamp = _timestamp(now)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cycle = connection.execute("SELECT * FROM cycles WHERE id = ?", (cycle_id,)).fetchone()
            if cycle is None:
                raise ValueError(f"unknown cycle: {cycle_id}")
            if not reason or not reason.strip():
                raise ValueError("reason is required")
            current = CycleStatus(cycle["status"])
            if current == target:
                return dict(cycle)
            if not next_cycle_state_allowed(current, target):
                raise ValueError(f"illegal cycle transition: {current} -> {target}")
            timestamp = self._monotonic_timestamp(timestamp, cycle["updated_at"])
            self._append_event(
                connection,
                entity_type="cycle",
                entity_id=cycle_id,
                from_state=cycle["status"],
                to_state=target,
                actor="runtime",
                reason=reason.strip(),
                cycle_id=cycle_id,
                created_at=timestamp,
            )
            connection.execute(
                "UPDATE cycles SET status = ?, stage = ?, lease_until = NULL, updated_at = ? WHERE id = ?",
                (target, self._stage_for_status(target, cycle["stage"]), timestamp, cycle_id),
            )
            return dict(connection.execute("SELECT * FROM cycles WHERE id = ?", (cycle_id,)).fetchone())

    def list_hypotheses(self, cycle_id: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as connection:
            query = "SELECT * FROM hypotheses"
            args: tuple[Any, ...] = ()
            if cycle_id:
                query += " WHERE cycle_id = ?"
                args = (cycle_id,)
            query += " ORDER BY total_score DESC, created_at ASC, id ASC"
            return [dict(row) for row in connection.execute(query, args)]

    def list_cycles(self, limit: int = 100) -> list[dict[str, Any]]:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        with self.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM cycles ORDER BY updated_at DESC, id DESC LIMIT ?", (limit,)
                )
            ]

    def record_validation_window(
        self,
        *,
        cycle_id: str,
        dataset: str | None,
        requested_timerange: str | None,
        policy_sha256: str | None,
        verdict: str,
        created_at: datetime | str | None = None,
    ) -> None:
        if not all((dataset, requested_timerange, policy_sha256)):
            return
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO validation_windows (cycle_id, dataset, requested_timerange, policy_sha256, verdict, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (cycle_id, dataset, requested_timerange, policy_sha256, verdict, _timestamp(created_at)),
            )

    def window_is_contaminated(
        self, *, dataset: str | None, requested_timerange: str | None, policy_sha256: str | None
    ) -> bool:
        if not all((dataset, requested_timerange, policy_sha256)):
            return False
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM validation_windows WHERE dataset = ? AND requested_timerange = ? AND policy_sha256 = ? AND verdict = 'PASS' LIMIT 1",
                (dataset, requested_timerange, policy_sha256),
            ).fetchone()
            if row is not None:
                return True
            if connection.execute(
                """
                SELECT 1
                FROM experiments e
                JOIN runs r ON r.experiment_id = e.id
                JOIN cycles c ON c.id = e.cycle_id
                WHERE c.dataset = ? AND c.requested_timerange = ?
                  AND c.policy_sha256 = ? AND r.verdict = 'PASS'
                LIMIT 1
                """,
                (dataset, requested_timerange, policy_sha256),
            ).fetchone() is not None:
                return True
            # Legacy rows without cycle identity remain conservative.
            return connection.execute(
                "SELECT 1 FROM experiments e JOIN runs r ON r.experiment_id = e.id WHERE e.policy_sha256 = ? AND r.verdict = 'PASS' LIMIT 1",
                (policy_sha256,),
            ).fetchone() is not None

    def events(self, cycle_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM state_events WHERE cycle_id = ? ORDER BY id DESC", (cycle_id,)
                )
            ]

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        *,
        entity_type: str,
        entity_id: str,
        from_state: HypothesisState | CycleStatus | str | None,
        to_state: HypothesisState | CycleStatus | str,
        actor: str,
        reason: str,
        cycle_id: str,
        run_id: str | None = None,
        payload: dict[str, Any] | None = None,
        created_at: str,
    ) -> None:
        connection.execute(
            "INSERT INTO state_events (entity_type, entity_id, from_state, to_state, actor, reason, cycle_id, run_id, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entity_type,
                entity_id,
                None if from_state is None else str(from_state),
                str(to_state),
                actor,
                reason,
                cycle_id,
                run_id,
                canonical_json(payload or {}),
                created_at,
            ),
        )

    @staticmethod
    def _monotonic_timestamp(value: str, floor: str | None) -> str:
        if floor is None or _as_datetime(value) >= _as_datetime(floor):
            return value
        return floor

    @staticmethod
    def _stage_for_status(status: CycleStatus, current: str) -> str:
        if status == CycleStatus.NEEDS_REVIEW:
            return "REVIEW"
        if status in {CycleStatus.COMPLETED, CycleStatus.FAILED}:
            return "DONE"
        if status == CycleStatus.INCOMPLETE:
            return "INTERRUPTED"
        return current
