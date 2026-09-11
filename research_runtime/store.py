from __future__ import annotations

import hashlib
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from .core import CycleStatus, HypothesisState, canonical_json, next_state_allowed, score_hypothesis


SCHEMA_VERSION = 1
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
  updated_at TEXT NOT NULL
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
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            elif version != SCHEMA_VERSION:
                raise RuntimeError(f"unsupported research schema version: {version}")

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
        if isinstance(now, dict):
            now = now.get("now")
        current = _timestamp(now)
        lease_until = _timestamp(_as_datetime(current) + timedelta(seconds=self.lease_seconds))
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM cycles WHERE status IN ('RUNNING', 'INTERRUPTED') ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if row is not None and row["status"] == CycleStatus.RUNNING:
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
            if row is not None and row["status"] == CycleStatus.INTERRUPTED:
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
                    "UPDATE cycles SET status = ?, lease_until = ?, updated_at = ? WHERE id = ?",
                    (CycleStatus.RUNNING, lease_until, current, row["id"]),
                )
                updated = connection.execute("SELECT * FROM cycles WHERE id = ?", (row["id"],)).fetchone()
                return {"cycle": dict(updated), "acquired": True}

            cycle_id = f"C-{current.replace(':', '').replace('-', '')}-{uuid.uuid4().hex[:8]}"
            connection.execute(
                "INSERT INTO cycles (id, status, stage, source_count, hypothesis_count, candidate_count, lease_until, created_at, updated_at) VALUES (?, ?, ?, 0, 0, 0, ?, ?, ?)",
                (cycle_id, CycleStatus.RUNNING, "COLLECTING", lease_until, current, current),
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

    def release_cycle_lease(self, cycle_id: str, now: datetime | str | None = None) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE cycles SET lease_until = NULL, updated_at = ? WHERE id = ?",
                (_timestamp(now), cycle_id),
            )

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
            existing = connection.execute(
                "SELECT * FROM sources WHERE fingerprint = ? OR (? IS NOT NULL AND doi = ?) OR (? IS NOT NULL AND canonical_url = ?) LIMIT 1",
                (fingerprint, doi, doi, canonical_url, canonical_url),
            ).fetchone()
            if existing is not None:
                return {"id": existing["id"], "inserted": False, "duplicate_of": existing["id"]}
            cycle = connection.execute("SELECT * FROM cycles WHERE id = ?", (cycle_id,)).fetchone()
            if cycle is None:
                raise ValueError(f"unknown cycle: {cycle_id}")
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
                    return {"id": existing["id"], "inserted": False, "duplicate_of": existing["id"]}
                raise ValueError("source violates uniqueness constraints") from exc
            connection.execute(
                "UPDATE cycles SET source_count = source_count + 1, updated_at = ? WHERE id = ?",
                (retrieved_at, cycle_id),
            )
            return {"id": source_id, "inserted": True, "duplicate_of": None}

    def insert_hypothesis(self, cycle_id: str, hypothesis: dict[str, Any]) -> dict[str, Any]:
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
        now = _timestamp(hypothesis.get("created_at"))
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
                "INSERT INTO hypotheses (id, cycle_id, thesis, mechanism, market_scope, required_data_json, falsifier, evidence_quality, reproducibility, ohlcv_transferability, novelty, falsifiability, total_score, state, candidate_path, candidate_sha256, metadata_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)",
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
                ),
            )
            connection.execute(
                "UPDATE cycles SET hypothesis_count = hypothesis_count + 1, updated_at = ? WHERE id = ?",
                (now, cycle_id),
            )
            return dict(connection.execute("SELECT * FROM hypotheses WHERE id = ?", (hypothesis_id,)).fetchone())

    def add_hypothesis_source(
        self, hypothesis_id: str, source_id: str, stance: str, note: str
    ) -> None:
        if stance not in {"SUPPORT", "CONTRADICT"}:
            raise ValueError("invalid source stance")
        if not note.strip():
            raise ValueError("source note is required")
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO hypothesis_sources (hypothesis_id, source_id, stance, note) VALUES (?, ?, ?, ?)",
                (hypothesis_id, source_id, stance, note.strip()),
            )

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
                "INSERT OR REPLACE INTO runs (id, experiment_id, kind, status, verdict, metrics_json, artifact_manifest_json, error_code, created_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id, run["experiment_id"], run["kind"], run["status"], run.get("verdict"),
                    _json_text(run.get("metrics", {}), "metrics"),
                    _json_text(run.get("artifact_manifest", {}), "artifact_manifest"),
                    run.get("error_code"), now, _timestamp(run["completed_at"]) if run.get("completed_at") else None,
                ),
            )
            return dict(connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone())

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

    def list_hypotheses(self, cycle_id: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as connection:
            query = "SELECT * FROM hypotheses"
            args: tuple[Any, ...] = ()
            if cycle_id:
                query += " WHERE cycle_id = ?"
                args = (cycle_id,)
            query += " ORDER BY total_score DESC, created_at ASC, id ASC"
            return [dict(row) for row in connection.execute(query, args)]

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
