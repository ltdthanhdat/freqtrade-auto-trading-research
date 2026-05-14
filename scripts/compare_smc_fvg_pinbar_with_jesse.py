from __future__ import annotations

import csv
import json
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / "freqtrade-template"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.smc_fvg_pinbar_data import (  # noqa: E402
    ALL_FUTURES_CACHE_DIR,
    Window,
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


def prepare_data() -> None:
    subprocess.run(
        ["uv", "run", "python", "scripts/prepare_smc_fvg_pinbar_data.py", "--scope", "btc-baseline"],
        cwd=TEMPLATE_DIR,
        check=True,
    )
    subprocess.run(
        ["uv", "run", "python", "scripts/prepare_smc_fvg_pinbar_data.py", "--scope", "recent-selected"],
        cwd=TEMPLATE_DIR,
        check=True,
    )


def jesse_metrics(symbol: str, cache_path: Path) -> dict:
    script = f"""
import json
from pathlib import Path
from jesse.research.backtest import backtest
from scripts.smc_fvg_pinbar_data import load_cache

symbol = {symbol!r}
cache_path = Path({str(cache_path)!r})
candles = load_cache(cache_path)
result = backtest(
    config={{
        "starting_balance": 10_000,
        "fee": 0.0004,
        "type": "futures",
        "futures_leverage": 1,
        "futures_leverage_mode": "cross",
        "exchange": "Binance Perpetual Futures",
        "warm_up_candles": 0,
    }},
    routes=[{{
        "exchange": "Binance Perpetual Futures",
        "strategy": "SMC_FVG_PinBar",
        "symbol": symbol,
        "timeframe": "1h",
    }}],
    data_routes=[],
    candles={{
        f"Binance Perpetual Futures-{{symbol}}": {{
            "exchange": "Binance Perpetual Futures",
            "symbol": symbol,
            "candles": candles,
        }}
    }},
    warmup_candles=None,
    generate_equity_curve=False,
    fast_mode=False,
)
metrics = result["metrics"]
trades = result.get("trades", [])
print(json.dumps({{
    "trades_count": len(trades),
    "net_profit_pct": float(metrics.get("net_profit_percentage", 0)),
    "max_drawdown_pct": float(metrics.get("max_drawdown", 0)),
    "win_rate": float(metrics.get("win_rate", 0)),
}}))
"""
    completed = subprocess.run(
        ["uv", "run", "python", "-c", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout.strip())


def load_jesse_cache_path(symbol: str, window: Window) -> Path:
    if symbol == "BTC-USDT" and window == BASELINE_WINDOW:
        return ROOT / "storage" / "temp" / "1704067200000-1709337540000-Binance Perpetual Futures-BTC-USDT.pickle"

    seeded = seed_symbol_windows(symbol, [window], ALL_FUTURES_CACHE_DIR)
    result = seeded[window.name]
    if "error" in result:
        raise RuntimeError(f"{symbol} {window.name}: {result['error']}")
    cache_path = Path(result["cache_path"])
    if cache_path.is_absolute():
        return cache_path
    return TEMPLATE_DIR / cache_path


def freqtrade_metrics(datadir: Path, symbol: str) -> dict:
    pair = to_freqtrade_pair(symbol)
    outdir = TEMPLATE_DIR / "user_data" / "backtest_results" / "compare"
    outdir.mkdir(parents=True, exist_ok=True)

    completed = subprocess.run(
        [
            "uv",
            "run",
            "freqtrade",
            "backtesting",
            "--config",
            "config/config.futures.json",
            "--strategy",
            "SMC_FVG_PinBar_Freqtrade",
            "--strategy-path",
            "src/strategies",
            "--datadir",
            str(datadir),
            "--timeframe",
            "1h",
            "--timeframe-detail",
            "1m",
            "--pairs",
            pair,
            "--fee",
            "0.0004",
            "--dry-run-wallet",
            "10000",
            "--max-open-trades",
            "1",
            "--export",
            "trades",
            "--backtest-directory",
            str(outdir),
            "--cache",
            "none",
        ],
        cwd=TEMPLATE_DIR,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return {
            "error": completed.stderr.strip() or completed.stdout.strip() or f"freqtrade failed for {symbol}",
        }

    latest = json.loads((outdir / ".last_result.json").read_text())
    zip_path = outdir / latest["latest_backtest"]
    with zipfile.ZipFile(zip_path) as zf:
        report_name = next(name for name in zf.namelist() if name.endswith(".json") and "_config" not in name)
        report = json.loads(zf.read(report_name))

    strat = report["strategy"]["SMC_FVG_PinBar_Freqtrade"]
    return {
        "trades_count": int(strat["total_trades"]),
        "net_profit_pct": float(strat["profit_total"]) * 100,
        "max_drawdown_pct": -float(strat["max_drawdown_account"]) * 100,
        "win_rate": float(strat["winrate"]),
    }


def compare_case(symbol: str, window: Window, datadir: Path, scope: str) -> dict:
    cache_path = load_jesse_cache_path(symbol, window)
    jesse = jesse_metrics(symbol, cache_path)
    freqtrade = freqtrade_metrics(datadir, symbol)
    if "error" in freqtrade:
        return {
            "scope": scope,
            "symbol": symbol,
            "status": "freqtrade_error",
            "error": freqtrade["error"],
            "jesse_trades": jesse["trades_count"],
            "freqtrade_trades": None,
            "jesse_net_profit_pct": jesse["net_profit_pct"],
            "freqtrade_net_profit_pct": None,
            "net_profit_diff_pct": None,
            "jesse_max_drawdown_pct": jesse["max_drawdown_pct"],
            "freqtrade_max_drawdown_pct": None,
            "drawdown_diff_pct": None,
            "jesse_win_rate": jesse["win_rate"],
            "freqtrade_win_rate": None,
            "win_rate_diff": None,
        }
    return {
        "scope": scope,
        "symbol": symbol,
        "status": "ok",
        "error": "",
        "jesse_trades": jesse["trades_count"],
        "freqtrade_trades": freqtrade["trades_count"],
        "jesse_net_profit_pct": jesse["net_profit_pct"],
        "freqtrade_net_profit_pct": freqtrade["net_profit_pct"],
        "net_profit_diff_pct": freqtrade["net_profit_pct"] - jesse["net_profit_pct"],
        "jesse_max_drawdown_pct": jesse["max_drawdown_pct"],
        "freqtrade_max_drawdown_pct": freqtrade["max_drawdown_pct"],
        "drawdown_diff_pct": freqtrade["max_drawdown_pct"] - jesse["max_drawdown_pct"],
        "jesse_win_rate": jesse["win_rate"],
        "freqtrade_win_rate": freqtrade["win_rate"],
        "win_rate_diff": freqtrade["win_rate"] - jesse["win_rate"],
    }


def write_outputs(rows: list[dict]) -> None:
    outdir = TEMPLATE_DIR / "user_data" / "compare"
    outdir.mkdir(parents=True, exist_ok=True)

    json_path = outdir / "smc_fvg_pinbar_freqtrade_vs_jesse.json"
    csv_path = outdir / "smc_fvg_pinbar_freqtrade_vs_jesse.csv"
    md_path = outdir / "smc_fvg_pinbar_freqtrade_vs_jesse.md"

    json_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False))

    fieldnames = list(rows[0].keys()) if rows else []
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# SMC_FVG_PinBar Freqtrade vs Jesse",
        "",
        "| scope | symbol | jesse trades | freqtrade trades | jesse net % | freqtrade net % | diff % | jesse win | freqtrade win |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['scope']} | {row['symbol']} | {row['jesse_trades']} | {row['freqtrade_trades']} | "
            f"{row['jesse_net_profit_pct'] if row['jesse_net_profit_pct'] is not None else ''} | "
            f"{row['freqtrade_net_profit_pct'] if row['freqtrade_net_profit_pct'] is not None else ''} | "
            f"{row['net_profit_diff_pct'] if row['net_profit_diff_pct'] is not None else ''} | "
            f"{row['jesse_win_rate'] if row['jesse_win_rate'] is not None else ''} | "
            f"{row['freqtrade_win_rate'] if row['freqtrade_win_rate'] is not None else ''} |"
        )
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(json_path)
    print(csv_path)
    print(md_path)


def main() -> None:
    prepare_data()

    rows = []
    rows.append(
        compare_case(
            "BTC-USDT",
            BASELINE_WINDOW,
            TEMPLATE_DIR / "user_data" / "data" / "btc_baseline_binance",
            "btc_baseline",
        )
    )

    recent_datadir = TEMPLATE_DIR / "user_data" / "data" / "recent_selected_binance"
    for symbol in RECENT_SYMBOLS:
        rows.append(compare_case(symbol, RECENT_WINDOW, recent_datadir, "recent_selected"))

    write_outputs(rows)


if __name__ == "__main__":
    main()
