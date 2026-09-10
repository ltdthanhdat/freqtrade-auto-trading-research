from __future__ import annotations

from pandas import DataFrame

from src.strategies.SMC_FVG_Context30m_Freqtrade import SMC_FVG_Context30m_Freqtrade


class SMC_FVG_Context30m_SymmetricDisplacement_Freqtrade(
    SMC_FVG_Context30m_Freqtrade
):
    """H020 candidate: add the bullish counterpart to the existing extra short branch."""

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)

        long_base = dataframe["ft_long_entry_signal_1h"] == 1
        extra_long = (
            (dataframe["ft_long_entry_signal"] == 1)
            & dataframe["ft_long_entry_tag"].str.startswith("displacement|")
            & (dataframe["close_1h"] > dataframe["ema20_1h"])
            & (dataframe["ema20_slope_1h"] > 0)
        )
        dataframe["ft_long_entry_signal"] = (long_base | extra_long).astype(int)
        dataframe.loc[long_base, "ft_long_entry_stop"] = dataframe.loc[
            long_base, "ft_long_entry_stop_1h"
        ]
        dataframe.loc[long_base, "ft_long_entry_tag"] = dataframe.loc[
            long_base, "ft_long_entry_tag_1h"
        ]
        return dataframe
