import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.strategies.SMC_FVG_Confirmation_Freqtrade import SMC_FVG_Confirmation_Freqtrade
from src.strategies.risk import RiskInputs, calculate_risk


def inputs(**overrides):
    values = {
        "side": "long",
        "entry_rate": 100.0,
        "stop_rate": 95.0,
        "leverage": 5.0,
        "max_leverage": 10.0,
        "available_equity": 1000.0,
        "min_stake": 1.0,
        "max_stake": 1000.0,
        "risk_fraction": 0.05,
        "collateral_cap_fraction": 0.25,
        "entry_fee_rate": 0.0,
        "exit_fee_rate": 0.0,
        "entry_slippage_rate": 0.0,
        "stop_slippage_rate": 0.0,
        "emergency_loss_ratio": 0.5,
    }
    values.update(overrides)
    return RiskInputs(**values)


def test_futures_config_uses_explicit_namespaced_smc_risk_values():
    config = json.loads(Path("config/config.futures.json").read_text())
    expected = {
        "smc_risk_per_trade",
        "smc_capital_cap",
        "smc_leverage",
        "smc_entry_fee_rate",
        "smc_exit_fee_rate",
        "smc_entry_slippage_rate",
        "smc_stop_slippage_rate",
        "smc_missing_stoploss_roi",
    }

    assert expected <= config.keys()
    assert config["smc_missing_stoploss_roi"] == -0.10
    assert not {"risk_per_trade", "capital_cap"} & config.keys()
    for key in expected - {"smc_leverage", "smc_missing_stoploss_roi"}:
        assert math.isfinite(float(config[key]))
        if "capital" not in key and "risk" not in key:
            assert float(config[key]) >= 0


def test_smc_risk_inputs_use_available_equity_and_validate_required_config():
    config = json.loads(Path("config/config.futures.json").read_text())
    strategy = SMC_FVG_Confirmation_Freqtrade(config)
    strategy.wallets = SimpleNamespace(
        get_available_stake_amount=lambda: 123.0,
        get_total_stake_amount=lambda: 9999.0,
    )

    risk = strategy._smc_risk_inputs(
        current_rate=100.0,
        stop_rate=95.0,
        leverage=5.0,
        max_leverage=10.0,
        min_stake=1.0,
        max_stake=500.0,
        side="long",
    )
    assert risk.available_equity == 123.0
    assert risk.max_stake == 500.0

    for key in ("smc_entry_fee_rate", "smc_exit_fee_rate", "smc_entry_slippage_rate", "smc_stop_slippage_rate"):
        broken = {name: value for name, value in config.items() if name != key}
        with pytest.raises(ValueError, match="SMC risk configuration"):
            SMC_FVG_Confirmation_Freqtrade(broken)._smc_risk_inputs(
                current_rate=100.0,
                stop_rate=95.0,
                leverage=5.0,
                max_leverage=10.0,
                min_stake=1.0,
                max_stake=500.0,
                side="long",
            )


def test_missing_state_emergency_is_the_declared_collateral_loss_ratio():
    config = json.loads(Path("config/config.futures.json").read_text())
    strategy = SMC_FVG_Confirmation_Freqtrade(config)
    trade = SimpleNamespace(is_short=False, leverage=5.0)

    assert strategy._emergency_stoploss(trade, 100.0) == pytest.approx(0.10)
    assert strategy._emergency_stoploss(SimpleNamespace(is_short=True, leverage=5.0), 100.0) == pytest.approx(0.10)


def test_long_uses_conservative_execution_prices_and_applies_leverage_once():
    decision = calculate_risk(
        inputs(
            entry_fee_rate=0.001,
            exit_fee_rate=0.002,
            entry_slippage_rate=0.01,
            stop_slippage_rate=0.01,
        )
    )

    entry_worst = 100.0 * 1.01
    stop_worst = 95.0 * 0.99
    distance = (entry_worst - stop_worst) / entry_worst
    loss_ratio = 5.0 * (
        distance + 0.001 + (stop_worst / entry_worst) * 0.002
    )
    expected_stake = min(1000.0 * 0.05 / loss_ratio, 1000.0 * 0.25, 1000.0)

    assert decision.accepted is True
    assert decision.price_distance_ratio == pytest.approx(distance)
    assert decision.collateral_loss_ratio == pytest.approx(loss_ratio)
    assert decision.target_risk_budget == pytest.approx(50.0)
    assert decision.collateral_stake == pytest.approx(expected_stake)
    assert decision.notional == pytest.approx(expected_stake * 5.0)
    assert decision.quantity == pytest.approx(expected_stake * 5.0 / entry_worst)
    assert decision.capital_cap_binding is False


