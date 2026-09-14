"""Pure fail-closed collateral risk arithmetic for futures strategies."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class RiskInputs:
    side: str
    entry_rate: float
    stop_rate: float | None
    leverage: float
    max_leverage: float
    available_equity: float
    min_stake: float | None
    max_stake: float
    risk_fraction: float
    collateral_cap_fraction: float
    entry_fee_rate: float
    exit_fee_rate: float
    entry_slippage_rate: float
    stop_slippage_rate: float
    emergency_loss_ratio: float


@dataclass(frozen=True)
class RiskDecision:
    accepted: bool
    rejection_code: str | None
    collateral_stake: float
    notional: float
    quantity: float
    price_distance_ratio: float
    collateral_loss_ratio: float
    target_risk_budget: float
    capital_cap_binding: bool


def _rejected(code: str) -> RiskDecision:
    return RiskDecision(False, code, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False)


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def calculate_risk(inputs: RiskInputs) -> RiskDecision:
    """Return a collateral stake that remains within the declared risk budget."""
    side = inputs.side.casefold() if isinstance(inputs.side, str) else ""
    if side not in {"long", "short"}:
        return _rejected("INVALID_RISK_CONFIG")
    if inputs.stop_rate is None:
        return _rejected("MISSING_STOP")

    entry = _number(inputs.entry_rate)
    stop = _number(inputs.stop_rate)
    if entry is None or stop is None or entry <= 0 or stop <= 0:
        return _rejected("INVALID_NUMBER")

    leverage = _number(inputs.leverage)
    max_leverage = _number(inputs.max_leverage)
    if (
        leverage is None
        or max_leverage is None
        or leverage <= 0
        or max_leverage <= 0
        or leverage > max_leverage
    ):
        return _rejected("INVALID_LEVERAGE")

    available = _number(inputs.available_equity)
    if available is None:
        return _rejected("INVALID_NUMBER")
    if available <= 0:
        return _rejected("NO_AVAILABLE_EQUITY")

    max_stake = _number(inputs.max_stake)
    min_stake = None if inputs.min_stake is None else _number(inputs.min_stake)
    config_values = {
        "max_stake": max_stake,
        "min_stake": min_stake,
        "risk_fraction": _number(inputs.risk_fraction),
        "collateral_cap_fraction": _number(inputs.collateral_cap_fraction),
        "entry_fee_rate": _number(inputs.entry_fee_rate),
        "exit_fee_rate": _number(inputs.exit_fee_rate),
        "entry_slippage_rate": _number(inputs.entry_slippage_rate),
        "stop_slippage_rate": _number(inputs.stop_slippage_rate),
        "emergency_loss_ratio": _number(inputs.emergency_loss_ratio),
    }
    if (
        max_stake is None
        or max_stake <= 0
        or (min_stake is not None and (min_stake <= 0))
        or config_values["risk_fraction"] is None
        or not 0 < config_values["risk_fraction"] < 1
        or config_values["collateral_cap_fraction"] is None
        or not 0 < config_values["collateral_cap_fraction"] <= 1
        or config_values["emergency_loss_ratio"] is None
        or config_values["emergency_loss_ratio"] <= 0
    ):
        return _rejected("INVALID_RISK_CONFIG")
    for name in (
        "entry_fee_rate",
        "exit_fee_rate",
        "entry_slippage_rate",
        "stop_slippage_rate",
    ):
        value = config_values[name]
        if value is None or not 0 <= value < 1:
            return _rejected("INVALID_RISK_CONFIG")

    if min_stake is not None and min_stake > available:
        return _rejected("MIN_STAKE_UNAVAILABLE")

    entry_fee = config_values["entry_fee_rate"]
    exit_fee = config_values["exit_fee_rate"]
    entry_slippage = config_values["entry_slippage_rate"]
    stop_slippage = config_values["stop_slippage_rate"]
    emergency_limit = config_values["emergency_loss_ratio"]
    if side == "long":
        entry_worst = entry * (1 + entry_slippage)
        stop_worst = stop * (1 - stop_slippage)
        distance = (entry_worst - stop_worst) / entry_worst
    else:
        entry_worst = entry * (1 - entry_slippage)
        stop_worst = stop * (1 + stop_slippage)
        distance = (stop_worst - entry_worst) / entry_worst
    if not math.isfinite(distance) or distance <= 0:
        return _rejected("INVALID_STOP_SIDE")

    loss_ratio = leverage * (
        distance + entry_fee + (stop_worst / entry_worst) * exit_fee
    )
    if not math.isfinite(loss_ratio) or loss_ratio <= 0:
        return _rejected("INVALID_RISK_CONFIG")
    if loss_ratio >= emergency_limit:
        return _rejected("STOP_BEYOND_EMERGENCY_LIMIT")

    equity = min(available, max_stake)
    risk_budget = equity * config_values["risk_fraction"]
    risk_stake = risk_budget / loss_ratio
    capital_cap = equity * config_values["collateral_cap_fraction"]
    candidate = min(risk_stake, capital_cap, equity, max_stake)
    if not math.isfinite(candidate) or candidate <= 0:
        return _rejected("NO_AVAILABLE_EQUITY")
    if min_stake is not None and candidate < min_stake:
        return _rejected("MIN_STAKE_EXCEEDS_RISK")

    notional = candidate * leverage
    quantity = notional / entry_worst
    return RiskDecision(
        accepted=True,
        rejection_code=None,
        collateral_stake=float(candidate),
        notional=float(notional),
        quantity=float(quantity),
        price_distance_ratio=float(distance),
        collateral_loss_ratio=float(loss_ratio),
        target_risk_budget=float(risk_budget),
        capital_cap_binding=math.isclose(candidate, capital_cap, rel_tol=1e-12, abs_tol=1e-12),
    )
