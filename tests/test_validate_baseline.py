import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import zipfile

import pandas as pd
import pytest

from scripts.validate_baseline import _attribution, collect_identity, run_validation


PAIRS = ("PLAY/USDT:USDT", "BIO/USDT:USDT")


def _write_policy(path: Path, pairs: tuple[str, ...] = PAIRS) -> None:
    path.write_text(
        json.dumps(
            {
                "accepted_basket": list(pairs),
                "in_sample_days": 1,
                "oos_days": 1,
                "required_folds": 3,
                "min_oos_trades": 6,
                "max_drawdown": 0.15,
                "stress_fee": 0.001,
                "slippage_per_side": 0.0005,
                "bootstrap_seed": 7,
                "bootstrap_samples": 20,
                "bootstrap_block": "2W",
            }
        )
        + "\n"
    )


def _write_config(path: Path, *, pairs: tuple[str, ...] = PAIRS, dry_run: bool = True) -> None:
    path.write_text(
        json.dumps(
            {
                "dry_run": dry_run,
                "dry_run_wallet": 1000,
                "exchange": {"pair_whitelist": list(pairs)},
                "dataformat_ohlcv": "feather",
                "trading_mode": "futures",
            }
        )
        + "\n"
    )


def _write_snapshot(datadir: Path, pairs: tuple[str, ...] = PAIRS, *, end="2025-01-05") -> None:
    futures = datadir / "futures"
    futures.mkdir(parents=True)
    for pair in pairs:
        pair_name = pair.replace("/", "_").replace(":", "_")
        for timeframe, frequency in (("1m", "1min"), ("30m", "30min"), ("1h", "1h")):
            dates = pd.date_range("2025-01-01", end, freq=frequency, tz="UTC")
            pd.DataFrame(
                {
                    "date": dates,
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.0,
                    "close": 10.0,
                    "volume": 1.0,
                }
            ).to_feather(futures / f"{pair_name}-{timeframe}-futures.feather")


def _trades(timerange: str, *, profit_abs=10.0, one_source=False):
    start = pd.Timestamp(timerange.split("-")[0], tz="UTC")
    rows = []
    for index in range(4):
        rows.append(
            {
                "pair": PAIRS[0] if one_source or index % 2 == 0 else PAIRS[1],
                "enter_tag": " Base " if one_source or index % 2 == 0 else "DISPLACEMENT",
                "is_short": bool(index % 2),
                "profit_ratio": profit_abs / 100,
                "profit_abs": profit_abs,
                "stake_amount": 100.0,
                "open_date": str(start + pd.Timedelta(hours=index + 1)),
                "close_date": str(start + pd.Timedelta(hours=index + 2)),
            }
        )
    return rows


class FakeExecutor:
    def __init__(
        self,
        *,
        profit_abs=10.0,
        one_source=False,
        lookahead="pass",
        recursive="pass",
        artifact="one",
        malformed_trades=False,
        empty_trades=False,
    ):
        self.commands: list[list[str]] = []
        self.profit_abs = profit_abs
        self.one_source = one_source
        self.lookahead = lookahead
        self.recursive = recursive
        self.artifact = artifact
        self.malformed_trades = malformed_trades
        self.empty_trades = empty_trades

    def __call__(self, command, **_kwargs):
        self.commands.append(command)
        operation = command[3]
        if operation == "lookahead-analysis":
            if self.lookahead != "missing":
                output = Path(command[command.index("--lookahead-analysis-exportfilename") + 1])
                pd.DataFrame(
                    [
                        {
                            "filename": "Strategy.py",
                            "strategy": "Strategy",
                            "has_bias": self.lookahead == "bias",
                            "total_signals": 12,
                            "biased_entry_signals": 1 if self.lookahead == "bias" else 0,
                            "biased_exit_signals": 0,
                            "biased_indicators": "future" if self.lookahead == "bias" else "",
                        }
                    ]
                ).to_csv(output, index=False)
            return argparse.Namespace(returncode=0, stdout="Lookahead Analysis", stderr="")
        if operation == "recursive-analysis":
            outputs = {
                "pass": "Recursive Analysis\nNo lookahead bias on indicators found.\n",
                "bias": "Recursive Analysis\n=> found lookahead in indicator future\n",
                "inconclusive": "starting recursive analysis\n",
            }
            return argparse.Namespace(returncode=0, stdout=outputs[self.recursive], stderr="")
        if operation == "backtesting":
            directory = Path(command[command.index("--backtest-directory") + 1])
            if self.artifact != "missing":
                timerange = command[command.index("--timerange") + 1]
                trades = _trades(
                    timerange, profit_abs=self.profit_abs, one_source=self.one_source
                )
                if self.empty_trades:
                    trades = []
                if self.malformed_trades:
                    trades[0]["profit_abs"] = "not-a-number"
                payload = {
                    "strategy": {
                        "Strategy": {
                            "trades": trades,
                            "starting_balance": 1000.0,
                            "timerange": timerange,
                            "enable_protections": True,
                        }
                    }
                }
                count = 2 if self.artifact == "ambiguous" else 1
                for number in range(count):
                    with zipfile.ZipFile(
                        directory / f"backtest-result-2025-01-01_00-00-0{number}.zip", "w"
                    ) as archive:
                        archive.writestr("backtest-result.json", json.dumps(payload))
            return argparse.Namespace(returncode=0, stdout="", stderr="")
        raise AssertionError(command)


