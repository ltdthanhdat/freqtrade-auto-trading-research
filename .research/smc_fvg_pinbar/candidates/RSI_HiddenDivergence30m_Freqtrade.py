from __future__ import annotations

import pandas as pd
from pandas import DataFrame

from RSI_Divergence30m_Freqtrade import (
    RSI_Divergence30m_Freqtrade,
    _strict_pivot,
    _wilder_rsi,
)


def _hidden_divergence_events(
    lows: pd.Series,
    highs: pd.Series,
    rsi: pd.Series,
    left: int = 3,
    right: int = 3,
) -> DataFrame:
    """Mark confirmed hidden RSI divergence with no future-row access."""
    if not (len(lows) == len(highs) == len(rsi)):
        raise ValueError("price and RSI series must have equal lengths")

    events = DataFrame(
        {
            "long_signal": 0,
            "short_signal": 0,
            "long_stop": float("nan"),
            "short_stop": float("nan"),
            "long_tag": "",
            "short_tag": "",
        },
        index=lows.index,
    )
    previous_low: tuple[float, float] | None = None
    previous_high: tuple[float, float] | None = None

    for current_index in range(len(lows)):
        pivot_index = current_index - right
        if pivot_index < left:
            continue
        pivot_rsi = rsi.iloc[pivot_index]
        if pd.isna(pivot_rsi):
            continue

        if _strict_pivot(lows, pivot_index, left, right, is_low=True):
            pivot_price = float(lows.iloc[pivot_index])
            pivot_value = float(pivot_rsi)
            if previous_low is not None:
                previous_price, previous_value = previous_low
                if pivot_price > previous_price and pivot_value < previous_value:
                    row = events.index[current_index]
                    events.at[row, "long_signal"] = 1
                    events.at[row, "long_stop"] = pivot_price
                    events.at[row, "long_tag"] = f"rsi_hidden_bullish|{pivot_price:.10f}"
            previous_low = (pivot_price, pivot_value)

        if _strict_pivot(highs, pivot_index, left, right, is_low=False):
            pivot_price = float(highs.iloc[pivot_index])
            pivot_value = float(pivot_rsi)
            if previous_high is not None:
                previous_price, previous_value = previous_high
                if pivot_price < previous_price and pivot_value > previous_value:
                    row = events.index[current_index]
                    events.at[row, "short_signal"] = 1
                    events.at[row, "short_stop"] = pivot_price
                    events.at[row, "short_tag"] = f"rsi_hidden_bearish|{pivot_price:.10f}"
            previous_high = (pivot_price, pivot_value)

    return events


class RSI_HiddenDivergence30m_Freqtrade(RSI_Divergence30m_Freqtrade):
    """H-RSI-03: hidden bullish/bearish RSI divergence on 30m pivots."""

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = dataframe.copy()
        rsi = _wilder_rsi(dataframe["close"], period=self.RSI_PERIOD)
        events = _hidden_divergence_events(
            dataframe["low"],
            dataframe["high"],
            rsi,
            left=self.PIVOT_LEFT,
            right=self.PIVOT_RIGHT,
        )
        dataframe["rsi"] = rsi
        for column in events.columns:
            dataframe[f"ft_{column}"] = events[column]
        dataframe["ft_long_entry_signal"] = dataframe["ft_long_signal"].astype(int)
        dataframe["ft_short_entry_signal"] = dataframe["ft_short_signal"].astype(int)
        dataframe["ft_long_entry_stop"] = dataframe["ft_long_stop"]
        dataframe["ft_short_entry_stop"] = dataframe["ft_short_stop"]
        dataframe["ft_long_entry_tag"] = dataframe["ft_long_tag"]
        dataframe["ft_short_entry_tag"] = dataframe["ft_short_tag"]
        return dataframe
