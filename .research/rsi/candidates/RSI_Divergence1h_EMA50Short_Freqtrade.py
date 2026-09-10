from __future__ import annotations

from pandas import DataFrame

from RSI_Divergence30m_EMA50_Freqtrade import RSI_Divergence30m_EMA50_Freqtrade


def _disable_long_events(events: DataFrame) -> DataFrame:
    filtered = events.copy()
    filtered["long_signal"] = 0
    filtered["long_stop"] = float("nan")
    filtered["long_tag"] = ""
    return filtered


class RSI_Divergence1h_EMA50Short_Freqtrade(RSI_Divergence30m_EMA50_Freqtrade):
    """H-RSI-06: H-RSI-05 with the long direction disabled."""

    timeframe = "1h"

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
        filtered = _disable_long_events(events)
        for column in filtered.columns:
            dataframe[f"ft_{column}"] = filtered[column]
        dataframe["ft_long_entry_signal"] = 0
        dataframe["ft_long_entry_stop"] = float("nan")
        dataframe["ft_long_entry_tag"] = ""
        dataframe["ft_short_entry_signal"] = dataframe["ft_short_signal"].astype(int)
        dataframe["ft_short_entry_stop"] = dataframe["ft_short_stop"]
        dataframe["ft_short_entry_tag"] = dataframe["ft_short_tag"]
        return dataframe
