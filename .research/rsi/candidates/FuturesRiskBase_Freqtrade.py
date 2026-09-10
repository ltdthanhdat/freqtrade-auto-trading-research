from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
from freqtrade.exchange import timeframe_to_prev_date
from freqtrade.persistence import Order, Trade
from freqtrade.strategy import IStrategy, stoploss_from_absolute
from pandas import DataFrame


class FuturesRiskBase_Freqtrade(IStrategy):
    """Shared futures execution and risk callbacks for independent strategies."""

    INTERFACE_VERSION = 3

    can_short = True
    timeframe = "1h"
    startup_candle_count = 4
    process_only_new_candles = True

    minimal_roi = {"0": 100.0}
    stoploss = -0.99
    use_custom_stoploss = True
    use_custom_roi = True
    use_exit_signal = False
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    order_types = {
        "entry": "market",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    @staticmethod
    def _signal_tag(signal_kind: str, stop: float) -> str:
        return f"{signal_kind}|{stop:.10f}"

    @staticmethod
    def _parse_enter_tag(tag: str | None) -> tuple[Optional[str], Optional[float]]:
        if not tag:
            return None, None
        parts = tag.split("|", 1)
        if len(parts) != 2:
            return tag, None
        try:
            return parts[0], float(parts[1])
        except ValueError:
            return parts[0], None

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["ft_long_entry_signal"] == 1) & (dataframe["volume"] > 0),
            "enter_long",
        ] = 1
        dataframe.loc[
            (dataframe["ft_short_entry_signal"] == 1) & (dataframe["volume"] > 0),
            "enter_short",
        ] = 1

        dataframe["enter_tag"] = ""
        dataframe.loc[dataframe["ft_long_entry_signal"] == 1, "enter_tag"] = dataframe[
            "ft_long_entry_tag"
        ]
        dataframe.loc[dataframe["ft_short_entry_signal"] == 1, "enter_tag"] = dataframe[
            "ft_short_entry_tag"
        ]
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        return dataframe

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        configured_leverage = self.config.get("research_leverage")
        if configured_leverage == "max":
            return max_leverage
        if configured_leverage is None:
            return min(proposed_leverage, max_leverage)
        return min(float(configured_leverage), max_leverage)

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: float | None,
        max_stake: float,
        leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        current_candle = dataframe.iloc[-1].squeeze()

        stop_rate = (
            current_candle["ft_long_entry_stop"]
            if side == "long"
            else current_candle["ft_short_entry_stop"]
        )
        if pd.isna(stop_rate):
            return 0

        stop_rate = float(stop_rate)
        distance_ratio = abs(current_rate - stop_rate) / current_rate
        if distance_ratio <= 0:
            return 0

        risk_per_trade = self.config.get("research_risk_per_trade")
        capital_cap_ratio = self.config.get("research_capital_cap")
        if risk_per_trade is None or capital_cap_ratio is None:
            return min(proposed_stake, max_stake)
        if leverage <= 0:
            return 0

        total_stake = self.wallets.get_total_stake_amount()
        risk_stake = (total_stake * float(risk_per_trade)) / (distance_ratio * leverage)
        capital_cap = total_stake * float(capital_cap_ratio)
        return min(risk_stake, capital_cap, max_stake)

    def order_filled(self, pair: str, trade: Trade, order: Order, current_time: datetime, **kwargs) -> None:
        if order.ft_order_side != trade.entry_side or trade.nr_of_successful_entries != 1:
            return

        signal_kind, stop_rate = self._parse_enter_tag(trade.enter_tag)
        if stop_rate is None:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            trade_date = timeframe_to_prev_date(self.timeframe, trade.open_date_utc)
            trade_candle = dataframe.loc[dataframe["date"] == trade_date]
            if trade_candle.empty:
                return
            candle = trade_candle.squeeze()
            stop_rate = (
                candle["ft_long_entry_stop"]
                if trade.is_short is False
                else candle["ft_short_entry_stop"]
            )
            signal_kind = signal_kind or "unknown"

        if stop_rate is None or pd.isna(stop_rate):
            return

        stop_rate = float(stop_rate)
        risk_ratio = abs(trade.open_rate - stop_rate) / trade.open_rate
        target_roi = risk_ratio * trade.leverage
        trade.set_custom_data("research_signal_kind", signal_kind or "unknown")
        trade.set_custom_data("research_stop_rate", stop_rate)
        trade.set_custom_data("research_target_roi", target_roi)

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> float | None:
        stop_rate = trade.get_custom_data("research_stop_rate")
        if stop_rate is None:
            _, stop_rate = self._parse_enter_tag(trade.enter_tag)
        if stop_rate is None:
            return None
        return stoploss_from_absolute(
            float(stop_rate),
            current_rate=current_rate,
            is_short=trade.is_short,
            leverage=trade.leverage,
        )

    def custom_roi(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        trade_duration: int,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float | None:
        target_roi = trade.get_custom_data("research_target_roi")
        if target_roi is not None:
            return float(target_roi)

        _, stop_rate = self._parse_enter_tag(entry_tag)
        if stop_rate is None:
            return None
        return (abs(trade.open_rate - float(stop_rate)) / trade.open_rate) * trade.leverage
