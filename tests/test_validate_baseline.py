import argparse
import json
from pathlib import Path

from scripts.validate_baseline import run_validation


class FakeExecutor:
    def __init__(self):
        self.commands: list[list[str]] = []

    def __call__(self, command, **_kwargs):
        self.commands.append(command)
        return argparse.Namespace(returncode=0, stdout="", stderr="")


def make_args(tmp_path: Path, complete: bool = False) -> argparse.Namespace:
    config = tmp_path / "config.json"
    strategy_file = tmp_path / "strategy.py"
    datadir = tmp_path / "snapshot"
    config.write_text("{}")
    strategy_file.write_text("class Strategy: pass\n")
    datadir.mkdir()
    for timeframe in ("30m", "1h"):
        (datadir / f"PLAY_USDT_USDT-{timeframe}-futures.feather").write_text(timeframe)
    if complete:
        (datadir / "PLAY_USDT_USDT-1m-futures.feather").write_text("1m")
    return argparse.Namespace(
        config=config,
        strategy_file=strategy_file,
        datadir=datadir,
        policy=Path("config/validation.baseline.json"),
        strategy="SMC_FVG_Context30m_Freqtrade",
        strategy_path=Path("src/strategies"),
        start="2025-01-01",
        end="2025-08-01",
        runs_dir=tmp_path / "runs",
        run_id="20260910T120000Z",
    )


def test_runner_rejects_snapshot_without_1m_data(tmp_path):
    executor = FakeExecutor()

    result = run_validation(make_args(tmp_path), executor=executor)

    assert result.verdict == "FAIL"
    assert "missing timeframe 1m" in result.reasons
    assert executor.commands == []


def test_manifest_binds_config_and_snapshot_hashes(tmp_path):
    executor = FakeExecutor()

    result = run_validation(make_args(tmp_path, complete=True), executor=executor)
    manifest = json.loads(result.manifest_path.read_text())

    assert manifest["config_sha256"]
    assert manifest["strategy_sha256"]
    assert manifest["snapshot_sha256"]
    assert result.report_path.exists()


def test_runner_uses_immutable_freqtrade_commands_per_fold(tmp_path):
    executor = FakeExecutor()

    run_validation(make_args(tmp_path, complete=True), executor=executor)

    commands = executor.commands
    assert [command[3] for command in commands[:2]] == [
        "lookahead-analysis",
        "recursive-analysis",
    ]
    fold_commands = [command for command in commands if command[3] == "backtesting"]
    filenames = [command[command.index("--backtest-filename") + 1] for command in fold_commands]
    assert len(filenames) == len(set(filenames))
    assert all("--cache" in command and "none" in command for command in fold_commands)
    assert all("--timeframe-detail" in command and "1m" in command for command in fold_commands)
    assert all("--export" in command and "trades" in command for command in fold_commands)
