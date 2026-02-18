"""
Strategy using 2 MA lines (50 and 200) for trading
- Golden Cross: MA50 crosses above MA200 -> Buy
- Death Cross: MA50 crosses below MA200 -> Sell
"""

from datetime import datetime
from typing import Optional

import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IStrategy

import talib.abstract as ta
from technical import qtpylib


class MA50_200_Strategy(IStrategy):
    """
    Strategy using MA50 and MA200 cross for trading
    """

    INTERFACE_VERSION = 3

    # Minimal ROI designed for the strategy.
    # This attribute will be overridden if the config file contains "minimal_roi".
    minimal_roi = {
        "60": 0.01,
        "30": 0.02,
        "0": 0.04,
    }

    # Optimal stoploss designed for the strategy.
    # This attribute will be overridden if the config file contains "stoploss".
    stoploss = -0.05  # 5% stoploss

    # Optimal timeframe for the strategy.
    timeframe = "5m"

    # Run "populate_indicators" only for new candle.
    process_only_new_candles = True

    # These values can be overridden in the config.
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 200  # Need 200 candles to calculate MA200

    # Optional order type mapping.
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    # Optional order time in force.
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    plot_config = {
        "main_plot": {
            "ma50": {"color": "blue"},
            "ma200": {"color": "red"},
        },
        "subplots": {
            "MACD": {
                "macd": {"color": "blue"},
                "macdsignal": {"color": "red"},
            },
        },
    }

    def informative_pairs(self):
        """
        Define additional, informative pair/interval combinations to be cached from the exchange.
        These pair/interval combinations are non-tradeable, unless they are part
        of the whitelist as well.
        For more information, please consult the documentation
        https://www.freqtrade.io/en/latest/freqtrade-strategy-utils/#informative-pairs
        :return: List of tuples in the format (pair, interval)
            Sample: [("ETH/USDT", "5m"), ("BTC/USDT", "15m")]
        """
        return []

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds several different TA indicators to the given DataFrame

        Performance Note: For the best performance be frugal on the number of indicators
        you are using. Let uncomment only the indicator you are using in your strategies
        or your hyperopt configuration, otherwise you will waste your CPU and memory.
        :param dataframe: Dataframe with data from the exchange
        :param metadata: Additional information, like the currently traded pair
        :return: a Dataframe with all mandatory indicators for the strategies
        """

        # MA50 and MA200
        dataframe["ma50"] = ta.SMA(dataframe, timeperiod=50)
        dataframe["ma200"] = ta.SMA(dataframe, timeperiod=200)

        # RSI for additional filter
        dataframe["rsi"] = ta.RSI(dataframe)

        # Volume for confirmation
        dataframe["volume_mean"] = dataframe["volume"].rolling(window=20).mean()

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        :param dataframe: DataFrame
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with entry columns populated
        """
        dataframe.loc[
            (
                # Golden Cross: MA50 crosses above MA200
                (qtpylib.crossed_above(dataframe["ma50"], dataframe["ma200"]))
                # RSI not overbought (optional filter)
                & (dataframe["rsi"] < 70)
                # Volume is sufficient
                & (dataframe["volume"] > dataframe["volume_mean"] * 0.8)
                # Ensure we have data
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        :param dataframe: DataFrame
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with exit columns populated
        """
        dataframe.loc[
            (
                # Death Cross: MA50 crosses below MA200
                (qtpylib.crossed_below(dataframe["ma50"], dataframe["ma200"]))
                # Or RSI overbought
                | (dataframe["rsi"] > 80)
                # Ensure we have data
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1

        return dataframe
