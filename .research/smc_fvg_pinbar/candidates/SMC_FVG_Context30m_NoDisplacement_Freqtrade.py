from __future__ import annotations

from pandas import DataFrame

from src.strategies.SMC_FVG_Context30m_Freqtrade import SMC_FVG_Context30m_Freqtrade


class SMC_FVG_Context30m_NoDisplacement_Freqtrade(SMC_FVG_Context30m_Freqtrade):
    """H027 candidate: evaluate only pin-bar and trend-body confirmations."""

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        long_displacement = dataframe["ft_long_entry_tag"].fillna("").str.startswith(
            "displacement|"
        )
        short_displacement = dataframe["ft_short_entry_tag"].fillna("").str.startswith(
            "displacement|"
        )
        dataframe["ft_long_entry_signal"] = (
            (dataframe["ft_long_entry_signal"] == 1) & ~long_displacement
        ).astype(int)
        dataframe["ft_short_entry_signal"] = (
            (dataframe["ft_short_entry_signal"] == 1) & ~short_displacement
        ).astype(int)
        return dataframe
