import argparse
from dataclasses import asdict
import json
from pathlib import Path

from scripts.validate_baseline import collect_identity, run_validation


class FakeExecutor:
    def __init__(self, trades=None):
        self.commands: list[list[str]] = []
        self.trades = trades or [
            {"pair": "PLAY/USDT:USDT", "enter_tag": "base", "profit_ratio": 0.01}
            for _ in range(51)
        ] + [
            {"pair": "BIO/USDT:USDT", "enter_tag": "displacement", "profit_ratio": 0.01}
            for _ in range(51)
        ]

    def __call__(self, command, **_kwargs):
        self.commands.append(command)
        if command[3] == "backtesting":
            filename = Path(command[command.index("--backtest-filename") + 1])
            filename.write_text(json.dumps({"strategy": {"baseline": {"trades": self.trades}}}))
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
    args = argparse.Namespace(
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
    args.approved_identity = asdict(collect_identity(config, strategy_file, datadir))
    args.p95_drawdown = lambda _metrics: 0.0
    return args


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
    assert result.verdict == "PASS"
    assert result.report_path.exists()


def test_runner_fails_when_identity_does_not_match_approved_baseline(tmp_path):
    args = make_args(tmp_path, complete=True)
    args.approved_identity["config_sha256"] = "not-the-approved-config"

    result = run_validation(args, executor=FakeExecutor())

    assert result.verdict == "FAIL"
    assert "config identity does not match approved baseline" in result.reasons


def test_runner_fails_when_fold_drawdown_exceeds_policy(tmp_path):
    trades = [
        {"pair": "PLAY/USDT:USDT", "enter_tag": "base", "profit_ratio": 0.20},
        {"pair": "BIO/USDT:USDT", "enter_tag": "displacement", "profit_ratio": -0.20},
    ] * 60

    result = run_validation(make_args(tmp_path, complete=True), executor=FakeExecutor(trades))

    assert result.verdict == "FAIL"
    assert "OOS drawdown exceeds policy" in result.reasons


def test_runner_records_three_chronological_folds_and_100_trade_pass_gate(tmp_path):
    result = run_validation(make_args(tmp_path, complete=True), executor=FakeExecutor())
    manifest = json.loads(result.manifest_path.read_text())

    assert len(result.folds) == 3
    assert all(
        result.folds[index].oos_end <= result.folds[index + 1].oos_start for index in range(2)
    )
    assert sum(metric["trades"] for metric in manifest["fold_metrics"]) >= 100
    assert result.verdict == "PASS"


def test_runner_fails_when_oos_fold_count_is_below_policy_requirement(tmp_path):
    args = make_args(tmp_path, complete=True)
    args.end = "2025-06-01"

    result = run_validation(args, executor=FakeExecutor())

    assert result.verdict == "FAIL"
    assert "requires 3 OOS folds, found 1" in result.reasons


def test_runner_fails_closed_when_attribution_cannot_be_evidenced(tmp_path):
    trades = [
        {"pair": "PLAY/USDT:USDT", "enter_tag": "base", "profit_ratio": 0.01}
        for _ in range(102)
    ]

    result = run_validation(make_args(tmp_path, complete=True), executor=FakeExecutor(trades))

    assert result.verdict == "FAIL"
    assert "attribution evidence is insufficient" in result.reasons


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
