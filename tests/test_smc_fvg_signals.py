import json
from pathlib import Path

import pandas as pd

from src.strategies.SMC_FVG_Confirmation_Freqtrade import SMC_FVG_Confirmation_Freqtrade
from src.strategies.SMC_FVG_Context30m_Freqtrade import SMC_FVG_Context30m_Freqtrade


def config():
    return json.loads(Path("config/config.futures.json").read_text())


def bullish_gap_dataframe(length=52, signal_index=None):
    rows = [
        {"open": 99.0, "high": 100.0, "low": 98.0, "close": 99.0, "volume": 1.0},
        {"open": 102.0, "high": 104.0, "low": 101.0, "close": 102.0, "volume": 1.0},
        {"open": 105.0, "high": 106.0, "low": 105.0, "close": 105.0, "volume": 1.0},
    ]
    rows.extend(
        {"open": 102.0, "high": 104.0, "low": 101.0, "close": 102.0, "volume": 1.0}
        for _ in range(length - len(rows))
    )
    if signal_index is not None:
        rows[signal_index] = {
            "open": 104.5,
            "high": 105.4,
            "low": 101.0,
            "close": 105.0,
            "volume": 1.0,
        }
    return pd.DataFrame(rows)


def bearish_gap_dataframe(length=52):
    rows = [
        {"open": 110.0, "high": 111.0, "low": 110.0, "close": 110.0, "volume": 1.0},
        {"open": 107.0, "high": 109.0, "low": 106.0, "close": 107.0, "volume": 1.0},
        {"open": 105.0, "high": 105.0, "low": 104.0, "close": 104.5, "volume": 1.0},
    ]
    rows.extend(
        {"open": 103.0, "high": 107.0, "low": 100.0, "close": 103.0, "volume": 1.0}
        for _ in range(length - len(rows))
    )
    return pd.DataFrame(rows)


def test_smc_family_advertises_sufficient_startup_and_bounded_fvg_age():
    assert SMC_FVG_Confirmation_Freqtrade.startup_candle_count >= 64
    assert SMC_FVG_Context30m_Freqtrade.startup_candle_count >= 64
    assert SMC_FVG_Confirmation_Freqtrade.FVG_MAX_AGE_CANDLES == 48
    assert SMC_FVG_Context30m_Freqtrade.FVG_MAX_AGE_CANDLES == 48


def test_bullish_fvg_entry_within_age_window_is_preserved():
    strategy = SMC_FVG_Confirmation_Freqtrade(config())
    result = strategy.populate_indicators(bullish_gap_dataframe(signal_index=10), {})

    assert result.loc[10, "ft_long_entry_signal"] == 1
    assert result.loc[10, "ft_long_entry_tag"].startswith("pin_bar|")
    assert result.loc[10, "ft_long_entry_stop"] == 100.0


def test_bullish_fvg_entry_after_age_window_is_not_emitted():
    strategy = SMC_FVG_Confirmation_Freqtrade(config())
    result = strategy.populate_indicators(bullish_gap_dataframe(signal_index=51), {})

    assert result.loc[51, "ft_long_entry_signal"] == 0
    assert result.loc[51, "ft_long_entry_tag"] == ""
    assert pd.isna(result.loc[51, "ft_long_entry_stop"])


def test_context_informative_bearish_fvg_expires_but_fresh_gap_remains_active():
    old_result = SMC_FVG_Context30m_Freqtrade._annotate_active_bearish_fvg(
        bearish_gap_dataframe(length=52)
    )
    fresh_result = SMC_FVG_Context30m_Freqtrade._annotate_active_bearish_fvg(
        bearish_gap_dataframe(length=12)
    )

    assert old_result.loc[3, "has_bearish_fvg"] == 1
    assert old_result.loc[51, "has_bearish_fvg"] == 0
    assert fresh_result.loc[11, "has_bearish_fvg"] == 1
