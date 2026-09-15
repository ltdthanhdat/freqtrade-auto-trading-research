import json
import hashlib
from http.client import HTTPConnection
from threading import Thread
from urllib.parse import urlsplit

import pytest

from research_runtime.dashboard import DashboardReadModel, build_server
from research_runtime.core import HypothesisState
from research_runtime.store import ResearchStore


@pytest.fixture
def seeded_store(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    now = "2026-09-11T08:00:00Z"
    cycle = store.start_or_resume_cycle(now)["cycle"]
    cycle_id = cycle["id"]
    store.insert_source(
        cycle_id,
        {
            "id": "S-1",
            "provider": "openalex",
            "canonical_url": "https://example.test/1",
            "title": "source",
            "excerpt": "evidence",
            "license": "CC-BY",
            "retrieved_at": now,
            "fingerprint": "fingerprint-1",
            "metadata": {"full_text": True},
        },
    )
    base = {
        "thesis": "thesis",
        "mechanism": "mechanism",
        "market_scope": "crypto perpetuals 30m",
        "required_data": ["OHLCV"],
        "falsifier": "stressed OOS profit <= 0",
        "scores": {
            "evidence_quality": 20,
            "reproducibility": 20,
            "ohlcv_transferability": 15,
            "novelty": 5,
            "falsifiability": 10,
        },
    }
    for identifier, state in (
        ("H-QUEUED", HypothesisState.QUEUED),
        ("H-TESTING", HypothesisState.TESTING),
        ("H-READY", HypothesisState.NEEDS_REVIEW),
    ):
        store.insert_hypothesis(cycle_id, {**base, "id": identifier})
        if state == HypothesisState.QUEUED:
            store.transition_hypothesis(identifier, state, "runtime", "queued")
        elif state == HypothesisState.TESTING:
            store.transition_hypothesis(identifier, HypothesisState.QUEUED, "runtime", "queued")
            store.transition_hypothesis(identifier, HypothesisState.IMPLEMENTING, "runtime", "implement")
            store.transition_hypothesis(identifier, state, "runtime", "testing")
        else:
            store.transition_hypothesis(identifier, HypothesisState.QUEUED, "runtime", "queued")
            store.transition_hypothesis(identifier, HypothesisState.IMPLEMENTING, "runtime", "implement")
            store.transition_hypothesis(identifier, HypothesisState.TESTING, "runtime", "testing")
            store.transition_hypothesis(identifier, state, "runtime", "validation")
    artifact_root = tmp_path / "artifacts"
    candidate = artifact_root / cycle_id / "candidate" / "Strategy.py"
    candidate.parent.mkdir(parents=True)
    candidate.write_text("class Strategy: pass\n")
    candidate_digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
    with store.connect() as connection:
        connection.execute(
            "UPDATE hypotheses SET candidate_path = ?, candidate_sha256 = ? WHERE id = ?",
            (str(candidate), candidate_digest, "H-READY"),
        )
    manifest = artifact_root / cycle_id / "validation" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({
        "verdict": "PASS",
        "cycle_id": cycle_id,
        "hypothesis_id": "H-READY",
        "candidate_sha256": candidate_digest,
        "holdout": {"available": True},
        "walk_forward": {"enabled": True},
    }) + "\n")
    manifest_digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    store.insert_experiment({
        "id": "EXP-READY",
        "cycle_id": cycle_id,
        "hypothesis_id": "H-READY",
        "parent_strategy": "parent",
        "parent_sha256": "a" * 64,
        "changed_variable": "variable",
        "config_path": "config.json",
        "config_sha256": "b" * 64,
        "pairs": [],
        "timeframes": ["30m"],
        "timeframe_detail": "1m",
        "snapshot_path": "snapshot",
        "snapshot_sha256": "c" * 64,
        "policy_path": "policy.json",
        "policy_sha256": "d" * 64,
        "strategy_name": "Strategy",
        "strategy_path": str(candidate.parent),
        "start_at": "2026-09-01T00:00:00Z",
        "end_at": "2026-09-11T00:00:00Z",
        "status": "PASS",
    })
    store.record_run({
        "id": "RUN-READY",
        "experiment_id": "EXP-READY",
        "kind": "validation",
        "status": "NEEDS_REVIEW",
        "verdict": "PASS",
        "metrics": {},
        "artifact_manifest": {
            "manifest_path": str(manifest),
            "manifest_sha256": manifest_digest,
        },
    })
    store.add_hypothesis_source("H-READY", "S-fingerprint-1", "SUPPORT", "explicit rules")
    return store


