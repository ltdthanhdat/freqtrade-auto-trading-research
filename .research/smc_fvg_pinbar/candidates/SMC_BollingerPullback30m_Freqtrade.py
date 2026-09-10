from __future__ import annotations

import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import informative

from src.strategies.SMC_FVG_Confirmation_Freqtrade import (
    SMC_FVG_Confirmation_Freqtrade,
)


class SMC_BollingerPullback30m_Freqtrade(SMC_FVG_Confirmation_Freqtrade):
    """H023 candidate: trend-aligned 30m Bollinger re-entry pullbacks."""

    timeframe = "30m"
    startup_candle_count = 100

    def __init__(self, config: dict):
        if "candle_type_def" not in config:
            config = {**config, "candle_type_def": "futures"}
        super().__init__(config)

    @property
    def protections(self) -> list[dict[str, int | str]]:
        return [{"method": "CooldownPeriod", "stop_duration_candles": 1}]

    @staticmethod
    def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gains = delta.clip(lower=0).rolling(period).mean()
        losses = (-delta.clip(upper=0)).rolling(period).mean()
        relative_strength = gains / losses.replace(0, pd.NA)
        return 100 - (100 / (1 + relative_strength))

    @informative("1h")
    def populate_indicators_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = dataframe.copy()
        dataframe["ema20"] = dataframe["close"].ewm(span=20, adjust=False).mean()
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = dataframe.copy()
        close = dataframe["close"]
        middle = close.rolling(20).mean()
        deviation = close.rolling(20).std(ddof=0)
        lower = middle - (2 * deviation)
        upper = middle + (2 * deviation)
        previous_close = close.shift(1)
        true_range = DataFrame(
            {
                "range": dataframe["high"] - dataframe["low"],
                "high_gap": (dataframe["high"] - previous_close).abs(),
                "low_gap": (dataframe["low"] - previous_close).abs(),
            }
        ).max(axis=1)
        atr = true_range.rolling(14).mean()
        rsi = self._rsi(close)

        long_signal = (
            (close.shift(1) < lower.shift(1))
            & (close >= lower)
            & (rsi < 50)
            & (dataframe["close_1h"] > dataframe["ema20_1h"])
        )
        short_signal = (
            (close.shift(1) > upper.shift(1))
            & (close <= upper)
            & (rsi > 50)
            & (dataframe["close_1h"] < dataframe["ema20_1h"])
        )
        long_stop = dataframe["low"] - atr
        short_stop = dataframe["high"] + atr

        dataframe["ft_long_entry_signal"] = long_signal.astype(int)
        dataframe["ft_short_entry_signal"] = short_signal.astype(int)
        dataframe["ft_long_entry_stop"] = long_stop
        dataframe["ft_short_entry_stop"] = short_stop
        dataframe["ft_long_entry_tag"] = ""
        dataframe["ft_short_entry_tag"] = ""
        dataframe.loc[long_signal, "ft_long_entry_tag"] = long_stop.loc[long_signal].map(
            lambda value: f"bb_pullback|{value:.10f}"
        )
        dataframe.loc[short_signal, "ft_short_entry_tag"] = short_stop.loc[short_signal].map(
            lambda value: f"bb_pullback|{value:.10f}"
        )
        return dataframe
