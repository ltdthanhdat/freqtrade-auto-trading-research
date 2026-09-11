from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import sqlite3
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import quote, unquote
from typing import Any, Callable

from .core import HypothesisState
from .store import ResearchStore


REVIEW_TARGETS = {
    "approve": HypothesisState.APPROVED_FOR_DRY_RUN,
    "reject": HypothesisState.REJECTED,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decode(value: str, field: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid stored JSON: {field}") from exc


class DashboardReadModel:
    def __init__(self, db_path: str | Path, artifact_root: str | Path):
        self.db_path = Path(db_path).resolve()
        self.artifact_root = Path(artifact_root).resolve()

    def connect_readonly(self) -> sqlite3.Connection:
        uri = f"file:{quote(str(self.db_path), safe='/')}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        return connection

    def _current_cycle(self, connection: sqlite3.Connection) -> dict[str, Any] | None:
        row = connection.execute("SELECT * FROM cycles ORDER BY updated_at DESC, id DESC LIMIT 1").fetchone()
        return None if row is None else dict(row)

    def overview(self) -> dict[str, Any]:
        with self.connect_readonly() as connection:
            cycle = self._current_cycle(connection)
            if cycle is None:
                return {
                    "current_cycle": None,
                    "counts": {"sources": 0, "hypotheses": 0, "queued": 0, "testing": 0, "review": 0},
                    "events": [],
                }
            cycle_id = cycle["id"]
            counts = {
                "sources": connection.execute("SELECT COUNT(*) FROM sources WHERE cycle_id = ?", (cycle_id,)).fetchone()[0],
                "hypotheses": connection.execute("SELECT COUNT(*) FROM hypotheses WHERE cycle_id = ?", (cycle_id,)).fetchone()[0],
                "queued": connection.execute("SELECT COUNT(*) FROM hypotheses WHERE cycle_id = ? AND state = 'QUEUED'", (cycle_id,)).fetchone()[0],
                "testing": connection.execute("SELECT COUNT(*) FROM hypotheses WHERE cycle_id = ? AND state = 'TESTING'", (cycle_id,)).fetchone()[0],
                "review": connection.execute("SELECT COUNT(*) FROM hypotheses WHERE cycle_id = ? AND state = 'NEEDS_REVIEW'", (cycle_id,)).fetchone()[0],
            }
            events = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM state_events WHERE cycle_id = ? ORDER BY id DESC LIMIT 20", (cycle_id,)
                )
            ]
            for event in events:
                event["payload"] = _decode(event.pop("payload_json"), "state_events.payload_json")
            return {"current_cycle": cycle, "counts": counts, "events": events}

    def sources(self) -> list[dict[str, Any]]:
        with self.connect_readonly() as connection:
            rows = connection.execute("SELECT * FROM sources ORDER BY retrieved_at DESC, id ASC")
            result = []
            for row in rows:
                item = dict(row)
                item["metadata"] = _decode(item.pop("metadata_json"), "sources.metadata_json")
                result.append(item)
            return result

    def hypotheses(self) -> list[dict[str, Any]]:
        with self.connect_readonly() as connection:
            rows = connection.execute("SELECT * FROM hypotheses ORDER BY total_score DESC, created_at ASC, id ASC")
            return [self._hypothesis(connection, row) for row in rows]

    def _hypothesis(self, connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["required_data"] = _decode(item.pop("required_data_json"), "hypotheses.required_data_json")
        item["metadata"] = _decode(item.pop("metadata_json"), "hypotheses.metadata_json")
        item["candidate_path"] = self._safe_artifact(
            item.get("candidate_path"), item.get("candidate_sha256")
        )
        supporting: list[dict[str, Any]] = []
        contradicting: list[dict[str, Any]] = []
        evidence_rows = connection.execute(
            "SELECT s.*, hs.stance, hs.note FROM hypothesis_sources hs JOIN sources s ON s.id = hs.source_id WHERE hs.hypothesis_id = ? ORDER BY s.retrieved_at ASC, s.id ASC",
            (item["id"],),
        )
        for evidence in evidence_rows:
            source = dict(evidence)
            source["metadata"] = _decode(source.pop("metadata_json"), "sources.metadata_json")
            target = supporting if source.pop("stance") == "SUPPORT" else contradicting
            target.append(source)
        item["supporting_sources"] = supporting
        item["contradicting_sources"] = contradicting
        return item

    def experiments(self) -> list[dict[str, Any]]:
        with self.connect_readonly() as connection:
            result = []
            references = self._artifact_references(connection)
            for row in connection.execute("SELECT * FROM experiments ORDER BY created_at ASC, id ASC"):
                item = dict(row)
                item["pairs"] = _decode(item.pop("pairs_json"), "experiments.pairs_json")
                item["timeframes"] = _decode(item.pop("timeframes_json"), "experiments.timeframes_json")
                for field in ("config_path", "snapshot_path", "policy_path", "strategy_path"):
                    item.pop(field, None)
                runs = []
                for run in connection.execute("SELECT * FROM runs WHERE experiment_id = ? ORDER BY created_at ASC, id ASC", (item["id"],)):
                    run_item = dict(run)
                    run_item["metrics"] = _decode(run_item.pop("metrics_json"), "runs.metrics_json")
                    manifest = _decode(
                        run_item.pop("artifact_manifest_json"), "runs.artifact_manifest_json"
                    )
                    run_item["artifact_manifest"] = {
                        "artifacts": self._manifest_links(manifest, references)
                    }
                    runs.append(run_item)
                item["runs"] = runs
                result.append(item)
            return result

    def review_queue(self) -> list[dict[str, Any]]:
        return [item for item in self.hypotheses() if item["state"] == HypothesisState.NEEDS_REVIEW]

    def record_review(self, hypothesis_id: str, action: str, reason: str) -> dict[str, Any]:
        target = REVIEW_TARGETS.get(action)
        if target is None:
            raise ValueError(f"unknown review action: {action}")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("review reason is required")
        store = ResearchStore(self.db_path)
        hypothesis = store.get_hypothesis(hypothesis_id)
        if hypothesis is None:
            raise ValueError(f"unknown hypothesis: {hypothesis_id}")
        if hypothesis["state"] != HypothesisState.NEEDS_REVIEW:
            raise ValueError(f"illegal transition: {hypothesis['state']} -> {target}")
        return store.transition_hypothesis(
            hypothesis_id,
            target,
            "local_user",
            reason.strip(),
            cycle_id=hypothesis["cycle_id"],
        )

    def _safe_artifact(self, value: Any, expected_sha256: Any = None) -> str | None:
        if not value:
            return None
        path = Path(str(value))
        resolved = path if path.is_absolute() else self.artifact_root / path
        try:
            resolved = resolved.resolve()
            relative = resolved.relative_to(self.artifact_root).as_posix()
        except ValueError:
            return None
        if not resolved.is_file() or not expected_sha256:
            return None
        if _sha256(resolved) != str(expected_sha256).casefold():
            return None
        return relative

    def _artifact_references(self, connection: sqlite3.Connection) -> dict[str, str]:
        references: dict[str, str] = {}
        for row in connection.execute("SELECT candidate_path, candidate_sha256 FROM hypotheses"):
            relative = self._safe_artifact(row["candidate_path"], row["candidate_sha256"])
            if relative:
                references[relative] = str(row["candidate_sha256"]).casefold()
        for row in connection.execute("SELECT artifact_manifest_json FROM runs"):
            manifest = _decode(row["artifact_manifest_json"], "runs.artifact_manifest_json")
            for entry in self._manifest_entries(manifest):
                relative = self._safe_artifact(entry["path"], entry["sha256"])
                if relative:
                    references[relative] = entry["sha256"].casefold()
        return references

    def _manifest_links(
        self, manifest: Any, references: dict[str, str]
    ) -> list[dict[str, Any]]:
        links = []
        seen: set[str] = set()
        for entry in self._manifest_entries(manifest):
            path = self._safe_artifact(entry["path"], entry["sha256"])
            if not path or path in seen or references.get(path) != entry["sha256"].casefold():
                continue
            seen.add(path)
            link = {
                "path": path,
                "url": f"/artifacts/{quote(path, safe='/')}",
                "sha256": entry["sha256"],
            }
            if entry.get("size") is not None:
                link["size"] = entry["size"]
            links.append(link)
        return links

    @classmethod
    def _manifest_entries(cls, value: Any) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        if isinstance(value, list):
            for item in value:
                entries.extend(cls._manifest_entries(item))
            return entries
        if not isinstance(value, dict):
            return entries
        for path_key in ("path", "manifest_path", "report_path", "artifact_path"):
            path = value.get(path_key)
            if not isinstance(path, str) or not path.strip():
                continue
            hash_key = "sha256" if path_key == "path" else f"{path_key.removesuffix('_path')}_sha256"
            digest = value.get(hash_key) or value.get("sha256")
            if isinstance(digest, str) and digest:
                entry = {"path": path, "sha256": digest}
                if isinstance(value.get("size"), int):
                    entry["size"] = value["size"]
                entries.append(entry)
        for key, nested in value.items():
            if key not in {"path", "manifest_path", "report_path", "artifact_path", "sha256", "manifest_sha256", "report_sha256"}:
                entries.extend(cls._manifest_entries(nested))
        return entries

    def artifact(self, relative_path: str) -> Path | None:
        if not relative_path or Path(relative_path).is_absolute():
            return None
        try:
            resolved = (self.artifact_root / relative_path).resolve()
            relative = resolved.relative_to(self.artifact_root).as_posix()
        except ValueError:
            return None
        if not resolved.is_file():
            return None
        with self.connect_readonly() as connection:
            expected = self._artifact_references(connection).get(relative)
        if expected is None or _sha256(resolved) != expected:
            return None
        return resolved


def build_server(db_path: Path, artifact_root: Path, port: int = 0):
    return _build_http_server(DashboardReadModel(db_path, artifact_root), port)


def _build_http_server(read_model: DashboardReadModel, port: int):
    from http.server import ThreadingHTTPServer

    class DashboardHTTPServer(ThreadingHTTPServer):
        daemon_threads = True

    class Handler(_DashboardHandler):
        model = read_model

    return DashboardHTTPServer(("127.0.0.1", port), Handler)


def serve(db_path: Path, artifact_root: Path, port: int = 7400) -> None:
    server = build_server(db_path, artifact_root, port)
    try:
        server.serve_forever()
    finally:
        server.server_close()


class _DashboardHandler(BaseHTTPRequestHandler):
    # Set by _build_http_server; keeping the handler stateless avoids global DB connections.
    model: DashboardReadModel

    def _headers(self, content_type: str = "application/json") -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:")
        self.send_header("X-Content-Type-Options", "nosniff")

    def _json_response(self, status: int, value: Any) -> None:
        body = json.dumps(value, ensure_ascii=False, default=str).encode()
        self.send_response(status)
        self._headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._headers()
        self.send_header("Access-Control-Allow-Origin", f"http://127.0.0.1:{self.server.server_port}")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        from urllib.parse import urlsplit

        path = urlsplit(self.path).path
        routes: dict[str, Callable[[], Any]] = {
            "/api/overview": self.model.overview,
            "/api/sources": self.model.sources,
            "/api/hypotheses": self.model.hypotheses,
            "/api/experiments": self.model.experiments,
            "/api/review": self.model.review_queue,
        }
        if path in routes:
            try:
                self._json_response(200, routes[path]())
            except (OSError, ValueError) as exc:
                self._json_response(500, {"error": str(exc)})
            return
        if path == "/":
            self._serve_file(Path(__file__).resolve().parent.parent / "dashboard" / "index.html", "text/html; charset=utf-8")
            return
        if path == "/assets/plotly.min.js":
            try:
                import plotly
                asset = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
                self._serve_file(asset, "application/javascript")
            except (ImportError, OSError):
                self.send_error(404)
            return
        if path.startswith("/artifacts/"):
            relative = unquote(path.removeprefix("/artifacts/"))
            artifact = self.model.artifact(relative)
            if artifact is None:
                self.send_error(404)
                return
            content_type = mimetypes.guess_type(artifact.name)[0] or "application/octet-stream"
            self._serve_file(artifact, content_type)
            return
        self.send_error(404)

    def _serve_file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self._headers(content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        from urllib.parse import urlsplit

        if urlsplit(self.path).path.startswith("/api/hypotheses/") and urlsplit(self.path).path.endswith("/review"):
            origin = self.headers.get("Origin")
            expected = f"http://127.0.0.1:{self.server.server_port}"
            if origin != expected:
                self._json_response(403, {"error": "same-origin Origin is required"})
                return
            if self.headers.get_content_type() != "application/json":
                self._json_response(415, {"error": "application/json is required"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length < 0:
                self._json_response(400, {"error": "invalid content length"})
                return
            if length > 16 * 1024:
                self._json_response(413, {"error": "request body is too large"})
                return
            try:
                body = json.loads(self.rfile.read(length))
                action, reason = body["action"], body["reason"]
                hypothesis_id = urlsplit(self.path).path.split("/")[3]
                result = self.model.record_review(hypothesis_id, action, reason)
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                status = 409 if isinstance(exc, ValueError) and "illegal transition" in str(exc) else 400
                self._json_response(status, {"error": str(exc)})
                return
            self._json_response(200, result)
            return
        self.send_error(404)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Loopback research dashboard")
    parser.add_argument("--db", type=Path, default=Path("user_data/research.sqlite"))
    parser.add_argument("--artifacts", type=Path, default=Path("user_data/research-artifacts"))
    parser.add_argument("--port", type=int, default=7400)
    args = parser.parse_args(argv)
    serve(args.db, args.artifacts, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
