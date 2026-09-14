import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest
from freqtrade.strategy import stoploss_from_absolute

from src.strategies.SMC_FVG_Confirmation_Freqtrade import SMC_FVG_Confirmation_Freqtrade


class Wallet:
    def __init__(self, available=1000.0):
        self.available = available

    def get_available_stake_amount(self):
        return self.available

    def get_total_stake_amount(self):
        raise AssertionError("total historical stake must not be used")


class UnavailableDataProvider:
    def get_analyzed_dataframe(self, **_kwargs):
        raise AssertionError("latest analyzed candle must not be read")


class FakeTrade:
    def __init__(self, *, is_short=False, tag="pin_bar|95.0", entries=1, open_rate=100.0, leverage=5.0):
        self.is_short = is_short
        self.enter_tag = tag
        self.nr_of_successful_entries = entries
        self.open_rate = open_rate
        self.leverage = leverage
        self.entry_side = "sell" if is_short else "buy"
        self.custom = {}

    def get_custom_data(self, key, default=None):
        return self.custom.get(key, default)

    def set_custom_data(self, key, value):
        self.custom[key] = value


class FailingPersistenceTrade(FakeTrade):
    def set_custom_data(self, key, value):
        if key != "smc_risk_state":
            raise OSError("custom data unavailable")
        self.custom[key] = value


def strategy(**config_overrides):
    config = json.loads(Path("config/config.futures.json").read_text())
    config.update(config_overrides)
    instance = SMC_FVG_Confirmation_Freqtrade(config)
    instance.wallets = Wallet()
    instance.dp = UnavailableDataProvider()
    return instance


def stake(instance, *, tag="pin_bar|95.0", side="long", rate=100.0, leverage=5.0, min_stake=1.0, max_stake=500.0):
    return instance.custom_stake_amount(
        pair="PLAY/USDT:USDT",
        current_time=None,
        current_rate=rate,
        proposed_stake=499.0,
        min_stake=min_stake,
        max_stake=max_stake,
        leverage=leverage,
        entry_tag=tag,
        side=side,
    )


def test_structural_stop_parser_is_tag_bound_and_side_validated():
    instance = strategy()

    assert instance._structural_stop_from_entry_tag("pin_bar|95.0", "long") == pytest.approx(95.0)
    assert instance._structural_stop_from_entry_tag("displacement|105.0", "short") == pytest.approx(105.0)
    assert instance._structural_stop_from_entry_tag("|95.0", "long") is None
    assert instance._structural_stop_from_entry_tag("pin_bar|nan", "long") is None
    assert instance._structural_stop_from_entry_tag("pin_bar|95.0", "diagonal") is None


def test_stake_uses_exact_tag_stop_not_latest_analyzed_candle():
    instance = strategy()

    result = stake(instance)

    assert result > 0
    assert result != 499.0


def test_short_tag_uses_short_stop_direction():
    assert stake(strategy(), tag="displacement|105.0", side="short") > 0


@pytest.mark.parametrize(
    ("tag", "side", "rate"),
    [
        (None, "long", 100.0),
        ("malformed", "long", 100.0),
        ("pin_bar|nan", "long", 100.0),
        ("pin_bar|inf", "long", 100.0),
        ("pin_bar|105", "long", 100.0),
        ("pin_bar|95", "short", 100.0),
        ("pin_bar|95", "diagonal", 100.0),
        ("pin_bar|95", "long", 0.0),
    ],
)
def test_invalid_or_wrong_side_tag_fails_closed(tag, side, rate):
    assert stake(strategy(), tag=tag, side=side, rate=rate) == 0.0


def test_zero_equity_invalid_leverage_and_minimum_stake_fail_closed():
    assert stake(strategy(), max_stake=0.0) == 0.0
    zero_wallet = strategy()
    zero_wallet.wallets = Wallet(available=0.0)
    assert stake(zero_wallet) == 0.0
    with pytest.raises(ValueError, match="SMC risk configuration"):
        strategy(smc_leverage=0)
    assert stake(strategy(), min_stake=500.0) == 0.0


def test_dp_is_not_required_to_reconstruct_a_valid_tag_stop():
    instance = strategy()
    instance.dp = None

    assert stake(instance) > 0


def test_first_entry_fill_persists_the_tag_bound_exit_plan_and_roi():
    instance = strategy()
    trade = FakeTrade(tag="pin_bar|95.0")

    instance.order_filled("PLAY/USDT:USDT", trade, SimpleNamespace(ft_order_side="buy"), None)

    assert trade.custom["smc_signal_kind"] == "pin_bar"
    assert trade.custom["smc_stop_rate"] == pytest.approx(95.0)
    assert trade.custom["smc_target_roi"] == pytest.approx(0.25)
    assert trade.custom["smc_risk_state"] == "READY"
    assert trade.custom["smc_plan_version"] == 1


