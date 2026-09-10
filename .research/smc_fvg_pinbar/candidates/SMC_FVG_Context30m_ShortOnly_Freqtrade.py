from __future__ import annotations

from pandas import DataFrame

from src.strategies.SMC_FVG_Context30m_Freqtrade import SMC_FVG_Context30m_Freqtrade


class SMC_FVG_Context30m_ShortOnly_Freqtrade(SMC_FVG_Context30m_Freqtrade):
    """H025 candidate: test whether the observed long-side loss is regime-specific."""

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        dataframe["ft_long_entry_signal"] = 0
        return dataframe
