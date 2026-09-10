from __future__ import annotations

from pandas import DataFrame
from freqtrade.strategy import informative

from src.strategies.SMC_FVG_Context30m_Freqtrade import SMC_FVG_Context30m_Freqtrade


class SMC_FVG_Context30m_BTCRegime_Freqtrade(SMC_FVG_Context30m_Freqtrade):
    """H026 candidate: align each side with the broad BTC 1h regime."""

    @informative("1h", "BTC/USDT:USDT", candle_type="futures")
    def populate_indicators_btc_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = dataframe.copy()
        dataframe["ema50"] = dataframe["close"].ewm(span=50, adjust=False).mean()
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        btc_bull = dataframe["btc_usdt_close_1h"] > dataframe["btc_usdt_ema50_1h"]
        btc_bear = dataframe["btc_usdt_close_1h"] < dataframe["btc_usdt_ema50_1h"]
        dataframe["ft_long_entry_signal"] = (
            (dataframe["ft_long_entry_signal"] == 1) & btc_bull
        ).astype(int)
        dataframe["ft_short_entry_signal"] = (
            (dataframe["ft_short_entry_signal"] == 1) & btc_bear
        ).astype(int)
        return dataframe
