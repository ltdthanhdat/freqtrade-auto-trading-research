from __future__ import annotations

from pandas import DataFrame

from src.strategies.SMC_FVG_Context30m_Freqtrade import SMC_FVG_Context30m_Freqtrade


class SMC_FVG_Context30m_TrendAligned_Freqtrade(SMC_FVG_Context30m_Freqtrade):
    """H015 candidate: require the 1h EMA20 direction to match each side."""

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        bullish = (dataframe["close_1h"] > dataframe["ema20_1h"]) & (
            dataframe["ema20_slope_1h"] > 0
        )
        bearish = (dataframe["close_1h"] < dataframe["ema20_1h"]) & (
            dataframe["ema20_slope_1h"] < 0
        )
        dataframe["ft_long_entry_signal"] = (
            (dataframe["ft_long_entry_signal"] == 1) & bullish
        ).astype(int)
        dataframe["ft_short_entry_signal"] = (
            (dataframe["ft_short_entry_signal"] == 1) & bearish
        ).astype(int)
        return dataframe