def make_args(tmp_path: Path, *, snapshot_end="2025-01-05") -> argparse.Namespace:
    config = tmp_path / "config.json"
    policy = tmp_path / "policy.json"
    strategy_path = tmp_path / "strategies"
    strategy_file = strategy_path / "Strategy.py"
    dependency = strategy_path / "dependency.py"
    datadir = tmp_path / "snapshot"
    strategy_path.mkdir()
    strategy_file.write_text("from dependency import Base\nclass Strategy(Base): pass\n")
    dependency.write_text("class Base: pass\n")
    _write_config(config)
    _write_policy(policy)
    _write_snapshot(datadir, end=snapshot_end)
    args = argparse.Namespace(
        config=config,
        strategy_file=strategy_file,
        datadir=datadir,
        policy=policy,
        strategy="Strategy",
        strategy_path=strategy_path,
        start="2025-01-01",
        end="2025-01-05",
        runs_dir=tmp_path / "runs",
        run_id="20260910T120000Z",
    )
    args.approved_identity = asdict(
        collect_identity(config, strategy_file, datadir, policy, args.strategy, strategy_path)
    )
    return args


def test_runner_persists_real_bootstrap_stress_and_attribution_summary(tmp_path):
    result = run_validation(make_args(tmp_path), executor=FakeExecutor())
    manifest = json.loads(result.manifest_path.read_text())

    assert result.verdict == "PASS"
    assert manifest["bootstrap_summary"]["p95_max_drawdown"] >= 0
    assert manifest["fold_metrics"][0]["raw_net_profit"] == pytest.approx(0.04)
    assert manifest["fold_metrics"][0]["net_profit"] == pytest.approx(0.0396)
    assert manifest["attribution"]["by_tag"] == {
        "base": pytest.approx(59.4),
        "displacement": pytest.approx(59.4),
    }
    assert set(manifest["attribution"]["by_side"]) == {"long", "short"}
    assert "strategy_files" in manifest and "dependency.py" in " ".join(
        manifest["strategy_files"]
    )


def test_runner_uses_frozen_analysis_and_supported_fold_artifact_contract(tmp_path):
    executor = FakeExecutor()
    result = run_validation(make_args(tmp_path), executor=executor)
    manifest = json.loads(result.manifest_path.read_text())

    analysis_commands = executor.commands[:2]
    assert all("--timerange" in command for command in analysis_commands)
    assert all("20250101-20250105" in command for command in analysis_commands)
    assert "--lookahead-analysis-exportfilename" in analysis_commands[0]
    assert manifest["correctness_evidence"]["lookahead"]["total_signals"] == 12
    assert manifest["correctness_evidence"]["recursive"]["conclusive"] is True

    fold_commands = [command for command in executor.commands if command[3] == "backtesting"]
    assert len(fold_commands) == 3
    assert all("--backtest-directory" in command for command in fold_commands)
    assert all("--backtest-filename" not in command for command in fold_commands)
    assert all("--enable-protections" in command for command in fold_commands)
    assert all("--fee" in command and "0.001" in command for command in fold_commands)
    assert len(manifest["backtest_artifacts"]) == 3


def test_runner_omits_unsupported_cache_option_from_lookahead_command(tmp_path):
    executor = FakeExecutor()

    run_validation(make_args(tmp_path), executor=executor)

    lookahead_command = next(
        command for command in executor.commands if command[3] == "lookahead-analysis"
    )
    assert "--cache" not in lookahead_command


@pytest.mark.parametrize(
    ("executor", "reason"),
    [
        (FakeExecutor(lookahead="missing"), "lookahead analysis evidence is inconclusive"),
        (FakeExecutor(lookahead="bias"), "lookahead analysis detected bias"),
        (FakeExecutor(recursive="inconclusive"), "recursive analysis evidence is inconclusive"),
        (FakeExecutor(recursive="bias"), "recursive analysis detected lookahead bias"),
        (FakeExecutor(artifact="missing"), "expected one timestamped ZIP"),
        (FakeExecutor(artifact="ambiguous"), "expected one timestamped ZIP"),
    ],
)
def test_runner_fails_closed_on_inconclusive_analysis_or_artifacts(tmp_path, executor, reason):
    result = run_validation(make_args(tmp_path), executor=executor)

    assert result.verdict == "FAIL"
    assert any(reason in item for item in result.reasons)
    assert json.loads(result.manifest_path.read_text())["verdict"] == "FAIL"


