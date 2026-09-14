from argparse import Namespace
import hashlib
import json
from pathlib import Path

import pytest

from research_runtime.freqtrade_preflight import CandidatePreflightResult, preflight_candidate
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


def isolated_preflight(values: dict[str, object]):
    return lambda **_: CandidatePreflightResult(
        True,
        str(values["strategy_name"]),
        Path(str(values["strategy_path"])),
        (),
    )


def identity_bound_experiment_for(candidate: Path, tmp_path: Path) -> dict[str, object]:
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "strategy": candidate.stem,
                "strategy_path": str(candidate.parent),
                "trading_mode": "futures",
                "can_short": True,
                "exchange": {"pair_whitelist": ["BTC/USDT:USDT"]},
            }
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
    return {
        "id": "EXP-preflight",
        "candidate_path": str(candidate),
        "candidate_sha256": digest,
        "strategy_name": candidate.stem,
        "strategy_path": str(candidate.parent),
        "strategy_file": str(candidate),
        "config_path": str(config),
        "snapshot_path": str(tmp_path / "snapshot"),
        "policy_path": str(tmp_path / "policy.json"),
        "start_at": "2026-01-01T00:00:00Z",
        "end_at": "2026-02-01T00:00:00Z",
        "runs_dir": str(tmp_path / "runs"),
        "parent_sha256": "a" * 64,
        "config_sha256": "b" * 64,
        "snapshot_sha256": "c" * 64,
        "policy_sha256": "d" * 64,
        "identity_bound": True,
        "plan_sha256": "e" * 64,
    }


def test_candidate_preflight_rejects_missing_exit_callback_before_oos(tmp_path):
    candidate = tmp_path / "Candidate.py"
    candidate.write_text(
        "from freqtrade.strategy import IStrategy\n"
        "class Candidate(IStrategy):\n"
        "    can_short = True\n"
        "    def populate_indicators(self, dataframe, metadata):\n"
        "        return dataframe\n"
        "    def populate_entry_trend(self, dataframe, metadata):\n"
        "        return dataframe\n",
        encoding="utf-8",
    )
    experiment_values = identity_bound_experiment_for(candidate, tmp_path)

    def must_not_run(_experiment):
        raise AssertionError("OOS validator was called")

    result = validate_candidate(
        experiment_values,
        collect_identity_fn=lambda *_: {
            "config_sha256": "b" * 64,
            "snapshot_sha256": "c" * 64,
            "policy_sha256": "d" * 64,
            "accepted_pairs": ("BTC/USDT:USDT",),
            "strategy": candidate.stem,
            "strategy_path": str(candidate.parent),
        },
        preflight_fn=preflight_candidate,
        run_validation_fn=must_not_run,
    )

    assert result.verdict == "FAIL"
    assert result.state == "REJECTED"
    assert result.error_code == "candidate_preflight"
    assert "populate_exit_trend" in " ".join(result.details)
    assert result.manifest_path and result.manifest_path.is_file()
    assert result.report_path and result.report_path.is_file()
    assert not result.artifacts.get("oos_partitions")


