from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from freqtrade.data.history import get_datahandler
from freqtrade.enums import CandleType


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.smc_fvg_pinbar_data import (  # noqa: E402
    ALL_FUTURES_CACHE_DIR,
    Window,
    cache_path,
    load_cache,
    seed_symbol_windows,
)


BASELINE_WINDOW = Window("baseline_2024_01_01_to_2024_03_01", 1704067200000, 1709337540000)
RECENT_WINDOW = Window("recent_2026_03_01_to_2026_04_30", 1772323200000, 1777593540000)
RECENT_SYMBOLS = [
    "BTC-USDT",
    "PLAY-USDT",
    "BIO-USDT",
    "SPACE-USDT",
    "PENDLE-USDT",
    "BR-USDT",
    "D-USDT",
    "YGG-USDT",
    "STG-USDT",
]


def to_freqtrade_pair(symbol: str) -> str:
    base, quote = symbol.split("-")
    return f"{base}/{quote}:{quote}"


def jesse_cache_to_dataframe(candles) -> pd.DataFrame:
    dataframe = pd.DataFrame(
        {
            "date": pd.to_datetime(candles[:, 0].astype("int64"), unit="ms", utc=True),
            "open": candles[:, 1].astype(float),
            "close": candles[:, 2].astype(float),
            "high": candles[:, 3].astype(float),
            "low": candles[:, 4].astype(float),
            "volume": candles[:, 5].astype(float),
        }
    )
    dataframe = dataframe[["date", "open", "high", "low", "close", "volume"]]
    return dataframe.sort_values("date").reset_index(drop=True)


def resample_ohlcv(dataframe: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    rule = {"1h": "1h", "15m": "15min", "5m": "5min", "1m": "1min"}[timeframe]
    frame = dataframe.set_index("date")
    resampled = (
        frame.resample(rule, label="left", closed="left")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna()
        .reset_index()
    )
    return resampled


def export_symbol(window: Window, symbol: str, datadir: Path) -> None:
    if window == BASELINE_WINDOW and symbol == "BTC-USDT":
        source = ROOT / "storage" / "temp" / cache_path(Path("."), symbol, window).name
        candles = load_cache(source)
    else:
        seeded = seed_symbol_windows(symbol, [window], ALL_FUTURES_CACHE_DIR)
        result = seeded[window.name]
        if "error" in result:
            raise RuntimeError(f"{symbol} {window.name}: {result['error']}")
        candles = load_cache(Path(result["cache_path"]))

    dataframe_1m = jesse_cache_to_dataframe(candles)
    dataframe_1h = resample_ohlcv(dataframe_1m, "1h")

    handler = get_datahandler(datadir, data_format="feather")
    pair = to_freqtrade_pair(symbol)
    handler.ohlcv_store(pair, "1m", dataframe_1m, CandleType.FUTURES)
    handler.ohlcv_store(pair, "1h", dataframe_1h, CandleType.FUTURES)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=["btc-baseline", "recent-selected"], required=True)
    args = parser.parse_args()

    if args.scope == "btc-baseline":
        datadir = ROOT / "freqtrade-template" / "user_data" / "data" / "btc_baseline_binance"
        datadir.mkdir(parents=True, exist_ok=True)
        export_symbol(BASELINE_WINDOW, "BTC-USDT", datadir)
        print(datadir)
        return

    datadir = ROOT / "freqtrade-template" / "user_data" / "data" / "recent_selected_binance"
    datadir.mkdir(parents=True, exist_ok=True)
    for symbol in RECENT_SYMBOLS:
        export_symbol(RECENT_WINDOW, symbol, datadir)
        print(f"exported {symbol}")
    print(datadir)


if __name__ == "__main__":
    main()
