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
