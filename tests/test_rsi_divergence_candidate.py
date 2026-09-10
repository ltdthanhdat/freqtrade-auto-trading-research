from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


CANDIDATE_DIR = (
    Path(__file__).resolve().parents[1]
    / ".research"
    / "smc_fvg_pinbar"
    / "candidates"
)
sys.path.insert(0, str(CANDIDATE_DIR))

from RSI_Divergence30m_Freqtrade import (  # noqa: E402
    _regular_divergence_events,
    _wilder_rsi,
)


def test_ema50_filter_keeps_only_direction_aligned_events() -> None:
    from RSI_Divergence30m_EMA50_Freqtrade import _apply_ema50_filter

    events = pd.DataFrame(
        {
            "long_signal": [1, 1, 0],
            "short_signal": [1, 0, 1],
            "long_stop": [90.0, 91.0, float("nan")],
            "short_stop": [110.0, float("nan"), 109.0],
            "long_tag": ["long|90", "long|91", ""],
            "short_tag": ["short|110", "", "short|109"],
        }
    )

    filtered = _apply_ema50_filter(
        events,
        close_1h=pd.Series([105.0, 95.0, 105.0]),
        ema50_1h=pd.Series([100.0, 100.0, 100.0]),
    )

    assert filtered.loc[0, "long_signal"] == 1
    assert filtered.loc[0, "short_signal"] == 0
    assert filtered.loc[0, "short_tag"] == ""
    assert filtered.loc[1, "long_signal"] == 0
    assert filtered.loc[1, "long_stop"] != filtered.loc[1, "long_stop"]
    assert filtered.loc[2, "short_signal"] == 0


def test_hidden_divergence_uses_higher_low_or_lower_high_with_opposite_rsi() -> None:
    from RSI_HiddenDivergence30m_Freqtrade import _hidden_divergence_events

    lows = pd.Series([10, 9, 8, 7, 8, 9, 10, 9, 9, 8, 9, 10, 11, 12, 13], dtype=float)
    highs = pd.Series([10, 11, 12, 13, 12, 11, 10, 11, 10, 12, 10, 11, 10, 9, 8], dtype=float)
    bullish_rsi = pd.Series([50, 45, 42, 40, 45, 50, 55, 50, 48, 30, 50, 55, 60, 65, 70], dtype=float)
    bearish_rsi = bullish_rsi.copy()
    bearish_rsi.iloc[3] = 60
    bearish_rsi.iloc[9] = 70

    bullish = _hidden_divergence_events(lows, highs, bullish_rsi, left=3, right=3)
    bearish = _hidden_divergence_events(lows, highs, bearish_rsi, left=3, right=3)

    assert bullish.loc[12, "long_signal"] == 1
    assert bullish.loc[12, "long_stop"] == 8
    assert bearish.loc[12, "short_signal"] == 1
    assert bearish.loc[12, "short_stop"] == 12


def test_short_only_filter_clears_long_entry_state() -> None:
    from RSI_Divergence1h_EMA50Short_Freqtrade import _disable_long_events

    events = pd.DataFrame(
        {
            "long_signal": [1, 0],
            "short_signal": [0, 1],
            "long_stop": [90.0, float("nan")],
            "short_stop": [float("nan"), 110.0],
            "long_tag": ["long|90", ""],
            "short_tag": ["", "short|110"],
        }
    )

    filtered = _disable_long_events(events)

    assert filtered["long_signal"].sum() == 0
    assert filtered["long_stop"].isna().all()
    assert filtered["long_tag"].eq("").all()
    assert filtered.loc[1, "short_signal"] == 1
    assert filtered.loc[1, "short_stop"] == 110


def test_four_hour_bear_filter_keeps_only_short_events_below_ema50() -> None:
    from RSI_Divergence1h_EMA50Short_4hRegime_Freqtrade import (
        _apply_4h_bear_filter,
    )

    events = pd.DataFrame(
        {
            "long_signal": [0, 0],
            "short_signal": [1, 1],
            "long_stop": [float("nan"), float("nan")],
            "short_stop": [110.0, 111.0],
            "long_tag": ["", ""],
            "short_tag": ["short|110", "short|111"],
        }
    )

    filtered = _apply_4h_bear_filter(
        events,
        close_4h=pd.Series([95.0, 105.0]),
        ema50_4h=pd.Series([100.0, 100.0]),
    )

    assert filtered.loc[0, "short_signal"] == 1
    assert filtered.loc[0, "short_stop"] == 110.0
    assert filtered.loc[1, "short_signal"] == 0
    assert pd.isna(filtered.loc[1, "short_stop"])
    assert filtered.loc[1, "short_tag"] == ""


def test_regular_divergence_waits_for_pivot_confirmation_and_sets_pivot_stop() -> None:
    lows = pd.Series([10, 9, 8, 7, 8, 9, 10, 9, 8, 6, 8, 9, 10, 11, 12], dtype=float)
    highs = pd.Series([10, 11, 12, 13, 12, 11, 10, 11, 12, 15, 12, 11, 10, 9, 8], dtype=float)
    rsi = pd.Series([50, 45, 35, 30, 45, 50, 55, 50, 45, 40, 50, 55, 60, 65, 70], dtype=float)

    events = _regular_divergence_events(lows, highs, rsi, left=3, right=3)

    assert events.loc[:11, "long_signal"].sum() == 0
    assert events.loc[12, "long_signal"] == 1
    assert events.loc[12, "long_stop"] == 6

    bearish_rsi = rsi.copy()
    bearish_rsi.iloc[3] = 70
    bearish_rsi.iloc[9] = 60
    bearish_events = _regular_divergence_events(lows, highs, bearish_rsi, left=3, right=3)
    assert bearish_events.loc[12, "short_signal"] == 1
    assert bearish_events.loc[12, "short_stop"] == 15


def test_future_candles_after_confirmation_do_not_change_prior_events() -> None:
    lows = pd.Series([10, 9, 8, 7, 8, 9, 10, 9, 8, 6, 8, 9, 10, 11, 12], dtype=float)
    highs = pd.Series([10, 11, 12, 13, 12, 11, 10, 11, 12, 15, 12, 11, 10, 9, 8], dtype=float)
    rsi = pd.Series([50, 45, 35, 30, 45, 50, 55, 50, 45, 40, 50, 55, 60, 65, 70], dtype=float)

    baseline = _regular_divergence_events(lows, highs, rsi, left=3, right=3)
    changed_future = _regular_divergence_events(
        lows,
        highs.mask(highs.index >= 13, 999),
        rsi.mask(rsi.index >= 13, 1),
        left=3,
        right=3,
    )

    pd.testing.assert_frame_equal(baseline.loc[:12], changed_future.loc[:12])


def test_wilder_rsi_is_bounded_and_has_a_warmup() -> None:
    close = pd.Series(range(20), dtype=float)

    rsi = _wilder_rsi(close, period=5)

    assert rsi.iloc[:5].isna().all()
    assert (rsi.iloc[5:] <= 100).all()
    assert (rsi.iloc[5:] >= 0).all()
    assert rsi.iloc[-1] == 100