def test_runner_rejects_policy_basket_mismatch(tmp_path):
    args = make_args(tmp_path)
    _write_config(args.config, pairs=(PAIRS[0],))

    result = run_validation(args, executor=FakeExecutor())

    assert result.verdict == "FAIL"
    assert "config basket does not match accepted policy basket" in result.reasons


def test_runner_requires_every_pair_and_timeframe(tmp_path):
    args = make_args(tmp_path)
    (args.datadir / "futures" / "BIO_USDT_USDT-1m-futures.feather").unlink()
    args.approved_identity = asdict(
        collect_identity(
            args.config,
            args.strategy_file,
            args.datadir,
            args.policy,
            args.strategy,
            args.strategy_path,
        )
    )

    result = run_validation(args, executor=FakeExecutor())

    assert result.verdict == "FAIL"
    assert "missing OHLCV for BIO/USDT:USDT 1m" in result.reasons


def test_runner_warns_for_insufficient_common_history_and_blocks_pass(tmp_path):
    args = make_args(tmp_path, snapshot_end="2025-01-03")
    executor = FakeExecutor()
    args.approved_identity = asdict(
        collect_identity(
            args.config,
            args.strategy_file,
            args.datadir,
            args.policy,
            args.strategy,
            args.strategy_path,
        )
    )

    result = run_validation(args, executor=executor)

    assert result.verdict == "WARN"
    assert any("common OHLCV history" in item for item in result.reasons)
    fold_commands = [
        command for command in executor.commands if command[3] == "backtesting"
    ]
    assert [
        command[command.index("--timerange") + 1] for command in fold_commands
    ] == ["20250102-20250103"]


def test_runner_warns_when_valid_folds_have_too_few_trades(tmp_path):
    result = run_validation(make_args(tmp_path), executor=FakeExecutor(empty_trades=True))
    manifest = json.loads(result.manifest_path.read_text())

    assert result.verdict == "WARN"
    assert [metric["trades"] for metric in manifest["fold_metrics"]] == [0, 0, 0]
    assert "requires 6 aggregate OOS trades, found 0" in result.reasons


def test_runner_identity_includes_and_rejects_changed_strategy_dependency(tmp_path):
    args = make_args(tmp_path)
    (args.strategy_path / "dependency.py").write_text("class Base: changed = True\n")

    result = run_validation(args, executor=FakeExecutor())

    assert result.verdict == "FAIL"
    assert "strategy identity does not match approved baseline" in result.reasons


def test_cost_stress_controls_oos_profitability_and_verdict(tmp_path):
    result = run_validation(make_args(tmp_path), executor=FakeExecutor(profit_abs=0.05))
    manifest = json.loads(result.manifest_path.read_text())

    assert result.verdict == "FAIL"
    assert manifest["fold_metrics"][0]["raw_net_profit"] > 0
    assert manifest["fold_metrics"][0]["net_profit"] < 0
    assert "aggregate stressed OOS profit is negative" in result.reasons


def test_single_pair_or_tag_source_cannot_pass(tmp_path):
    result = run_validation(make_args(tmp_path), executor=FakeExecutor(one_source=True))
    manifest = json.loads(result.manifest_path.read_text())

    assert result.verdict != "PASS"
    assert manifest["attribution"]["single_source"] is True


def test_attribution_does_not_count_stop_suffixes_as_distinct_tag_sources():
    attribution, diversified = _attribution(
        pd.DataFrame(
            {
                "pair": list(PAIRS),
                "enter_tag": [
                    " displacement|100.0000000000",
                    "DISPLACEMENT|101.0000000000 ",
                ],
                "is_short": [False, True],
                "stressed_profit_abs": [10.0, 10.0],
            }
        )
    )

    assert attribution["by_tag"] == {"displacement": 20.0}
    assert attribution["single_source"] is True
    assert diversified is False


def test_attribution_maps_empty_signal_kinds_to_untagged():
    attribution, diversified = _attribution(
        pd.DataFrame(
            {
                "pair": list(PAIRS),
                "enter_tag": [None, " |100.0000000000"],
                "is_short": [False, True],
                "stressed_profit_abs": [10.0, 10.0],
            }
        )
    )

    assert attribution["by_tag"] == {"untagged": 20.0}
    assert attribution["single_source"] is True
    assert diversified is False


@pytest.mark.parametrize("failure", ["malformed-trades", "malformed-config"])
def test_malformed_inputs_always_write_fail_artifact(tmp_path, failure):
    args = make_args(tmp_path)
    executor = FakeExecutor(malformed_trades=failure == "malformed-trades")
    if failure == "malformed-config":
        args.config.write_text("{broken")

    result = run_validation(args, executor=executor)

    assert result.verdict == "FAIL"
    assert result.manifest_path.exists()
    assert json.loads(result.manifest_path.read_text())["verdict"] == "FAIL"


def test_make_validate_snapshot_uses_supported_module_entrypoint():
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
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "-m scripts.validate_baseline" in result.stdout
    assert "--datadir user_data/data/snapshots/accepted_6pair_2026q3" in result.stdout