def test_additional_or_wrong_side_fills_do_not_replace_first_entry_state():
    instance = strategy()
    trade = FakeTrade(tag="pin_bar|95.0", entries=2)
    trade.custom = {"smc_stop_rate": 94.0}

    instance.order_filled("PLAY/USDT:USDT", trade, SimpleNamespace(ft_order_side="buy"), None)

    assert trade.custom == {"smc_stop_rate": 94.0}

    wrong_side = FakeTrade(tag="pin_bar|95.0")
    instance.order_filled("PLAY/USDT:USDT", wrong_side, SimpleNamespace(ft_order_side="sell"), None)
    assert wrong_side.custom == {}


def test_malformed_fill_state_does_not_read_latest_candle_and_uses_emergency_stop():
    instance = strategy()
    trade = FakeTrade(tag="malformed")

    instance.order_filled("PLAY/USDT:USDT", trade, SimpleNamespace(ft_order_side="buy"), None)

    assert trade.custom["smc_risk_state"] == "EMERGENCY"
    assert instance.custom_stoploss("PLAY/USDT:USDT", trade, None, 100.0, 0.0, False) == pytest.approx(0.10)
    assert instance.custom_roi("PLAY/USDT:USDT", trade, None, 1, trade.enter_tag, "long") is None


def test_persistence_failure_marks_degraded_state_and_keeps_emergency_protection():
    instance = strategy()
    trade = FailingPersistenceTrade(tag="pin_bar|95.0")

    instance.order_filled("PLAY/USDT:USDT", trade, SimpleNamespace(ft_order_side="buy"), None)

    assert trade.custom["smc_risk_state"] == "EMERGENCY"
    assert instance.custom_stoploss("PLAY/USDT:USDT", trade, None, 100.0, 0.0, False) == pytest.approx(0.10)


def test_custom_stoploss_prefers_valid_persisted_or_tag_stop_and_never_candle_data():
    instance = strategy()
    trade = FakeTrade(tag="pin_bar|95.0")
    trade.custom["smc_stop_rate"] = 94.0
    expected = stoploss_from_absolute(94.0, current_rate=100.0, is_short=False, leverage=5.0)
    assert instance.custom_stoploss("PLAY/USDT:USDT", trade, None, 100.0, 0.0, False) == pytest.approx(expected)

    trade.custom["smc_stop_rate"] = 105.0
    expected_tag = stoploss_from_absolute(95.0, current_rate=100.0, is_short=False, leverage=5.0)
    assert instance.custom_stoploss("PLAY/USDT:USDT", trade, None, 100.0, 0.0, False) == pytest.approx(expected_tag)

    trade.custom.clear()
    assert instance.custom_stoploss("PLAY/USDT:USDT", trade, None, 100.0, 0.0, False) == pytest.approx(expected_tag)


def test_custom_stoploss_missing_state_always_returns_finite_emergency_value():
    instance = strategy()
    trade = FakeTrade(tag=None)

    result = instance.custom_stoploss("PLAY/USDT:USDT", trade, None, 100.0, 0.0, False)

    assert result == pytest.approx(0.10)
    assert math.isfinite(result)


def test_custom_roi_uses_fill_rate_and_tag_or_persisted_plan_without_inventing_target():
    instance = strategy()
    trade = FakeTrade(tag="pin_bar|95.0", open_rate=102.0, leverage=5.0)
    expected = (7.0 / 102.0) * 5.0
    assert instance.custom_roi("PLAY/USDT:USDT", trade, None, 1, trade.enter_tag, "long") == pytest.approx(expected)
    trade.custom["smc_target_roi"] = 0.4
    assert instance.custom_roi("PLAY/USDT:USDT", trade, None, 1, None, "long") == pytest.approx(0.4)

    trade.custom["smc_target_roi"] = float("nan")
    trade.enter_tag = None
    assert instance.custom_roi("PLAY/USDT:USDT", trade, None, 1, None, "long") is None


def test_risk_input_adapter_uses_the_callback_maximum():
    instance = strategy()
    values = instance._smc_risk_inputs(
        current_rate=100.0,
        stop_rate=95.0,
        leverage=5.0,
        max_leverage=7.0,
        min_stake=1.0,
        max_stake=500.0,
        side="long",
    )

    assert values.max_leverage == 7.0
    assert values.available_equity == 1000.0
