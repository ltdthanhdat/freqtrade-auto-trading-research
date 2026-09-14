import argparse

from scripts.seed_freqtrade_data import build_command, parse_args, resolve_datadir, resolve_pairs


def test_resolve_datadir_uses_explicit_data_root(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "sys.argv",
        [
            "seed",
            "--config",
            "config.json",
            "--dataset",
            "snapshots/run-1",
            "--pairs",
            "BTC/USDT:USDT",
            "--days",
            "10",
        ],
    )
    args = parse_args()

    assert resolve_datadir(args, tmp_path) == tmp_path / "snapshots" / "run-1"


def test_download_command_keeps_all_required_timeframes(tmp_path):
    args = argparse.Namespace(
        config="config.json",
        dataset="snapshots/run-1",
        timeframes=["30m", "1h", "1m"],
        days=10,
        timerange=None,
        erase=False,
    )

    command = build_command(args, ["BTC/USDT:USDT"], data_root=tmp_path)

    assert command[command.index("--datadir") + 1] == str(tmp_path / "snapshots" / "run-1")
    assert command[command.index("--timeframes") + 1 : command.index("--pairs")] == ["30m", "1h", "1m"]


def test_smc_basket_preset_is_the_frozen_accepted_six_pair_basket():
    pairs = resolve_pairs(argparse.Namespace(pairs=None, preset="smc-basket"))

    assert pairs == [
        "PLAY/USDT:USDT",
        "BIO/USDT:USDT",
        "SPACE/USDT:USDT",
        "PENDLE/USDT:USDT",
        "BR/USDT:USDT",
        "YGG/USDT:USDT",
    ]
