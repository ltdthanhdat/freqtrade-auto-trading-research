import argparse
import json
from pathlib import Path
import subprocess

import pytest

from research_runtime.prompt import load_research_prompt, render_research_prompt
from scripts import research_loop
from scripts.run_summary import read_run_summary
from scripts.research_loop import run_research_loop


def test_research_loop_parser_uses_resolved_state_and_artifact_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("RESEARCH_DB", str(tmp_path / "research.sqlite"))
    monkeypatch.setenv("RESEARCH_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setattr("sys.argv", ["research-loop"])

    args = research_loop.parse_args()

    assert args.db_path == tmp_path / "research.sqlite"
    assert args.summary_root == tmp_path / "artifacts"


def test_prompt_loader_returns_stable_sha256(tmp_path: Path):
    path = tmp_path / "strategy-research.md"
    path.write_text("cycle={{CYCLE_ID}}\ncontext={{VALIDATION_CONTEXT}}\n", encoding="utf-8")

    template, digest = load_research_prompt(path)

    assert template.startswith("cycle={{CYCLE_ID}}")
    assert len(digest) == 64
    assert digest == load_research_prompt(path)[1]


def test_prompt_renderer_replaces_only_known_tokens():
    rendered = render_research_prompt(
        "cycle={{CYCLE_ID}}\ncontext={{VALIDATION_CONTEXT}}\n",
        cycle_id="C-1",
        validation_context="snapshot_sha256=abc",
    )

    assert rendered == "cycle=C-1\ncontext=snapshot_sha256=abc\n"


def test_prompt_renderer_rejects_unresolved_tokens():
    with pytest.raises(ValueError, match="unresolved prompt token"):
        render_research_prompt("{{CYCLE_ID}} {{UNKNOWN}}", cycle_id="C-1", validation_context="x")


def test_supervisor_prompt_tolerates_baked_image_without_git(monkeypatch, tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "config.futures.json").write_text("{}")
    (tmp_path / "config" / "validation.baseline.json").write_text("{}")
    strategy_dir = tmp_path / "src" / "strategies"
    strategy_dir.mkdir(parents=True)
    (strategy_dir / "SMC_FVG_Context30m_Freqtrade.py").write_text("class Strategy: pass\\n")
    (tmp_path / "user_data" / "data" / "snapshots" / "accepted").mkdir(parents=True)

    def fail_without_git(*_args, **_kwargs):
        raise subprocess.CalledProcessError(128, ["git", "rev-parse", "HEAD"])

    import scripts.validate_baseline as validate_baseline

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(validate_baseline, "collect_identity", fail_without_git)

    prompt = research_loop._research_prompt(
        cycle={"id": "C-1", "holdout_start": "", "holdout_end": ""},
        dataset="accepted",
        timerange="20260124-20260911",
        template="cycle={{CYCLE_ID}}\\ncontext={{VALIDATION_CONTEXT}}\\n",
    )

    assert "cycle=C-1" in prompt
    assert "dataset=snapshots/accepted" in prompt


def test_supervisor_prompt_uses_canonical_template_and_cycle_identity():
    prompt = research_loop._research_prompt(
        cycle={"id": "C-1", "holdout_start": "", "holdout_end": ""},
        dataset="accepted",
        timerange="20260124-20260911",
    )

    assert "cycle_id=C-1" in prompt
    assert "required_data" in prompt
    assert "role-specific claim-level evidence" in prompt


def test_supervisor_is_bounded_and_retries_only_incomplete_cycles(tmp_path):
    calls = []
    statuses = iter([
        {"id": "C-1", "status": "INCOMPLETE"},
        {"id": "C-2", "status": "NEEDS_REVIEW"},
    ])

    class FakeStore:
        def __init__(self, _path):
            pass

        def start_or_resume_cycle(self, _payload):
            return {"cycle": {"id": "C-1"}, "acquired": True}

        def list_cycles(self, limit=1):
            return [next(statuses)]

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return argparse.Namespace(returncode=0, stdout="", stderr="")

    result = run_research_loop(
        db_path=tmp_path / "research.sqlite",
        dataset="accepted",
        timerange="20260124-20260911",
        max_cycles=2,
        store_factory=FakeStore,
        command_runner=runner,
        log_path=tmp_path / "research.log",
    )
    assert result["cycles_started"] == 2
    assert result["stopped_reason"] == "NEEDS_REVIEW"
    assert len(calls) == 2
    assert all(
        command[0:2] == ["pi", "-p"]
        and command[command.index("--extension") + 1] == ".pi/extensions/strategy-research.ts"
        and command[command.index("--mode") + 1] == "json"
        and "supporting_source_ids" in command[-1]
        and "contradicting_source_ids" in command[-1]
        and "Do not include" in command[-1]
        and "hypothesis_id" in command[-1]
        and "Use parent strategy" in command[-1]
        and "SMC_FVG_Context30m_Freqtrade" in command[-1]
        and "timeframe_detail='1m'" in command[-1]
        and "sealed holdout" in command[-1]
        and "never use it in development, OOS validation, tuning, or selection" in command[-1]
        and "WFO" in command[-1]
        and "collect_sources` payload" in command[-1]
        and "limit" in command[-1]
        and "not `max_results`" in command[-1]
        and "all experiment fields are nested under" in command[-1]
        for command, _kwargs in calls
    )


def test_supervisor_writes_terminal_summary_when_lease_is_not_acquired(tmp_path):
    class FakeStore:
        def __init__(self, _path):
            pass

        def start_or_resume_cycle(self, _payload):
            return {"cycle": {"id": "C-1", "status": "RUNNING"}, "acquired": False}

    result = run_research_loop(
        db_path=tmp_path / "research.sqlite",
        dataset="accepted",
        timerange="20260124-20260911",
        run_key="scheduled__run-1",
        summary_root=tmp_path / "artifacts",
        store_factory=FakeStore,
        command_runner=lambda *_args, **_kwargs: pytest.fail("Pi must not launch"),
    )

    assert result["cycle_status"] == "INCOMPLETE"
    summary = read_run_summary(tmp_path / "artifacts", "scheduled__run-1")
    assert summary["status"] == "INCOMPLETE"
    assert summary["completed_at"] is not None


def test_supervisor_carries_run_and_sealed_snapshot_identity(tmp_path):
    manifest = tmp_path / "snapshot-readiness.json"
    manifest.write_text(json.dumps({"snapshot_sha256": "a" * 64}), encoding="utf-8")
    payloads = []
    commands = []

    class FakeStore:
        def __init__(self, _path):
            pass

        def start_or_resume_cycle(self, payload):
            payloads.append(payload)
            return {"cycle": {"id": "C-1", "status": "INCOMPLETE"}, "acquired": True}

        def list_cycles(self, limit=1):
            return [{"id": "C-1", "status": "INCOMPLETE"}]

    run_research_loop(
        db_path=tmp_path / "research.sqlite",
        dataset="accepted",
        timerange="20260124-20260911",
        run_key="scheduled__run-1",
        snapshot_manifest=manifest,
        command_runner=lambda command, **_kwargs: commands.append(command) or argparse.Namespace(returncode=0),
        store_factory=FakeStore,
        log_path=tmp_path / "research.log",
    )

    assert payloads[0]["airflow_run_key"] == "scheduled__run-1"
    assert payloads[0]["lease_owner"] == "scheduled__run-1"
    assert payloads[0]["snapshot_sha256"] == "a" * 64
    assert payloads[0]["snapshot_manifest_path"] == str(manifest)
    assert f"snapshot_manifest={manifest}" in commands[0][-1]
    assert "sealed_snapshot_sha256=" + "a" * 64 in commands[0][-1]


def test_supervisor_does_not_launch_pi_without_lease(tmp_path):
    calls = []

    class FakeStore:
        def __init__(self, _path):
            pass

        def start_or_resume_cycle(self, _payload):
            return {"cycle": {"id": "C-1"}, "acquired": False}

    result = run_research_loop(
        db_path=tmp_path / "research.sqlite",
        dataset="accepted",
        timerange="20260124-20260911",
        store_factory=FakeStore,
        command_runner=lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    assert result["cycles_started"] == 0
    assert result["stopped_reason"] == "lease_not_acquired"
    assert result["cycle_status"] == "INCOMPLETE"
    assert calls == []


def test_supervisor_stops_after_one_cycle_limit(tmp_path):
    class FakeStore:
        def __init__(self, _path):
            pass

        def start_or_resume_cycle(self, _payload):
            return {"cycle": {"id": "C-1"}, "acquired": True}

        def list_cycles(self, limit=1):
            return [{"id": "C-1", "status": "INCOMPLETE"}]

    result = run_research_loop(
        db_path=tmp_path / "research.sqlite",
        dataset="accepted",
        timerange="20260124-20260911",
        max_cycles=1,
        store_factory=FakeStore,
        command_runner=lambda *_args, **_kwargs: argparse.Namespace(returncode=0),
        log_path=tmp_path / "research.log",
    )
    assert result["cycles_started"] == 1
    assert result["stopped_reason"] == "max_cycles"


def test_supervisor_uses_configured_research_model(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_MODEL", "openai-codex/gpt-5.6-terra")
    calls = []

    class FakeStore:
        def __init__(self, _path):
            pass

        def start_or_resume_cycle(self, _payload):
            return {"cycle": {"id": "C-1"}, "acquired": True}

        def list_cycles(self, limit=1):
            return [{"id": "C-1", "status": "INCOMPLETE"}]

    def runner(command, **kwargs):
        calls.append(command)
        return argparse.Namespace(returncode=0)

    run_research_loop(
        db_path=tmp_path / "research.sqlite",
        dataset="accepted",
        timerange="20260124-20260911",
        store_factory=FakeStore,
        command_runner=runner,
        log_path=tmp_path / "research.log",
    )
    assert calls[0][calls[0].index("--model") + 1] == "openai-codex/gpt-5.6-terra"


def test_supervisor_persists_pi_error_output(tmp_path):
    reasons = []

    class FakeStore:
        def __init__(self, _path):
            pass

        def start_or_resume_cycle(self, _payload):
            return {"cycle": {"id": "C-1"}, "acquired": True}

        def list_cycles(self, limit=1):
            return [{"id": "C-1", "status": "RUNNING"}]

        def set_cycle_status(self, _cycle_id, _status, reason):
            reasons.append(reason)

    result = run_research_loop(
        db_path=tmp_path / "research.sqlite",
        dataset="accepted",
        timerange="20260124-20260911",
        store_factory=FakeStore,
        command_runner=lambda *_args, **_kwargs: argparse.Namespace(
            returncode=1, stdout="", stderr="Codex error: usage limit reached"
        ),
        log_path=tmp_path / "research.log",
    )
    assert result["stopped_reason"] == "command_failed"
    assert "usage limit reached" in reasons[0]


def test_stream_command_detaches_child_stdin(tmp_path, monkeypatch):
    calls = []

    class FakeStdout:
        def __iter__(self):
            return iter(["child output\n"])

    class FakeProcess:
        stdout = FakeStdout()
        returncode = 0

        def wait(self, timeout):
            return None

        def kill(self):
            raise AssertionError("fake process should not be killed")

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))
        return FakeProcess()

    monkeypatch.setattr(research_loop.subprocess, "Popen", fake_popen)
    result = research_loop._stream_command(
        ["pi"], env={}, timeout=30, log_path=tmp_path / "research.log"
    )

    assert result.returncode == 0
    assert calls[0][1]["stdin"] is subprocess.DEVNULL


def test_supervisor_writes_child_output_to_log(tmp_path):
    class FakeStore:
        def __init__(self, _path):
            pass

        def start_or_resume_cycle(self, _payload):
            return {"cycle": {"id": "C-1"}, "acquired": True}

        def list_cycles(self, limit=1):
            return [{"id": "C-1", "status": "INCOMPLETE"}]

    log_path = tmp_path / "logs" / "research-supervisor.log"
    run_research_loop(
        db_path=tmp_path / "research.sqlite",
        dataset="accepted",
        timerange="20260124-20260911",
        store_factory=FakeStore,
        command_runner=lambda *_args, **_kwargs: argparse.Namespace(
            returncode=0, stdout="child stdout\n", stderr="child stderr\n"
        ),
        log_path=log_path,
    )

    log = log_path.read_text()
    assert "child stdout" in log
    assert "child stderr" in log
