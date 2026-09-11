from __future__ import annotations

import pandas as pd
from pandas import DataFrame

from FuturesRiskBase_Freqtrade import FuturesRiskBase_Freqtrade


def _wilder_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Return RSI using Wilder's exponentially smoothed gains and losses."""
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    average_gain = gains.ewm(
        alpha=1 / period, adjust=False, min_periods=period
    ).mean()
    average_loss = losses.ewm(
        alpha=1 / period, adjust=False, min_periods=period
    ).mean()

    relative_strength = average_gain / average_loss
    rsi = 100 - (100 / (1 + relative_strength))
    no_losses = average_loss.eq(0)
    no_moves = no_losses & average_gain.eq(0)
    rsi = rsi.mask(no_losses & ~no_moves, 100.0)
    return rsi.mask(no_moves, 50.0)


def _strict_pivot(
    series: pd.Series,
    index: int,
    left: int,
    right: int,
    is_low: bool,
) -> bool:
    if index - left < 0 or index + right >= len(series):
        return False

    window = series.iloc[index - left : index + right + 1]
    center = series.iloc[index]
    if window.isna().any() or pd.isna(center):
        return False

    extreme = window.min() if is_low else window.max()
    return bool(center == extreme and (window == center).sum() == 1)


def _regular_divergence_events(
    lows: pd.Series,
    highs: pd.Series,
    rsi: pd.Series,
    left: int = 3,
    right: int = 3,
) -> DataFrame:
    """Mark confirmed regular RSI divergence without using future rows.

    A pivot at ``p`` is only evaluated on row ``p + right``.  The event uses
    the second confirmed price pivot as its structural stop.
    """
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
                if pivot_price < previous_price and pivot_value > previous_value:
                    row = events.index[current_index]
                    events.at[row, "long_signal"] = 1
                    events.at[row, "long_stop"] = pivot_price
                    events.at[row, "long_tag"] = f"rsi_regular_bullish|{pivot_price:.10f}"
            previous_low = (pivot_price, pivot_value)

        if _strict_pivot(highs, pivot_index, left, right, is_low=False):
            pivot_price = float(highs.iloc[pivot_index])
            pivot_value = float(pivot_rsi)
            if previous_high is not None:
                previous_price, previous_value = previous_high
                if pivot_price > previous_price and pivot_value < previous_value:
                    row = events.index[current_index]
                    events.at[row, "short_signal"] = 1
                    events.at[row, "short_stop"] = pivot_price
                    events.at[row, "short_tag"] = f"rsi_regular_bearish|{pivot_price:.10f}"
            previous_high = (pivot_price, pivot_value)

    return events


class RSI_Divergence30m_Freqtrade(FuturesRiskBase_Freqtrade):
    """H-RSI-01: regular RSI(14) divergence on confirmed 30m pivots.

    This first candidate intentionally has no trend, volume, or oscillator
    confirmation filter. Those are separate hypotheses so their effect stays
    attributable. Stops are the second confirmed price pivot.
    """

    timeframe = "30m"
    startup_candle_count = 64
    RSI_PERIOD = 14
    PIVOT_LEFT = 3
    PIVOT_RIGHT = 3

    def __init__(self, config: dict):
        if "candle_type_def" not in config:
            config = {**config, "candle_type_def": "futures"}
        super().__init__(config)

    @property
    def protections(self) -> list[dict[str, int | str]]:
        return [{"method": "CooldownPeriod", "stop_duration_candles": 1}]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = dataframe.copy()
        rsi = _wilder_rsi(dataframe["close"], period=self.RSI_PERIOD)
        events = _regular_divergence_events(
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
