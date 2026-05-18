from __future__ import annotations

from pandas import DataFrame

from freqtrade.strategy import informative

from src.strategies.SMC_FVG_Confirmation_Freqtrade import FVG, SMC_FVG_Confirmation_Freqtrade


class SMC_FVG_Context30m_Freqtrade(SMC_FVG_Confirmation_Freqtrade):
    timeframe = "30m"
    startup_candle_count = 8

    @staticmethod
    def _annotate_active_bearish_fvg(dataframe: DataFrame) -> DataFrame:
        rows = dataframe.reset_index(drop=True).copy()
        active_bearish: list[FVG] = []
        has_bearish_fvg: list[int] = []

        for i in range(len(rows)):
            row = rows.iloc[i]
            current_fvg = None
            if i >= 3:
                candle_3 = rows.iloc[i - 3]
                candle_1 = rows.iloc[i - 1]
                if float(candle_3["low"]) > float(candle_1["high"]):
                    current_fvg = FVG(
                        top=float(candle_3["low"]),
                        bottom=float(candle_1["high"]),
                        is_bullish=False,
                        bar_index=i,
                    )

            if current_fvg is not None:
                active_bearish.append(current_fvg)

            current_high = float(row["high"])
            active_bearish = [fvg for fvg in active_bearish if current_high < fvg.top]
            has_bearish_fvg.append(1 if active_bearish else 0)

        rows["has_bearish_fvg"] = has_bearish_fvg
        return rows

    @informative("1h")
    def populate_indicators_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = dataframe.copy()
        dataframe["ema20"] = dataframe["close"].ewm(span=20, adjust=False).mean()
        dataframe["ema20_slope"] = dataframe["ema20"].diff()
        dataframe = super().populate_indicators(dataframe, metadata)
        return self._annotate_active_bearish_fvg(dataframe)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)

        long_base = dataframe["ft_long_entry_signal_1h"] == 1
        short_base = dataframe["ft_short_entry_signal_1h"] == 1
        extra_short = (
            (dataframe["ft_short_entry_signal"] == 1)
            & dataframe["ft_short_entry_tag"].str.startswith("displacement|")
            & (dataframe["close_1h"] < dataframe["ema20_1h"])
            & (dataframe["ema20_slope_1h"] < 0)
        )

        dataframe["ft_long_entry_signal"] = long_base.astype(int)
        dataframe["ft_short_entry_signal"] = (short_base | extra_short).astype(int)

        dataframe.loc[long_base, "ft_long_entry_stop"] = dataframe.loc[long_base, "ft_long_entry_stop_1h"]
        dataframe.loc[long_base, "ft_long_entry_tag"] = dataframe.loc[long_base, "ft_long_entry_tag_1h"]
        dataframe.loc[short_base, "ft_short_entry_stop"] = dataframe.loc[short_base, "ft_short_entry_stop_1h"]
        dataframe.loc[short_base, "ft_short_entry_tag"] = dataframe.loc[short_base, "ft_short_entry_tag_1h"]

        return dataframe
