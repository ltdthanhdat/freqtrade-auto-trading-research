from __future__ import annotations

from pandas import DataFrame

from freqtrade.strategy import informative

from src.strategies.SMC_FVG_Confirmation_Freqtrade import (
    SMC_FVG_Confirmation_Freqtrade,
)


class SMC_FVG_Context30m_BreakoutRetest_Freqtrade(
    SMC_FVG_Confirmation_Freqtrade
):
    """H022 candidate: 1h structure breakout followed by a 30m retest."""

    timeframe = "30m"
    startup_candle_count = 80

    def __init__(self, config: dict):
        if "candle_type_def" not in config:
            config = {**config, "candle_type_def": "futures"}
        super().__init__(config)

    @property
    def protections(self) -> list[dict[str, int | str]]:
        return [{"method": "CooldownPeriod", "stop_duration_candles": 1}]

    @staticmethod
    def _active_breakout_levels(dataframe: DataFrame) -> DataFrame:
        rows = dataframe.reset_index(drop=True).copy()
        long_levels: list[float | None] = []
        short_levels: list[float | None] = []
        long_ages: list[int] = []
        short_ages: list[int] = []
        long_level: float | None = None
        short_level: float | None = None
        long_age = 0
        short_age = 0

        for row in rows.itertuples(index=False):
            previous_high = getattr(row, "previous_high")
            previous_low = getattr(row, "previous_low")
            close = float(getattr(row, "close"))

            if previous_high == previous_high and close > float(previous_high):
                long_level = float(previous_high)
                long_age = 0
            elif long_level is not None:
                long_age += 1
                if long_age > 6:
                    long_level = None
                    long_age = 0

            if previous_low == previous_low and close < float(previous_low):
                short_level = float(previous_low)
                short_age = 0
            elif short_level is not None:
                short_age += 1
                if short_age > 6:
                    short_level = None
                    short_age = 0

            long_levels.append(long_level)
            short_levels.append(short_level)
            long_ages.append(long_age)
            short_ages.append(short_age)

        rows["active_long_level"] = long_levels
        rows["active_short_level"] = short_levels
        rows["active_long_age"] = long_ages
        rows["active_short_age"] = short_ages
        return rows

    @informative("1h")
    def populate_indicators_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = dataframe.copy()
        dataframe["ema20"] = dataframe["close"].ewm(span=20, adjust=False).mean()
        dataframe["ema20_slope"] = dataframe["ema20"].diff()
        dataframe["previous_high"] = dataframe["high"].rolling(20).max().shift(1)
        dataframe["previous_low"] = dataframe["low"].rolling(20).min().shift(1)
        previous_close = dataframe["close"].shift(1)
        true_range = DataFrame(
            {
                "range": dataframe["high"] - dataframe["low"],
                "high_gap": (dataframe["high"] - previous_close).abs(),
                "low_gap": (dataframe["low"] - previous_close).abs(),
            }
        ).max(axis=1)
        dataframe["atr14"] = true_range.rolling(14).mean()
        return self._active_breakout_levels(dataframe)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)

        long_level = dataframe["active_long_level_1h"]
        short_level = dataframe["active_short_level_1h"]
        bullish = (
            (dataframe["close_1h"] > dataframe["ema20_1h"])
            & (dataframe["ema20_slope_1h"] > 0)
        )
        bearish = (
            (dataframe["close_1h"] < dataframe["ema20_1h"])
            & (dataframe["ema20_slope_1h"] < 0)
        )
        long_retest = (
            long_level.notna()
            & (dataframe["low"] <= long_level * 1.002)
            & (dataframe["close"] > long_level)
        )
        short_retest = (
            short_level.notna()
            & (dataframe["high"] >= short_level * 0.998)
            & (dataframe["close"] < short_level)
        )
        long_retest = long_retest.fillna(False)
        short_retest = short_retest.fillna(False)
        long_signal = bullish & long_retest & ~long_retest.shift(1, fill_value=False)
        short_signal = bearish & short_retest & ~short_retest.shift(1, fill_value=False)
        long_stop = long_level - dataframe["atr14_1h"]
        short_stop = short_level + dataframe["atr14_1h"]

        dataframe["ft_long_entry_signal"] = long_signal.astype(int)
        dataframe["ft_short_entry_signal"] = short_signal.astype(int)
        dataframe["ft_long_entry_stop"] = long_stop
        dataframe["ft_short_entry_stop"] = short_stop
        dataframe["ft_long_entry_tag"] = ""
        dataframe["ft_short_entry_tag"] = ""
        dataframe.loc[long_signal, "ft_long_entry_tag"] = "breakout_retest|" + long_stop.loc[
            long_signal
        ].map(lambda value: f"{value:.10f}")
        dataframe.loc[short_signal, "ft_short_entry_tag"] = "breakout_retest|" + short_stop.loc[
            short_signal
        ].map(lambda value: f"{value:.10f}")
        return dataframe