def test_short_uses_the_opposite_adverse_slippage_direction():
    decision = calculate_risk(
        inputs(
            side="short",
            entry_rate=100.0,
            stop_rate=105.0,
            entry_fee_rate=0.001,
            exit_fee_rate=0.002,
            entry_slippage_rate=0.01,
            stop_slippage_rate=0.01,
        )
    )

    entry_worst = 100.0 * 0.99
    stop_worst = 105.0 * 1.01
    distance = (stop_worst - entry_worst) / entry_worst
    loss_ratio = 5.0 * (
        distance + 0.001 + (stop_worst / entry_worst) * 0.002
    )
    assert decision.accepted is True
    assert decision.price_distance_ratio == pytest.approx(distance)
    assert decision.collateral_loss_ratio == pytest.approx(loss_ratio)


def test_costs_reduce_stake_and_risk_and_capital_limits_bind():
    free = calculate_risk(inputs())
    costly = calculate_risk(
        inputs(entry_fee_rate=0.001, exit_fee_rate=0.001, entry_slippage_rate=0.01)
    )
    capped = calculate_risk(inputs(risk_fraction=0.9, collateral_cap_fraction=0.1))

    assert free.collateral_stake > costly.collateral_stake
    assert capped.collateral_stake == pytest.approx(100.0)
    assert capped.capital_cap_binding is True


def test_available_equity_not_total_historical_balance():
    decision = calculate_risk(inputs(available_equity=100.0, max_stake=1000.0))

    assert decision.collateral_stake == pytest.approx(20.0)
    assert decision.target_risk_budget == pytest.approx(5.0)


def test_stake_below_exchange_minimum_is_rejected_without_rounding_up():
    decision = calculate_risk(inputs(min_stake=21.0, available_equity=100.0))

    assert decision.accepted is False
    assert decision.rejection_code == "MIN_STAKE_EXCEEDS_RISK"
    assert decision.collateral_stake == 0.0
    assert decision.notional == 0.0


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"stop_rate": None}, "MISSING_STOP"),
        ({"stop_rate": 100.0}, "INVALID_STOP_SIDE"),
        ({"side": "short", "stop_rate": 100.0}, "INVALID_STOP_SIDE"),
        ({"side": "diagonal"}, "INVALID_RISK_CONFIG"),
        ({"entry_rate": float("nan")}, "INVALID_NUMBER"),
        ({"stop_rate": float("inf")}, "INVALID_NUMBER"),
        ({"leverage": 0.0}, "INVALID_LEVERAGE"),
        ({"leverage": 11.0}, "INVALID_LEVERAGE"),
        ({"max_leverage": 0.0}, "INVALID_LEVERAGE"),
        ({"available_equity": 0.0}, "NO_AVAILABLE_EQUITY"),
        ({"available_equity": 0.5, "min_stake": 1.0}, "MIN_STAKE_UNAVAILABLE"),
        ({"entry_fee_rate": -0.01}, "INVALID_RISK_CONFIG"),
        ({"risk_fraction": 0.0}, "INVALID_RISK_CONFIG"),
        ({"emergency_loss_ratio": 0.01}, "STOP_BEYOND_EMERGENCY_LIMIT"),
    ],
)
def test_rejection_codes_are_deterministic(overrides, code):
    decision = calculate_risk(inputs(**overrides))

    assert decision.accepted is False
    assert decision.rejection_code == code
    assert decision.collateral_stake == 0.0
    assert decision.notional == 0.0
    assert decision.quantity == 0.0


def test_every_rejection_amount_is_finite():
    decision = calculate_risk(inputs(stop_rate=float("nan")))

    assert all(
        math.isfinite(value)
        for value in (
            decision.collateral_stake,
            decision.notional,
            decision.quantity,
            decision.price_distance_ratio,
            decision.collateral_loss_ratio,
            decision.target_risk_budget,
        )
    )
