from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_CONFIG = ROOT / "config" / "config.futures.json"
DEFAULT_DATA_ROOT = ROOT / "user_data" / "data"
DEFAULT_DATASET = "active"
DEFAULT_TIMEFRAMES = ["30m", "1h"]
SMC_BASKET = [
    "BTC/USDT:USDT",
    "PLAY/USDT:USDT",
    "BIO/USDT:USDT",
    "SPACE/USDT:USDT",
    "PENDLE/USDT:USDT",
    "BR/USDT:USDT",
    "D/USDT:USDT",
    "YGG/USDT:USDT",
    "STG/USDT:USDT",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed OHLCV data in Freqtrade's standard format."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Freqtrade config used to download data.",
    )
    parser.add_argument(
        "--dataset",
        default=DEFAULT_DATASET,
        help="`active` to seed the default dataset, or a relative path under user_data/data. Example: snapshots/recent_selected.",
    )
    parser.add_argument(
        "--preset",
        choices=["smc-basket"],
        help="Built-in pair list preset.",
    )
    parser.add_argument(
        "--pairs",
        nargs="+",
        help="List of Freqtrade pairs. Example: BTC/USDT:USDT ETH/USDT:USDT",
    )
    parser.add_argument(
        "--timeframes",
        nargs="+",
        default=DEFAULT_TIMEFRAMES,
        help="List of timeframes to seed.",
    )
    parser.add_argument(
        "--days",
        type=int,
        help="Download the most recent N days.",
    )
    parser.add_argument(
        "--timerange",
        help="Freqtrade timerange. Example: 20250101-20250301",
    )
    parser.add_argument(
        "--erase",
        action="store_true",
        help="Erase existing data for the pair/timeframe before downloading again.",
    )
    args = parser.parse_args()

    if bool(args.days) == bool(args.timerange):
        parser.error("Specify exactly one of --days or --timerange.")

    if not args.preset and not args.pairs:
        parser.error("Must provide --preset or --pairs.")

    return args


def resolve_pairs(args: argparse.Namespace) -> list[str]:
    if args.pairs:
        return args.pairs
    if args.preset == "smc-basket":
        return SMC_BASKET
    raise ValueError("Could not resolve pair list.")


def resolve_datadir(args: argparse.Namespace) -> Path:
    if args.dataset == DEFAULT_DATASET:
        return DEFAULT_DATA_ROOT / "binance"
    dataset = Path(args.dataset)
    if dataset.is_absolute() or ".." in dataset.parts:
        raise ValueError("`--dataset` must be a relative path under user_data/data.")
    return DEFAULT_DATA_ROOT / dataset


def build_command(args: argparse.Namespace, pairs: list[str]) -> list[str]:
    datadir = resolve_datadir(args)
    command = [
        "uv",
        "run",
        "python",
        "-m",
        "freqtrade",
        "download-data",
        "--config",
        args.config,
        "--datadir",
        str(datadir),
        "--timeframes",
        *args.timeframes,
        "--pairs",
        *pairs,
    ]
    if args.days:
        command.extend(["--days", str(args.days)])
    if args.timerange:
        command.extend(["--timerange", args.timerange])
    if args.erase:
        command.append("--erase")
    return command


def main() -> None:
    args = parse_args()
    pairs = resolve_pairs(args)
    command = build_command(args, pairs)
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