def test_candidate_preflight_allows_a_concrete_futures_strategy(tmp_path):
    base = Path(__file__).parent / "fixtures" / "rsi_candidates" / "FuturesRiskBase_Freqtrade.py"
    candidate = tmp_path / "CandidateValid.py"
    (tmp_path / base.name).write_text(base.read_text(), encoding="utf-8")
    candidate.write_text(
        "from FuturesRiskBase_Freqtrade import FuturesRiskBase_Freqtrade\n"
        "class CandidateValid(FuturesRiskBase_Freqtrade):\n"
        "    def populate_indicators(self, dataframe, metadata):\n"
        "        return dataframe\n",
        encoding="utf-8",
    )
    values = identity_bound_experiment_for(candidate, tmp_path)
    values["identity_bound"] = False
    values.pop("plan_sha256")
    calls = []

    result = validate_candidate(
        values,
        collect_identity_fn=lambda *_: {
            "config_sha256": "b" * 64,
            "snapshot_sha256": "c" * 64,
            "policy_sha256": "d" * 64,
            "accepted_pairs": ("BTC/USDT:USDT",),
            "strategy": candidate.stem,
            "strategy_path": str(candidate.parent),
        },
        preflight_fn=preflight_candidate,
        run_validation_fn=lambda _args: calls.append(True) or {"verdict": "FAIL"},
    )

    assert result.error_code != "candidate_preflight"
    assert calls == [True]


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

    values = experiment(tmp_path)
    result = validate_candidate(
        values,
        collect_identity_fn=identity,
        preflight_fn=isolated_preflight(values),
        run_validation_fn=runner,
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


def test_identity_bound_validation_requires_plan_hash(tmp_path):
    values = experiment(tmp_path)
    values["identity_bound"] = True
    values["candidate_path"] = str(Path(values["candidate_path"]))
    Path(values["candidate_path"]).write_text(
        "from freqtrade.strategy import IStrategy\nclass CandidateA(IStrategy):\n    pass\n"
    )
    with pytest.raises(ValueError, match="plan_sha256"):
        validate_candidate(values, collect_identity_fn=lambda *_: {}, run_validation_fn=lambda _: {})


def test_complete_plan_pass_without_exit_or_risk_coverage_cannot_need_review(tmp_path):
    values = experiment(tmp_path)
    candidate = Path(values["candidate_path"])
    candidate.write_text(
        "from freqtrade.strategy import IStrategy\nclass CandidateA(IStrategy):\n    pass\n"
    )
    values.update({
        "identity_bound": True,
        "candidate_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
        "plan_sha256": "p" * 64,
    })
    manifest = tmp_path / "manifest.json"
    report = tmp_path / "report.md"
    partitions = [{"kind": "WFO_OOS", "start_at": "2025-01-02T00:00:00Z", "end_at": "2025-01-03T00:00:00Z"}]
    manifest.write_text(json.dumps({"verdict": "PASS", "oos_partitions": partitions}))
    report.write_text("report\n")

    result = validate_candidate(
        values,
        collect_identity_fn=lambda *_: {"config_sha256": "b" * 64, "snapshot_sha256": "c" * 64, "policy_sha256": "d" * 64},
        preflight_fn=isolated_preflight(values),
        run_validation_fn=lambda _args: {"verdict": "PASS", "manifest_path": manifest, "report_path": report},
    )

    assert result.verdict == "FAIL"
    assert result.state == "REJECTED"
    assert "exit coverage" in " ".join(result.details)
    assert result.artifacts["oos_partitions"] == partitions


def test_validation_wrapper_exposes_manifest_oos_partitions(tmp_path):
    manifest = tmp_path / "manifest.json"
    report = tmp_path / "report.md"
    partitions = [{"kind": "WFO_OOS", "start_at": "2025-01-02T00:00:00Z", "end_at": "2025-01-03T00:00:00Z"}]
    manifest.write_text(json.dumps({"verdict": "PASS", "oos_partitions": partitions}))
    report.write_text("report\n")

    values = experiment(tmp_path)
    result = validate_candidate(
        values,
        collect_identity_fn=lambda *_: {"config_sha256": "b" * 64, "snapshot_sha256": "c" * 64, "policy_sha256": "d" * 64},
        preflight_fn=isolated_preflight(values),
        run_validation_fn=lambda _args: {"verdict": "PASS", "manifest_path": manifest, "report_path": report},
    )

    assert result.artifacts["oos_partitions"] == partitions


def test_validation_wrapper_classifies_runner_exception_as_retryable(tmp_path):
    def identity(*_args):
        return {"config_sha256": "b" * 64, "snapshot_sha256": "c" * 64, "policy_sha256": "d" * 64}

    def runner(_args):
        raise OSError("runner unavailable")

    values = experiment(tmp_path)
    result = validate_candidate(
        values,
        collect_identity_fn=identity,
        preflight_fn=isolated_preflight(values),
        run_validation_fn=runner,
    )
    assert result.state == "RETRYABLE"
    assert result.error_code == "validation_exception"


def test_validation_rechecks_candidate_identity_before_runner(tmp_path):
    values = experiment(tmp_path)
    values["candidate_sha256"] = hashlib.sha256(Path(values["candidate_path"]).read_bytes()).hexdigest()
    calls = []

    def identity(*_args):
        Path(values["candidate_path"]).write_text("class CandidateA:\n    changed = True\n")
        return {"config_sha256": "b" * 64, "snapshot_sha256": "c" * 64, "policy_sha256": "d" * 64}

    with pytest.raises(ValueError, match="candidate identity"):
        validate_candidate(values, collect_identity_fn=identity, run_validation_fn=lambda _args: calls.append(True))
    assert calls == []


def test_validation_rejects_experiment_metadata_mismatches(tmp_path):
    values = experiment(tmp_path)
    values.update({
        "pairs": ["BTC/USDT:USDT"],
        "timeframes": ["1m", "30m", "1h"],
        "timeframe_detail": "1m",
        "strategy_path": str(Path(values["candidate_path"]).parent),
    })
    identity = {
        "config_sha256": "b" * 64,
        "snapshot_sha256": "c" * 64,
        "policy_sha256": "d" * 64,
        "accepted_pairs": ("BTC/USDT:USDT",),
        "strategy_path": str(Path(values["candidate_path"]).parent),
        "strategy": "CandidateA",
    }
    for field, replacement in {
        "pairs": ["ETH/USDT:USDT"],
        "timeframes": ["30m"],
        "timeframe_detail": "5m",
        "strategy_path": str(tmp_path / "wrong"),
    }.items():
        changed = dict(values)
        changed[field] = replacement
        with pytest.raises(ValueError, match="experiment metadata"):
            validate_candidate(changed, collect_identity_fn=lambda *_: identity, run_validation_fn=lambda _args: {})


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
