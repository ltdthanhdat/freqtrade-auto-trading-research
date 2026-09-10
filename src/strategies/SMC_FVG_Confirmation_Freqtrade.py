from __future__ import annotations

from typing import Optional

import pandas as pd
from pandas import DataFrame

from src.strategies.FuturesRiskBase_Freqtrade import FuturesRiskBase_Freqtrade


class FVG:
    def __init__(self, top: float, bottom: float, is_bullish: bool, bar_index: int) -> None:
        self.top = top
        self.bottom = bottom
        self.is_bullish = is_bullish
        self.bar_index = bar_index


class SMC_FVG_Confirmation_Freqtrade(FuturesRiskBase_Freqtrade):
    PIN_BAR_BODY_RATIO = 0.33
    PIN_BAR_WICK_TO_BODY = 2.5
    PIN_BAR_CLOSE_EXTREME_RATIO = 0.30
    FVG_RETRACE_RATIO = 0.45
    FVG_CONFIRM_RATIO = 0.55

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
                and body_ratio >= 0.55
                and close_price > prev_high
                and close_price >= high_price - total_range * 0.25
            )

        return (
            close_price < open_price
            and body_ratio >= 0.55
            and close_price < prev_low
            and close_price <= low_price + total_range * 0.25
        )

    def _entry_signal_kind(self, row: pd.Series, prev_row: pd.Series, is_bullish: bool) -> Optional[str]:
        if self._is_displacement_break(row, prev_row, is_bullish):
            return "displacement"
        if self._is_trend_body(row, is_bullish):
            return "trend_body"
        if self._is_pin_bar(row, is_bullish):
            return "pin_bar"
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