def test_overview_reports_pipeline_and_current_cycle(seeded_store, tmp_path):
    view = DashboardReadModel(seeded_store.path, tmp_path / "artifacts").overview()
    assert view["counts"] == {"sources": 1, "hypotheses": 3, "queued": 1, "testing": 1, "review": 1}
    assert view["current_cycle"]["stage"] == "COLLECTING"


def test_read_models_decode_provenance_and_evidence(seeded_store, tmp_path):
    model = DashboardReadModel(seeded_store.path, tmp_path / "artifacts")
    assert model.sources()[0]["canonical_url"] == "https://example.test/1"
    ready = next(item for item in model.hypotheses() if item["id"] == "H-READY")
    assert ready["required_data"] == ["OHLCV"]
    assert ready["supporting_sources"][0]["id"] == "S-fingerprint-1"


def test_dashboard_exposes_cycle_and_event_history(seeded_store, tmp_path):
    model = DashboardReadModel(seeded_store.path, tmp_path / "artifacts")
    assert model.cycles()[0]["id"] == model.overview()["current_cycle"]["id"]
    assert model.events(model.cycles()[0]["id"])[0]["cycle_id"] == model.cycles()[0]["id"]


def test_review_requires_verified_pass_bundle(seeded_store, tmp_path):
    with seeded_store.connect() as connection:
        connection.execute("DELETE FROM runs WHERE id = 'RUN-READY'")
    with pytest.raises(ValueError, match="review bundle"):
        DashboardReadModel(seeded_store.path, tmp_path / "artifacts").record_review(
            "H-READY", "approve", "looks stable"
        )


def test_review_requires_needs_review_state_and_uses_store_transition(seeded_store, tmp_path):
    model = DashboardReadModel(seeded_store.path, tmp_path / "artifacts")
    with pytest.raises(ValueError, match="illegal transition"):
        model.record_review("H-TESTING", "approve", "looks stable")
    result = model.record_review("H-READY", "approve", "reviewed WFO and bootstrap")
    assert result["state"] == HypothesisState.APPROVED_FOR_DRY_RUN


def test_review_rejects_unknown_action_and_empty_reason(seeded_store, tmp_path):
    model = DashboardReadModel(seeded_store.path, tmp_path / "artifacts")
    with pytest.raises(ValueError, match="unknown review action"):
        model.record_review("H-READY", "hold", "reason")
    with pytest.raises(ValueError, match="reason"):
        model.record_review("H-READY", "reject", " ")


