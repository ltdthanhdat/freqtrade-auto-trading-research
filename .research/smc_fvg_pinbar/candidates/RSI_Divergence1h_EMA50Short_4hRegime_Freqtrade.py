from __future__ import annotations

import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import informative

from RSI_Divergence1h_EMA50Short_Freqtrade import (
    RSI_Divergence1h_EMA50Short_Freqtrade,
)


def _apply_4h_bear_filter(
    events: DataFrame,
    close_4h: pd.Series,
    ema50_4h: pd.Series,
) -> DataFrame:
    """Keep short divergence events only in a bearish 4h EMA50 regime."""
    filtered = events.copy()
    short_remove = (filtered["short_signal"] == 1) & ~(close_4h < ema50_4h)
    filtered.loc[short_remove, "short_signal"] = 0
    filtered.loc[short_remove, "short_stop"] = float("nan")
    filtered.loc[short_remove, "short_tag"] = ""
    return filtered


class RSI_Divergence1h_EMA50Short_4hRegime_Freqtrade(
    RSI_Divergence1h_EMA50Short_Freqtrade
):
    """H-RSI-07: H-RSI-06 with a bearish 4h EMA50 regime filter."""

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
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
        filtered = _apply_4h_bear_filter(
            events,
            dataframe["close_4h"],
            dataframe["ema50_4h"],
        )
        for column in filtered.columns:
            dataframe[f"ft_{column}"] = filtered[column]
        dataframe["ft_long_entry_signal"] = 0
        dataframe["ft_long_entry_stop"] = float("nan")
        dataframe["ft_long_entry_tag"] = ""
        dataframe["ft_short_entry_signal"] = dataframe["ft_short_signal"].astype(int)
        dataframe["ft_short_entry_stop"] = dataframe["ft_short_stop"]
        dataframe["ft_short_entry_tag"] = dataframe["ft_short_tag"]
        return dataframe
