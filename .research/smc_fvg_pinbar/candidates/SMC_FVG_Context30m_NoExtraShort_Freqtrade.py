from __future__ import annotations

from pandas import DataFrame

from src.strategies.SMC_FVG_Context30m_Freqtrade import SMC_FVG_Context30m_Freqtrade


class SMC_FVG_Context30m_NoExtraShort_Freqtrade(SMC_FVG_Context30m_Freqtrade):
    """H014 candidate: retain only the 1h-confirmed short entries."""

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        short_base = dataframe["ft_short_entry_signal_1h"] == 1
        dataframe["ft_short_entry_signal"] = short_base.astype(int)
        return dataframe