def test_dashboard_main_uses_resolved_database_and_artifact_paths(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setenv("RESEARCH_DB", str(tmp_path / "research.sqlite"))
    monkeypatch.setenv("RESEARCH_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setattr(
        "research_runtime.dashboard.serve",
        lambda db, artifacts, port: captured.update(db=db, artifacts=artifacts, port=port),
    )

    from research_runtime.dashboard import main

    assert main(["--port", "7410"]) == 0
    assert captured == {
        "db": tmp_path / "research.sqlite",
        "artifacts": tmp_path / "artifacts",
        "port": 7410,
    }


def test_empty_database_has_honest_empty_views(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    model = DashboardReadModel(store.path, tmp_path / "artifacts")
    assert model.overview()["current_cycle"] is None
    assert model.sources() == []
    assert model.hypotheses() == []
    assert model.experiments() == []
    assert model.review_queue() == []


def test_artifact_links_never_escape_configured_root(seeded_store, tmp_path):
    outside = tmp_path / "outside.py"
    outside.write_text("not a candidate")
    with seeded_store.connect() as connection:
        connection.execute(
            "UPDATE hypotheses SET candidate_path = ?, candidate_sha256 = ? WHERE id = ?",
            (str(outside), "a" * 64, "H-READY"),
        )
    view = next(item for item in DashboardReadModel(seeded_store.path, tmp_path / "artifacts").hypotheses() if item["id"] == "H-READY")
    assert view["candidate_path"] is None


def test_experiment_artifacts_are_hash_verified_and_paths_are_redacted(seeded_store, tmp_path):
    artifacts = tmp_path / "artifacts"
    artifact = artifacts / "C-1" / "validation" / "manifest.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"verdict":"PASS"}\n')
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    with seeded_store.connect() as connection:
        cycle_id = connection.execute("SELECT id FROM cycles LIMIT 1").fetchone()[0]
    seeded_store.insert_experiment(
        {
            "id": "EXP-1",
            "cycle_id": cycle_id,
            "hypothesis_id": "H-READY",
            "parent_strategy": "parent",
            "parent_sha256": "a" * 64,
            "changed_variable": "variable",
            "config_path": "/private/config.json",
            "config_sha256": "b" * 64,
            "pairs": ["BTC/USDT:USDT"],
            "timeframes": ["30m"],
            "timeframe_detail": "1m",
            "snapshot_path": "/private/snapshot",
            "snapshot_sha256": "c" * 64,
            "policy_path": "/private/policy.json",
            "policy_sha256": "d" * 64,
            "strategy_name": "Candidate",
            "strategy_path": "/private/strategy",
            "start_at": "2026-09-01T00:00:00Z",
            "end_at": "2026-09-11T00:00:00Z",
            "status": "PASS",
        }
    )
    seeded_store.record_run(
        {
            "id": "RUN-1",
            "experiment_id": "EXP-1",
            "kind": "validation",
            "status": "NEEDS_REVIEW",
            "verdict": "PASS",
            "metrics": {"fold_metrics": []},
            "artifact_manifest": [
                {"path": "C-1/validation/manifest.json", "size": artifact.stat().st_size, "sha256": digest},
                {"path": "/private/not-an-artifact.txt", "sha256": "e" * 64},
            ],
        }
    )
    experiment = DashboardReadModel(seeded_store.path, artifacts).experiments()[0]
    assert "config_path" not in experiment
    links = experiment["runs"][0]["artifact_manifest"]["artifacts"]
    assert links == [{"path": "C-1/validation/manifest.json", "url": "/artifacts/C-1/validation/manifest.json", "sha256": digest, "size": artifact.stat().st_size}]


def request(origin, method, path, body=None, headers=None):
    parsed = urlsplit(origin)
    connection = HTTPConnection(parsed.hostname, parsed.port, timeout=2)
    encoded = None if body is None else json.dumps(body).encode()
    connection.request(method, path, body=encoded, headers=headers or {})
    response = connection.getresponse()
    result = response.status, response.headers, response.read().decode()
    connection.close()
    return result


def test_http_contract(seeded_store, tmp_path):
    server = build_server(seeded_store.path, tmp_path / "artifacts", port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        status, headers, body = request(origin, "GET", "/api/overview")
        assert status == 200
        assert json.loads(body)["counts"]["sources"] == 1
        assert headers["Content-Security-Policy"].startswith("default-src 'self'")
        assert request(origin, "GET", "/")[0] == 200
        asset_status, asset_headers, _ = request(origin, "GET", "/assets/plotly.min.js")
        assert asset_status == 200
        assert asset_headers["Content-Type"].startswith("application/javascript")

        status, _, body = request(
            origin,
            "POST",
            "/api/hypotheses/H-READY/review",
            body={"action": "approve", "reason": "reviewed WFO and bootstrap"},
            headers={"Origin": origin, "Content-Type": "application/json"},
        )
        assert status == 200
        assert json.loads(body)["state"] == "APPROVED_FOR_DRY_RUN"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


@pytest.mark.parametrize(
    ("headers", "status"),
    [({}, 403), ({"Origin": "http://evil.test", "Content-Type": "application/json"}, 403),
     ({"Origin": "http://127.0.0.1:0", "Content-Type": "text/plain"}, 403)],
)
def test_http_review_requires_same_origin(seeded_store, tmp_path, headers, status):
    server = build_server(seeded_store.path, tmp_path / "artifacts", port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        actual, _, _ = request(origin, "POST", "/api/hypotheses/H-READY/review", {"action": "approve", "reason": "x"}, headers)
        assert actual == status
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_http_review_rejects_content_size_action_and_routes(seeded_store, tmp_path):
    server = build_server(seeded_store.path, tmp_path / "artifacts", port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    good_headers = {"Origin": origin, "Content-Type": "application/json"}
    try:
        status, _, _ = request(origin, "POST", "/api/hypotheses/H-READY/review", {"action": "hold", "reason": "x"}, good_headers)
        assert status == 400
        status, _, _ = request(origin, "POST", "/api/hypotheses/H-READY/review", ["approve"], good_headers)
        assert status == 400
        status, _, _ = request(origin, "POST", "/api/hypotheses/H-TESTING/review", {"action": "approve", "reason": "x"}, good_headers)
        assert status == 409
        status, _, _ = request(origin, "POST", "/api/hypotheses/H-READY/review", {"action": "approve", "reason": "x"}, {"Origin": origin, "Content-Type": "text/plain"})
        assert status == 415
        status, _, _ = request(origin, "POST", "/api/hypotheses/H-READY/review", {"action": "approve", "reason": "x"}, {**good_headers, "Content-Length": str(17 * 1024)})
        assert status == 413
        assert request(origin, "GET", "/missing")[0] == 404
        assert request(origin, "GET", "/%2e%2e/research.sqlite")[0] == 404
        status, headers, _ = request(origin, "OPTIONS", "/api/overview")
        assert status == 204
        assert headers["Access-Control-Allow-Origin"] == origin
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_http_artifact_route_requires_reference_and_matching_hash(seeded_store, tmp_path):
    artifacts = tmp_path / "artifacts"
    artifact = artifacts / "C-1" / "evidence.txt"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("verified\n")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    with seeded_store.connect() as connection:
        cycle_id = connection.execute("SELECT id FROM cycles LIMIT 1").fetchone()[0]
    seeded_store.record_run(
        {
            "id": "RUN-ARTIFACT",
            "experiment_id": seeded_store.insert_experiment(
                {
                    "id": "EXP-ARTIFACT",
                    "cycle_id": cycle_id,
                    "hypothesis_id": "H-READY",
                    "parent_strategy": "parent",
                    "parent_sha256": "a" * 64,
                    "changed_variable": "variable",
                    "config_path": "config.json",
                    "config_sha256": "b" * 64,
                    "pairs": [],
                    "timeframes": ["30m"],
                    "timeframe_detail": "1m",
                    "snapshot_path": "snapshot",
                    "snapshot_sha256": "c" * 64,
                    "policy_path": "policy.json",
                    "policy_sha256": "d" * 64,
                    "strategy_name": "Candidate",
                    "strategy_path": "strategy",
                    "start_at": "2026-09-01T00:00:00Z",
                    "end_at": "2026-09-11T00:00:00Z",
                    "status": "PASS",
                }
            )["id"],
            "kind": "validation",
            "status": "PASS",
            "verdict": "PASS",
            "metrics": {},
            "artifact_manifest": [{"path": "C-1/evidence.txt", "sha256": digest}],
        }
    )
    server = build_server(seeded_store.path, artifacts, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        assert request(origin, "GET", "/artifacts/C-1/evidence.txt")[0] == 200
        assert request(origin, "GET", "/artifacts/C-1/missing.txt")[0] == 404
        artifact.write_text("tampered\n")
        assert request(origin, "GET", "/artifacts/C-1/evidence.txt")[0] == 404
        assert request(origin, "GET", "/artifacts/%2e%2e/research.sqlite")[0] == 404
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
