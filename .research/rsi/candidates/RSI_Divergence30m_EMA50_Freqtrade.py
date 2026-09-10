from __future__ import annotations

import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import informative

from RSI_Divergence30m_Freqtrade import RSI_Divergence30m_Freqtrade


def _apply_ema50_filter(
    events: DataFrame,
    close_1h: pd.Series,
    ema50_1h: pd.Series,
) -> DataFrame:
    """Keep long events above and short events below the 1h EMA50."""
    filtered = events.copy()
    long_aligned = close_1h > ema50_1h
    short_aligned = close_1h < ema50_1h

    long_remove = (filtered["long_signal"] == 1) & ~long_aligned
    short_remove = (filtered["short_signal"] == 1) & ~short_aligned
    filtered.loc[long_remove, "long_signal"] = 0
    filtered.loc[long_remove, "long_stop"] = float("nan")
    filtered.loc[long_remove, "long_tag"] = ""
    filtered.loc[short_remove, "short_signal"] = 0
    filtered.loc[short_remove, "short_stop"] = float("nan")
    filtered.loc[short_remove, "short_tag"] = ""
    return filtered


class RSI_Divergence30m_EMA50_Freqtrade(RSI_Divergence30m_Freqtrade):
    """H-RSI-02: H-RSI-01 plus a 1h EMA50 direction filter."""

    @informative("1h")
    def populate_indicators_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = dataframe.copy()
        dataframe["ema50"] = dataframe["close"].ewm(span=50, adjust=False).mean()
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        events = dataframe[
            [
                "ft_long_signal",
                "ft_short_signal",
                "ft_long_stop",
                "ft_short_stop",
                "ft_long_tag",
                "ft_short_tag",
            ]
        ].rename(
            columns={
                "ft_long_signal": "long_signal",
                "ft_short_signal": "short_signal",
                "ft_long_stop": "long_stop",
                "ft_short_stop": "short_stop",
                "ft_long_tag": "long_tag",
                "ft_short_tag": "short_tag",
            }
        )
        filtered = _apply_ema50_filter(
            events,
            dataframe["close_1h"],
            dataframe["ema50_1h"],
        )
        for column in filtered.columns:
            dataframe[f"ft_{column}"] = filtered[column]
        dataframe["ft_long_entry_signal"] = dataframe["ft_long_signal"].astype(int)
        dataframe["ft_short_entry_signal"] = dataframe["ft_short_signal"].astype(int)
        dataframe["ft_long_entry_stop"] = dataframe["ft_long_stop"]
        dataframe["ft_short_entry_stop"] = dataframe["ft_short_stop"]
        dataframe["ft_long_entry_tag"] = dataframe["ft_long_tag"]
        dataframe["ft_short_entry_tag"] = dataframe["ft_short_tag"]
        return dataframe
