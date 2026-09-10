from __future__ import annotations

from pandas import DataFrame

from src.strategies.SMC_FVG_Context30m_Freqtrade import SMC_FVG_Context30m_Freqtrade


class SMC_FVG_Context30m_TrendSideOnly_Freqtrade(SMC_FVG_Context30m_Freqtrade):
    """H016 candidate: require only 1h price/EMA20 side alignment."""

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        bullish = dataframe["close_1h"] > dataframe["ema20_1h"]
        bearish = dataframe["close_1h"] < dataframe["ema20_1h"]
        dataframe["ft_long_entry_signal"] = (
            (dataframe["ft_long_entry_signal"] == 1) & bullish
        ).astype(int)
        dataframe["ft_short_entry_signal"] = (
            (dataframe["ft_short_entry_signal"] == 1) & bearish
        ).astype(int)
        return dataframe
