import json
import os
import subprocess
import sys


def run_cli(tmp_path, *requests):
    payload = "".join(json.dumps(request) + "\n" for request in requests)
    env = {**os.environ, "PYTHONPATH": "."}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "research_runtime.cli",
            "--db",
            str(tmp_path / "research.sqlite"),
            "--artifacts",
            str(tmp_path / "artifacts"),
        ],
        input=payload,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return [json.loads(line) for line in result.stdout.splitlines()]


def test_cli_returns_one_structured_response_per_request(tmp_path):
    request = {"tool": "start_or_resume_cycle", "payload": {"now": "2026-09-11T08:00:00Z"}}
    result = run_cli(tmp_path, request)[0]
    assert result["ok"] is True
    assert result["cycle"]["status"] == "RUNNING"


def test_cli_rejects_unknown_fields(tmp_path):
    result = run_cli(
        tmp_path,
        {"tool": "start_or_resume_cycle", "payload": {"extra": 1}},
    )[0]
    assert result == {
        "ok": False,
        "error": {"code": "validation_error", "details": ["unknown fields: extra"]},
    }


def test_cli_handles_malformed_json_and_unknown_operation(tmp_path):
    payload = '{"tool":"load_context","payload":{}}\nnot-json\n'
    env = {**os.environ, "PYTHONPATH": "."}
    result = subprocess.run(
        [sys.executable, "-m", "research_runtime.cli", "--db", str(tmp_path / "db.sqlite")],
        input=payload,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert responses[0]["ok"] is False
    assert responses[0]["error"]["code"] == "validation_error"
    assert responses[1] == {
        "ok": False,
        "error": {"code": "invalid_json", "details": ["request must be a JSON object"]},
    }


def test_cli_reports_unknown_operation_without_nonzero_exit(tmp_path):
    result = run_cli(tmp_path, {"tool": "does_not_exist", "payload": {}})[0]
    assert result["ok"] is False
    assert result["error"]["code"] == "unknown_operation"
