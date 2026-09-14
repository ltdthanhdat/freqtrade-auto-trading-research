import argparse
import subprocess

from scripts import research_loop
from scripts.research_loop import run_research_loop


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
        and "Do not include hypothesis_id" in command[-1]
        and "parent_strategy 'SMC_FVG_Context30m_Freqtrade'" in command[-1]
        and "timeframe_detail '1m'" in command[-1]
        and "sealed holdout" in command[-1]
        and "never use it in development, OOS validation, tuning, or selection" in command[-1]
        and "WFO" in command[-1]
        and "collect_sources payload" in command[-1]
        and "limit, not max_results" in command[-1]
        and "all experiment fields are nested under experiment" in command[-1]
        for command, _kwargs in calls
    )


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

    assert result == {"cycles_started": 0, "stopped_reason": "lease_not_acquired"}
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
