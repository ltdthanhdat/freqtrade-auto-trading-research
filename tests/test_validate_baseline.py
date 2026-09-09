import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess

from scripts.validate_baseline import collect_identity, run_validation


def test_makefile_exposes_validate_snapshot():
    makefile = Path("Makefile").read_text()

    assert "validate-snapshot:" in makefile
    assert "scripts/validate_baseline.py" in makefile


def test_make_validate_snapshot_passes_required_runner_inputs():
    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "--dry-run",
            "validate-snapshot",
            "CONFIG=config/custom.json",
            "DATASET=accepted_6pair_2026q3",
            "STRATEGY=FrozenStrategy",
            "SPATH=custom/strategies",
            "VALIDATION_START=2026-01-01",
            "VALIDATION_END=2026-08-01",
            "APPROVED_IDENTITY=approved.json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "scripts/validate_baseline.py" in result.stdout
    assert "--config config/custom.json" in result.stdout
    assert "--datadir user_data/data/snapshots/accepted_6pair_2026q3" in result.stdout
    assert "--policy config/validation.baseline.json" in result.stdout
    assert "--strategy FrozenStrategy" in result.stdout
    assert "--strategy-path custom/strategies" in result.stdout
    assert "--strategy-file custom/strategies/FrozenStrategy.py" in result.stdout
    assert "--start 2026-01-01" in result.stdout
    assert "--end 2026-08-01" in result.stdout
    assert "--runs-dir .research/smc_fvg_pinbar/runs" in result.stdout
    assert "--approved-identity approved.json" in result.stdout


def test_make_dry_run_requires_validate_pass_gate():
    makefile = Path("Makefile").read_text()

    assert "dry-run: validate-pass install" in makefile


def test_make_validate_pass_requires_a_pass_manifest(tmp_path):
    passed = tmp_path / "passed.json"
    warned = tmp_path / "warned.json"
    failed = tmp_path / "failed.json"
    missing = tmp_path / "missing.json"
    passed.write_text('{"verdict": "PASS"}\n')
    warned.write_text('{"verdict": "WARN"}\n')
    failed.write_text('{"verdict": "FAIL"}\n')

    def validate(manifest: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["make", "--no-print-directory", "validate-pass", f"VALIDATION_MANIFEST={manifest}"],
            check=False,
            capture_output=True,
            text=True,
        )

    assert validate(passed).returncode == 0
    assert validate(warned).returncode != 0
    assert validate(failed).returncode != 0
    assert validate(missing).returncode != 0


def test_make_dry_run_blocks_nonpassing_manifests_before_freqtrade(tmp_path):
    manifests = {
        "missing": tmp_path / "missing.json",
        "warn": tmp_path / "warn.json",
        "fail": tmp_path / "fail.json",
    }
    manifests["warn"].write_text('{"verdict": "WARN"}\n')
    manifests["fail"].write_text('{"verdict": "FAIL"}\n')

    for name, manifest in manifests.items():
        started = tmp_path / f"freqtrade-{name}-started"
        result = subprocess.run(
            [
                "make",
                "--no-print-directory",
                "dry-run",
                f"VALIDATION_MANIFEST={manifest}",
                f"FREQ=touch {started}",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert not started.exists()


def test_make_dry_run_reaches_trade_only_with_pass_manifest(tmp_path):
    manifest = tmp_path / "passed.json"
    invoked = tmp_path / "freqtrade-arguments.json"
    fake_freqtrade = tmp_path / "fake-freqtrade"
    override = tmp_path / "override.mk"
    manifest.write_text('{"verdict": "PASS"}\n')
    fake_freqtrade.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$@\" > {invoked}\n"
    )
    fake_freqtrade.chmod(0o755)
    override.write_text(f"install:\n\t@:\nFREQ := {fake_freqtrade}\n")

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "-f",
            "Makefile",
            "-f",
            str(override),
            "dry-run",
            f"VALIDATION_MANIFEST={manifest}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert invoked.read_text().splitlines() == [
        "trade",
        "--config",
        "config/config.futures.json",
        "--strategy",
        "SMC_FVG_Context30m_Freqtrade",
        "--strategy-path",
        "src/strategies",
    ]


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
