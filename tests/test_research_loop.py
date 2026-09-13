import argparse

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
    )
    assert result["cycles_started"] == 2
    assert result["stopped_reason"] == "NEEDS_REVIEW"
    assert len(calls) == 2
    assert all(
        command[0:3] == ["pi", "-p", "--no-extensions"]
        and command[command.index("--extension") + 1] == ".pi/extensions/strategy-research.ts"
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
    )
    assert result["stopped_reason"] == "command_failed"
    assert "usage limit reached" in reasons[0]
