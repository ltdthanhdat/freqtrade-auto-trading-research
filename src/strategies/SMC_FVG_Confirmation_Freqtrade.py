from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
from typing import Optional

import pandas as pd
from freqtrade.persistence import Order, Trade
from freqtrade.strategy import IStrategy, stoploss_from_absolute
from pandas import DataFrame

from src.strategies.risk import RiskInputs, calculate_risk


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
    startup_candle_count = 64
    process_only_new_candles = True

    FVG_MAX_AGE_CANDLES = 48

    RISK_FORMULA_VERSION = "smc-risk-v1"
    EXIT_PLAN_VERSION = 1
    SMC_MAX_COLLATERAL_LOSS_RATIO = 1.0
    REQUIRED_SMC_CONFIG_KEYS = (
        "smc_risk_per_trade",
        "smc_capital_cap",
        "smc_leverage",
        "smc_entry_fee_rate",
        "smc_exit_fee_rate",
        "smc_entry_slippage_rate",
        "smc_stop_slippage_rate",
        "smc_missing_stoploss_roi",
    )

    def __init__(self, config: dict):
        self.validate_smc_config(config)
        super().__init__(config)

    minimal_roi = {"0": 100.0}
    stoploss = -0.99
    use_custom_stoploss = True
    use_custom_roi = True
    use_exit_signal = False
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    PIN_BAR_BODY_RATIO = 0.33
    PIN_BAR_WICK_TO_BODY = 2.5
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
        except (TypeError, ValueError):
            return parts[0], None

    @classmethod
    def _structural_stop_from_entry_tag(
        cls, entry_tag: str | None, side: str
    ) -> float | None:
        if not isinstance(side, str) or side.casefold() not in {"long", "short"}:
            return None
        signal_kind, stop_rate = cls._parse_enter_tag(entry_tag)
        if not isinstance(signal_kind, str) or not signal_kind.strip() or stop_rate is None:
            return None
        if not math.isfinite(stop_rate) or stop_rate <= 0:
            return None
        return float(stop_rate)

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
            active_bullish = [
                fvg
                for fvg in active_bullish
                if i - fvg.bar_index < self.FVG_MAX_AGE_CANDLES and current_low > fvg.bottom
            ]
            active_bearish = [
                fvg
                for fvg in active_bearish
                if i - fvg.bar_index < self.FVG_MAX_AGE_CANDLES and current_high < fvg.top
            ]

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

    @classmethod
    def validate_smc_config(cls, config: dict) -> None:
        if not isinstance(config, dict):
            raise ValueError("SMC risk configuration is invalid")
        missing = [key for key in cls.REQUIRED_SMC_CONFIG_KEYS if key not in config]
        if missing:
            raise ValueError(f"SMC risk configuration missing: {missing[0]}")

        leverage = config.get("smc_leverage")
        if leverage != "max":
            leverage = cls._finite_config_value(config, "smc_leverage")
            if leverage <= 0:
                raise ValueError("SMC risk configuration smc_leverage is invalid")
        risk_fraction = cls._finite_config_value(config, "smc_risk_per_trade")
        capital_cap = cls._finite_config_value(config, "smc_capital_cap")
        if not 0 < risk_fraction < 1 or not 0 < capital_cap <= 1:
            raise ValueError("SMC risk configuration fractions are invalid")
        for key in cls.REQUIRED_SMC_CONFIG_KEYS[3:7]:
            value = cls._finite_config_value(config, key)
            if not 0 <= value < 1:
                raise ValueError(f"SMC risk configuration {key} is invalid")
        missing_stoploss = cls._finite_config_value(config, "smc_missing_stoploss_roi")
        if not -1 < missing_stoploss < 0:
            raise ValueError("SMC risk configuration smc_missing_stoploss_roi is invalid")

    @classmethod
    def _validation_metadata_for_config(cls, config: dict) -> dict[str, object]:
        cls.validate_smc_config(config)
        encoded = json.dumps(config, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        config_sha256 = hashlib.sha256(encoded).hexdigest()
        return {
            "strategy_name": cls.__name__,
            "config_sha256": config_sha256,
            "risk_formula_version": cls.RISK_FORMULA_VERSION,
            "plan_version": cls.EXIT_PLAN_VERSION,
            "exit_plan_version": cls.EXIT_PLAN_VERSION,
        }

    def validation_metadata(self) -> dict[str, object]:
        return self._validation_metadata_for_config(self.config)

    def validation_metadata_for_config(self) -> dict[str, object]:
        return self.validation_metadata()

    @staticmethod
    def _finite_config_value(config: dict, key: str) -> float:
        value = config.get(key)
        if isinstance(value, bool):
            raise ValueError(f"SMC risk configuration {key} is invalid")
        try:
            value = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"SMC risk configuration {key} is invalid") from exc
        if not math.isfinite(value):
            raise ValueError(f"SMC risk configuration {key} is invalid")
        return value

    def _configured_leverage(self, max_leverage: float) -> float:
        if not math.isfinite(float(max_leverage)) or float(max_leverage) <= 0:
            raise ValueError("SMC risk configuration max_leverage is invalid")
        configured = self.config.get("smc_leverage")
        if configured == "max":
            value = float(max_leverage)
        else:
            value = self._finite_config_value(self.config, "smc_leverage")
        if value <= 0 or value > float(max_leverage):
            raise ValueError("SMC risk configuration smc_leverage is invalid")
        return value

    def _smc_risk_inputs(
        self,
        *,
        current_rate: float,
        stop_rate: float | None,
        leverage: float,
        max_leverage: float,
        min_stake: float | None,
        max_stake: float,
        side: str,
    ) -> RiskInputs:
        self._configured_leverage(max_leverage)
        risk_fraction = self._finite_config_value(self.config, "smc_risk_per_trade")
        capital_cap = self._finite_config_value(self.config, "smc_capital_cap")
        if not 0 < risk_fraction < 1 or not 0 < capital_cap <= 1:
            raise ValueError("SMC risk configuration fractions are invalid")
        for key in (
            "smc_entry_fee_rate",
            "smc_exit_fee_rate",
            "smc_entry_slippage_rate",
            "smc_stop_slippage_rate",
        ):
            value = self._finite_config_value(self.config, key)
            if not 0 <= value < 1:
                raise ValueError(f"SMC risk configuration {key} is invalid")
        emergency = self._finite_config_value(self.config, "smc_missing_stoploss_roi")
        if not -1 < emergency < 0:
            raise ValueError("SMC risk configuration smc_missing_stoploss_roi is invalid")
        if self.wallets is None or not callable(getattr(self.wallets, "get_available_stake_amount", None)):
            raise ValueError("SMC risk configuration wallet is unavailable")
        available_equity = self.wallets.get_available_stake_amount()
        return RiskInputs(
            side=side,
            entry_rate=current_rate,
            stop_rate=stop_rate,
            leverage=leverage,
            max_leverage=max_leverage,
            available_equity=available_equity,
            min_stake=min_stake,
            max_stake=max_stake,
            risk_fraction=risk_fraction,
            collateral_cap_fraction=capital_cap,
            entry_fee_rate=self._finite_config_value(self.config, "smc_entry_fee_rate"),
            exit_fee_rate=self._finite_config_value(self.config, "smc_exit_fee_rate"),
            entry_slippage_rate=self._finite_config_value(self.config, "smc_entry_slippage_rate"),
            stop_slippage_rate=self._finite_config_value(self.config, "smc_stop_slippage_rate"),
            emergency_loss_ratio=self.SMC_MAX_COLLATERAL_LOSS_RATIO,
        )

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
        try:
            return self._configured_leverage(max_leverage)
        except (TypeError, ValueError):
            return 0.0

    def _emergency_stoploss(self, trade: Trade, current_rate: float) -> float:
        try:
            ratio = abs(self._finite_config_value(self.config, "smc_missing_stoploss_roi"))
            leverage = float(trade.leverage)
            current_rate = float(current_rate)
            if not 0 < ratio < 1 or not math.isfinite(leverage) or leverage <= 0:
                return 0.0
            if not math.isfinite(current_rate) or current_rate <= 0:
                return 0.0
            price_ratio = ratio / leverage
            stop_rate = current_rate * (1 - price_ratio if not trade.is_short else 1 + price_ratio)
            result = stoploss_from_absolute(
                stop_rate,
                current_rate=current_rate,
                is_short=trade.is_short,
                leverage=leverage,
            )
            return float(result) if math.isfinite(float(result)) else 0.0
        except (AttributeError, TypeError, ValueError):
            return 0.0

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
        try:
            stop_rate = self._structural_stop_from_entry_tag(entry_tag, side)
            if stop_rate is None:
                return 0.0
            decision = calculate_risk(
                self._smc_risk_inputs(
                    current_rate=current_rate,
                    stop_rate=stop_rate,
                    leverage=leverage,
                    max_leverage=float(kwargs.get("max_leverage", leverage)),
                    min_stake=min_stake,
                    max_stake=max_stake,
                    side=side,
                )
            )
            return decision.collateral_stake if decision.accepted else 0.0
        except Exception:
            return 0.0

    @staticmethod
    def _valid_stop_for_entry(trade: Trade, stop_rate: object) -> float | None:
        try:
            stop_rate = float(stop_rate)
            open_rate = float(trade.open_rate)
        except (AttributeError, TypeError, ValueError):
            return None
        if not math.isfinite(stop_rate) or not math.isfinite(open_rate) or open_rate <= 0:
            return None
        if trade.is_short:
            return stop_rate if stop_rate > open_rate else None
        return stop_rate if stop_rate < open_rate else None

    @staticmethod
    def _valid_stop_for_current(trade: Trade, stop_rate: object, current_rate: object) -> float | None:
        stop_rate = SMC_FVG_Confirmation_Freqtrade._valid_stop_for_entry(trade, stop_rate)
        try:
            current_rate = float(current_rate)
        except (TypeError, ValueError):
            return None
        if stop_rate is None or not math.isfinite(current_rate) or current_rate <= 0:
            return None
        if trade.is_short:
            return stop_rate if stop_rate > current_rate else None
        return stop_rate if stop_rate < current_rate else None

    @staticmethod
    def _custom_data(trade: Trade, key: str, default: object = None) -> object:
        try:
            return trade.get_custom_data(key, default)
        except Exception:
            return default

    def _tag_stop_for_trade(self, trade: Trade, entry_tag: str | None = None) -> float | None:
        tag = entry_tag if entry_tag is not None else getattr(trade, "enter_tag", None)
        side = "short" if trade.is_short else "long"
        return self._valid_stop_for_entry(trade, self._structural_stop_from_entry_tag(tag, side))

    def _mark_emergency(self, trade: Trade) -> None:
        for key, value in (("smc_risk_state", "EMERGENCY"), ("smc_plan_version", self.EXIT_PLAN_VERSION)):
            try:
                trade.set_custom_data(key, value)
            except Exception:
                pass

    def _persist_exit_plan(self, trade: Trade, signal_kind: str, stop_rate: float, target_roi: float) -> bool:
        payload = {
            "smc_signal_kind": signal_kind,
            "smc_stop_rate": stop_rate,
            "smc_target_roi": target_roi,
            "smc_risk_state": "READY",
            "smc_plan_version": self.EXIT_PLAN_VERSION,
        }
        try:
            for key, value in payload.items():
                trade.set_custom_data(key, value)
            for key, expected in payload.items():
                if self._custom_data(trade, key) != expected:
                    return False
            return True
        except Exception:
            return False

    def order_filled(self, pair: str, trade: Trade, order: Order, current_time: datetime, **kwargs) -> None:
        if order.ft_order_side != trade.entry_side or trade.nr_of_successful_entries != 1:
            return
        if self._custom_data(trade, "smc_plan_version") is not None:
            return

        signal_kind, _ = self._parse_enter_tag(getattr(trade, "enter_tag", None))
        stop_rate = self._tag_stop_for_trade(trade)
        if stop_rate is None:
            self._mark_emergency(trade)
            return

        try:
            leverage = float(trade.leverage)
            risk_ratio = abs(float(trade.open_rate) - stop_rate) / float(trade.open_rate)
            target_roi = risk_ratio * leverage
            if not math.isfinite(leverage) or leverage <= 0 or not math.isfinite(target_roi):
                raise ValueError("invalid SMC exit plan")
        except (AttributeError, TypeError, ValueError, ZeroDivisionError):
            self._mark_emergency(trade)
            return

        if not self._persist_exit_plan(trade, signal_kind or "unknown", stop_rate, target_roi):
            self._mark_emergency(trade)

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> float:
        try:
            if self._custom_data(trade, "smc_risk_state") == "EMERGENCY":
                return self._emergency_stoploss(trade, current_rate)
            stop_rate = self._valid_stop_for_current(
                trade,
                self._custom_data(trade, "smc_stop_rate"),
                current_rate,
            )
            if stop_rate is None:
                stop_rate = self._valid_stop_for_current(
                    trade,
                    self._tag_stop_for_trade(trade),
                    current_rate,
                )
            if stop_rate is None:
                return self._emergency_stoploss(trade, current_rate)
            result = stoploss_from_absolute(
                stop_rate,
                current_rate=float(current_rate),
                is_short=trade.is_short,
                leverage=float(trade.leverage),
            )
            return float(result) if math.isfinite(float(result)) else 0.0
        except (AttributeError, TypeError, ValueError, ZeroDivisionError):
            return self._emergency_stoploss(trade, current_rate)

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
        if self._custom_data(trade, "smc_risk_state") == "EMERGENCY":
            return None
        target_roi = self._custom_data(trade, "smc_target_roi")
        try:
            if target_roi is not None:
                target_roi = float(target_roi)
                if math.isfinite(target_roi) and target_roi >= 0:
                    return target_roi
        except (TypeError, ValueError):
            pass

        expected_side = "short" if trade.is_short else "long"
        if not isinstance(side, str) or side.casefold() != expected_side:
            return None
        stop_rate = self._tag_stop_for_trade(trade, entry_tag)
        if stop_rate is None:
            return None
        try:
            target_roi = (abs(float(trade.open_rate) - stop_rate) / float(trade.open_rate)) * float(trade.leverage)
            return target_roi if math.isfinite(target_roi) and target_roi >= 0 else None
        except (AttributeError, TypeError, ValueError, ZeroDivisionError):
            return None
