from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
from freqtrade.exchange import timeframe_to_prev_date
from freqtrade.persistence import Order, Trade
from freqtrade.strategy import IStrategy, stoploss_from_absolute
from pandas import DataFrame


class FVG:
    def __init__(self, top: float, bottom: float, is_bullish: bool, bar_index: int) -> None:
        self.top = top
        self.bottom = bottom
        self.is_bullish = is_bullish
        self.bar_index = bar_index


class SMC_FVG_Confirmation_Freqtrade(IStrategy):
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

    PIN_BAR_BODY_RATIO = 0.33
    PIN_BAR_WICK_TO_BODY = 2.25
    PIN_BAR_CLOSE_EXTREME_RATIO = 0.30
    FVG_RETRACE_RATIO = 0.45
    FVG_CONFIRM_RATIO = 0.55

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

    def _is_pin_bar(self, row: pd.Series, is_bullish: bool) -> bool:
        open_price = float(row["open"])
        close_price = float(row["close"])
        high_price = float(row["high"])
        low_price = float(row["low"])

        body = abs(close_price - open_price)
        upper_wick = high_price - max(close_price, open_price)
        lower_wick = min(close_price, open_price) - low_price
        total_range = high_price - low_price

        if total_range == 0:
            return False

        if is_bullish:
            close_near_high = close_price >= high_price - total_range * self.PIN_BAR_CLOSE_EXTREME_RATIO
            body_in_upper_range = min(open_price, close_price) >= low_price + total_range * (
                1 - self.PIN_BAR_BODY_RATIO
            )
            return (
                close_price >= open_price
                and lower_wick >= self.PIN_BAR_WICK_TO_BODY * body
                and upper_wick <= body
                and body <= total_range * self.PIN_BAR_BODY_RATIO
                and close_near_high
                and body_in_upper_range
            )

        close_near_low = close_price <= low_price + total_range * self.PIN_BAR_CLOSE_EXTREME_RATIO
        body_in_lower_range = max(open_price, close_price) <= high_price - total_range * (
            1 - self.PIN_BAR_BODY_RATIO
        )
        return (
            close_price <= open_price
            and upper_wick >= self.PIN_BAR_WICK_TO_BODY * body
            and lower_wick <= body
            and body <= total_range * self.PIN_BAR_BODY_RATIO
            and close_near_low
            and body_in_lower_range
        )

    @staticmethod
    def _is_trend_body(row: pd.Series, is_bullish: bool) -> bool:
        open_price = float(row["open"])
        close_price = float(row["close"])
        high_price = float(row["high"])
        low_price = float(row["low"])

        body = abs(close_price - open_price)
        upper_wick = high_price - max(close_price, open_price)
        lower_wick = min(close_price, open_price) - low_price
        total_range = high_price - low_price

        if total_range == 0:
            return False

        body_ratio = body / total_range
        if is_bullish:
            return (
                close_price > open_price
                and body_ratio >= 0.55
                and close_price >= high_price - total_range * 0.15
                and upper_wick <= total_range * 0.15
                and lower_wick <= total_range * 0.2
            )

        return (
            close_price < open_price
            and body_ratio >= 0.55
            and close_price <= low_price + total_range * 0.15
            and lower_wick <= total_range * 0.15
            and upper_wick <= total_range * 0.2
        )

    @staticmethod
    def _is_displacement_break(row: pd.Series, prev_row: pd.Series, is_bullish: bool) -> bool:
        open_price = float(row["open"])
        close_price = float(row["close"])
        high_price = float(row["high"])
        low_price = float(row["low"])

        prev_high = float(prev_row["high"])
        prev_low = float(prev_row["low"])

        body = abs(close_price - open_price)
        total_range = high_price - low_price
        if total_range == 0:
            return False

        body_ratio = body / total_range
        if is_bullish:
            return (
                close_price > open_price
                and body_ratio >= 0.6
                and close_price > prev_high
                and close_price >= high_price - total_range * 0.2
            )

        return (
            close_price < open_price
            and body_ratio >= 0.6
            and close_price < prev_low
            and close_price <= low_price + total_range * 0.2
        )

    def _entry_signal_kind(self, row: pd.Series, prev_row: pd.Series, is_bullish: bool) -> Optional[str]:
        if self._is_pin_bar(row, is_bullish):
            return "pin_bar"
        if self._is_trend_body(row, is_bullish):
            return "trend_body"
        if self._is_displacement_break(row, prev_row, is_bullish):
            return "displacement"
        return None

    @staticmethod
    def _signal_matches_fvg(row: pd.Series, fvg: FVG, signal_kind: str, is_bullish: bool) -> bool:
        high_price = float(row["high"])
        low_price = float(row["low"])
        close_price = float(row["close"])

        if is_bullish != fvg.is_bullish:
            return False

        overlaps_fvg = high_price >= fvg.bottom and low_price <= fvg.top
        if not overlaps_fvg:
            return False

        if signal_kind not in {"trend_body", "displacement"}:
            return True

        fvg_height = fvg.top - fvg.bottom
        if fvg_height <= 0:
            return False

        if is_bullish:
            return (
                low_price <= fvg.bottom + fvg_height * SMC_FVG_Confirmation_Freqtrade.FVG_RETRACE_RATIO
                and close_price >= fvg.bottom + fvg_height * SMC_FVG_Confirmation_Freqtrade.FVG_CONFIRM_RATIO
            )

        return (
            high_price >= fvg.top - fvg_height * SMC_FVG_Confirmation_Freqtrade.FVG_RETRACE_RATIO
            and close_price <= fvg.bottom + fvg_height * SMC_FVG_Confirmation_Freqtrade.FVG_RETRACE_RATIO
        )

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = dataframe.copy()
        dataframe["ft_long_signal"] = 0
        dataframe["ft_short_signal"] = 0
        dataframe["ft_long_stop"] = pd.NA
        dataframe["ft_short_stop"] = pd.NA
        dataframe["ft_long_tag"] = ""
        dataframe["ft_short_tag"] = ""

        active_bullish: list[FVG] = []
        active_bearish: list[FVG] = []

        rows = dataframe.reset_index(drop=True)
        for i in range(len(rows)):
            row = rows.iloc[i]

            current_fvg: Optional[FVG] = None
            if i >= 3:
                candle_3 = rows.iloc[i - 3]
                candle_1 = rows.iloc[i - 1]
                high_3 = float(candle_3["high"])
                low_3 = float(candle_3["low"])
                high_1 = float(candle_1["high"])
                low_1 = float(candle_1["low"])

                if high_3 < low_1:
                    current_fvg = FVG(top=low_1, bottom=high_3, is_bullish=True, bar_index=i)
                elif low_3 > high_1:
                    current_fvg = FVG(top=low_3, bottom=high_1, is_bullish=False, bar_index=i)

            if current_fvg is not None:
                if current_fvg.is_bullish:
                    active_bullish.append(current_fvg)
                else:
                    active_bearish.append(current_fvg)

            current_low = float(row["low"])
            current_high = float(row["high"])
            active_bullish = [fvg for fvg in active_bullish if current_low > fvg.bottom]
            active_bearish = [fvg for fvg in active_bearish if current_high < fvg.top]

            if i == 0:
                continue

            prev_row = rows.iloc[i - 1]

            long_kind = self._entry_signal_kind(row, prev_row, is_bullish=True)
            if long_kind is not None:
                for fvg in reversed(active_bullish):
                    if self._signal_matches_fvg(row, fvg, long_kind, is_bullish=True):
                        rows.at[i, "ft_long_signal"] = 1
                        rows.at[i, "ft_long_stop"] = fvg.bottom
                        rows.at[i, "ft_long_tag"] = self._signal_tag(long_kind, fvg.bottom)
                        break

            short_kind = self._entry_signal_kind(row, prev_row, is_bullish=False)
            if short_kind is not None:
                for fvg in reversed(active_bearish):
                    if self._signal_matches_fvg(row, fvg, short_kind, is_bullish=False):
                        rows.at[i, "ft_short_signal"] = 1
                        rows.at[i, "ft_short_stop"] = fvg.top
                        rows.at[i, "ft_short_tag"] = self._signal_tag(short_kind, fvg.top)
                        break

        rows["ft_long_entry_signal"] = rows["ft_long_signal"].astype(int)
        rows["ft_short_entry_signal"] = rows["ft_short_signal"].astype(int)
        rows["ft_long_entry_stop"] = rows["ft_long_stop"]
        rows["ft_short_entry_stop"] = rows["ft_short_stop"]
        rows["ft_long_entry_tag"] = rows["ft_long_tag"]
        rows["ft_short_entry_tag"] = rows["ft_short_tag"]

        return rows

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
        dataframe.loc[dataframe["ft_long_entry_signal"] == 1, "enter_tag"] = dataframe["ft_long_entry_tag"]
        dataframe.loc[dataframe["ft_short_entry_signal"] == 1, "enter_tag"] = dataframe["ft_short_entry_tag"]
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
        return 1.0

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

        stop_rate = current_candle["ft_long_entry_stop"] if side == "long" else current_candle["ft_short_entry_stop"]
        if pd.isna(stop_rate):
            return 0

        stop_rate = float(stop_rate)
        distance_ratio = abs(current_rate - stop_rate) / current_rate
        if distance_ratio <= 0:
            return 0

        total_stake = self.wallets.get_total_stake_amount()
        risk_stake = (total_stake * 0.02) / distance_ratio
        capital_cap = total_stake * 0.25
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
            stop_rate = candle["ft_long_entry_stop"] if trade.is_short is False else candle["ft_short_entry_stop"]
            signal_kind = signal_kind or "unknown"

        if stop_rate is None or pd.isna(stop_rate):
            return

        stop_rate = float(stop_rate)
        risk_ratio = abs(trade.open_rate - stop_rate) / trade.open_rate
        trade.set_custom_data("smc_signal_kind", signal_kind or "unknown")
        trade.set_custom_data("smc_stop_rate", stop_rate)
        trade.set_custom_data("smc_target_roi", risk_ratio)

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
        stop_rate = trade.get_custom_data("smc_stop_rate")
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
        target_roi = trade.get_custom_data("smc_target_roi")
        if target_roi is not None:
            return float(target_roi)

        _, stop_rate = self._parse_enter_tag(entry_tag)
        if stop_rate is None:
            return None
        return abs(trade.open_rate - float(stop_rate)) / trade.open_rate
