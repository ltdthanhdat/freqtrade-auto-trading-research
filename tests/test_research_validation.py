from argparse import Namespace
import json
from pathlib import Path

import pytest

from research_runtime.validation import ResearchVerdict, validate_candidate


def experiment(tmp_path):
    candidate = tmp_path / "candidate" / "CandidateA.py"
    candidate.parent.mkdir()
    candidate.write_text("class CandidateA:\n    pass\n")
    return {
        "id": "EXP-1",
        "candidate_path": str(candidate),
        "strategy_name": "CandidateA",
        "strategy_path": str(candidate.parent),
        "config_path": str(tmp_path / "config.json"),
        "snapshot_path": str(tmp_path / "snapshot"),
        "policy_path": str(tmp_path / "policy.json"),
        "start_at": "2025-01-01T00:00:00Z",
        "end_at": "2025-02-01T00:00:00Z",
        "runs_dir": str(tmp_path / "runs"),
        "parent_sha256": "a" * 64,
        "config_sha256": "b" * 64,
        "snapshot_sha256": "c" * 64,
        "policy_sha256": "d" * 64,
    }


@pytest.mark.parametrize(
    ("verdict", "state"),
    [("PASS", "NEEDS_REVIEW"), ("WARN", "INCONCLUSIVE"), ("FAIL", "REJECTED")],
)
def test_validation_wrapper_maps_runner_verdicts(tmp_path, verdict, state):
    calls = {}
    manifest = tmp_path / "manifest.json"
    report = tmp_path / "report.md"
    manifest.write_text('{"verdict":"%s"}\n' % verdict)
    report.write_text("report\n")

    def identity(*args):
        calls["identity_args"] = args
        return {"config_sha256": "b" * 64, "snapshot_sha256": "c" * 64, "policy_sha256": "d" * 64}

    def runner(args):
        calls["approved_identity"] = args.approved_identity
        assert isinstance(args, Namespace)
        return {"verdict": verdict, "manifest_path": manifest, "report_path": report, "metrics": {"folds": 3}}

    result = validate_candidate(
        experiment(tmp_path), collect_identity_fn=identity, run_validation_fn=runner
    )
    assert isinstance(result, ResearchVerdict)
    assert result.state == state
    assert result.manifest_hash
    assert result.report_hash
    assert json.loads(manifest.read_text())["candidate_sha256"] == __import__("hashlib").sha256(
        (tmp_path / "candidate" / "CandidateA.py").read_bytes()
    ).hexdigest()
    assert calls["approved_identity"] == {
        "config_sha256": "b" * 64,
        "snapshot_sha256": "c" * 64,
        "policy_sha256": "d" * 64,
    }


def test_validation_wrapper_exposes_manifest_oos_partitions(tmp_path):
    manifest = tmp_path / "manifest.json"
    report = tmp_path / "report.md"
    partitions = [{"kind": "WFO_OOS", "start_at": "2025-01-02T00:00:00Z", "end_at": "2025-01-03T00:00:00Z"}]
    manifest.write_text(json.dumps({"verdict": "PASS", "oos_partitions": partitions}))
    report.write_text("report\n")

    result = validate_candidate(
        experiment(tmp_path),
        collect_identity_fn=lambda *_: {"config_sha256": "b" * 64, "snapshot_sha256": "c" * 64, "policy_sha256": "d" * 64},
        run_validation_fn=lambda _args: {"verdict": "PASS", "manifest_path": manifest, "report_path": report},
    )

    assert result.artifacts["oos_partitions"] == partitions


def test_validation_wrapper_classifies_runner_exception_as_retryable(tmp_path):
    def identity(*_args):
        return {"config_sha256": "b" * 64, "snapshot_sha256": "c" * 64, "policy_sha256": "d" * 64}

    def runner(_args):
        raise OSError("runner unavailable")

    result = validate_candidate(
        experiment(tmp_path), collect_identity_fn=identity, run_validation_fn=runner
    )
    assert result.state == "RETRYABLE"
    assert result.error_code == "validation_exception"


def test_validation_wrapper_rejects_missing_identity_hashes(tmp_path):
    values = experiment(tmp_path)
    del values["policy_sha256"]
    with pytest.raises(ValueError, match="policy_sha256"):
        validate_candidate(values, collect_identity_fn=lambda *_: {}, run_validation_fn=lambda _: {})


def test_validation_wrapper_rejects_changed_parent_strategy(tmp_path, monkeypatch):
    values = experiment(tmp_path)
    parent_root = tmp_path / "parent-strategies"
    parent_root.mkdir()
    parent_file = parent_root / "Frozen.py"
    parent_file.write_text("class Frozen: pass\n")
    values.update({"parent_strategy": "Frozen", "parent_strategy_path": str(parent_root), "parent_sha256": "a" * 64})
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="parent strategy"):
        validate_candidate(values, collect_identity_fn=lambda *_: {"config_sha256": "b" * 64, "snapshot_sha256": "c" * 64, "policy_sha256": "d" * 64}, run_validation_fn=lambda _: {})
