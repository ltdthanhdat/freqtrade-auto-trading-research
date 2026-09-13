import hashlib

import pytest

from research_runtime.plan import (
    canonical_plan_json,
    plan_sha256,
    validate_evidence_link,
    validate_trading_plan,
)


def valid_plan():
    return {
        "schema_version": 1,
        "family_id": "smc-fvg",
        "required_data": ["OHLCV"],
        "entry_plan": {
            "signal_definition": "confirmed FVG retest",
            "confirmation": "close confirms direction",
            "timestamp_semantics": "completed candle close",
            "order_assumption": "market at signal close",
            "validity_window": "one execution candle",
            "duplicate_signal_policy": "one entry per signal candle",
            "pre_fill_invalidation": "cancel when structural stop is crossed",
        },
        "exit_designs": [
            {
                "name": "smc-1r",
                "protective_stop": {
                    "type": "FVG_ABSOLUTE",
                    "formula": "long stop=fvg.bottom; short stop=fvg.top",
                    "constants": {"fvg_validity_candles": 48},
                },
                "profit_exit": {
                    "type": "R_MULTIPLE",
                    "formula": "one gross R from filled entry to structural stop",
                    "multiple": 1,
                },
                "time_exit": {"type": "NONE"},
                "trailing_exit": {"type": "NONE"},
                "regime_exit": {"type": "NONE"},
                "exit_precedence": ["PROTECTIVE_STOP", "PROFIT_TARGET"],
                "gap_behavior": "stop execution is exchange dependent",
                "stop_update_policy": "fixed after fill",
                "emergency_behavior": "configured missing-state fallback",
            }
        ],
        "sizing_plan": {
            "risk_basis": "initial structural stop",
            "risk_budget": "smc_risk_per_trade",
            "capital_cap": "smc_capital_cap",
            "leverage_rule": "configured leverage capped by exchange maximum",
            "concurrent_risk_limit": "max open trades",
            "stop_relation": "stake is reduced as stop distance grows",
            "fee_slippage_allowance": "config rates",
            "minimum_order_behavior": "reject below minimum",
            "precision_behavior": "never round risk upward",
        },
        "cost_model": {
            "entry_fee": "smc_entry_fee_rate",
            "exit_fee": "smc_exit_fee_rate",
            "entry_slippage": "smc_entry_slippage_rate",
            "stop_slippage": "smc_stop_slippage_rate",
        },
        "development_protocol": {
            "windows": ["development-1", "development-2", "development-3"],
            "selector": "hard gates then return-to-drawdown",
            "tie_breaker": "simpler plan",
            "attempt_limit": 1,
        },
        "outer_acceptance_policy": {
            "required_folds": 3,
            "positive_fold_majority": 2,
            "stress_required": True,
        },
        "falsifiers": [
            "negative stressed OOS profit",
            "wrong-side initial stop",
            "missing risk ledger coverage",
        ],
        "evidence_map": {
            "entry": ["S-entry"],
            "stop": ["S-stop"],
            "profit_exit": ["S-profit"],
        },
    }


def test_complete_plan_is_valid_and_hash_is_canonical():
    plan = valid_plan()

    validated = validate_trading_plan(plan, identity_bound=True)
    reordered = {key: plan[key] for key in reversed(list(plan))}

    assert validated["required_data"] == ["OHLCV"]
    assert canonical_plan_json(plan) == canonical_plan_json(reordered)
    assert plan_sha256(plan) == hashlib.sha256(canonical_plan_json(plan).encode()).hexdigest()
    assert plan_sha256(plan) == plan_sha256(reordered)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["exit_designs"][0].pop("protective_stop"),
        lambda value: value["exit_designs"][0]["time_exit"].update({"type": "OMITTED"}),
        lambda value: value["development_protocol"].update({"parameter_range": [1, 2]}),
        lambda value: value.update({"required_data": ["OHLCV", "OPTIONS"]}),
        lambda value: value.update({"falsifiers": []}),
        lambda value: value["exit_designs"][0]["profit_exit"].pop("formula"),
    ],
)
def test_identity_bound_plan_rejects_incomplete_or_unsafe_shape(mutation):
    plan = valid_plan()
    mutation(plan)

    with pytest.raises(ValueError):
        validate_trading_plan(plan, identity_bound=True)


def test_non_identity_plan_may_declare_non_ohlcv_data_but_identity_plan_may_not():
    plan = valid_plan()
    plan["required_data"] = ["OHLCV", "FUNDING"]

    validate_trading_plan(plan, identity_bound=False)
    with pytest.raises(ValueError, match="required_data"):
        validate_trading_plan(plan, identity_bound=True)


@pytest.mark.parametrize(
    "value",
    [
        {"roles": ["ENTRY_SUPPORT"]},
        {"roles": ["STOP_SUPPORT"], "supported_claim": ""},
        {"roles": ["UNKNOWN"], "supported_claim": "stop", "transfer_assumption": "x"},
        {"roles": ["STOP_SUPPORT"], "supported_claim": "stop"},
    ],
)
def test_evidence_link_requires_claim_role_and_transfer_limitations(value):
    with pytest.raises(ValueError):
        validate_evidence_link(value)


def test_evidence_link_accepts_explicit_claim_roles():
    link = validate_evidence_link(
        {
            "roles": ["STOP_SUPPORT", "PROFIT_EXIT_SUPPORT"],
            "supported_claim": "structural stop and target",
            "transfer_assumption": "crypto OHLCV transfer",
            "limitations": "does not establish exact multiplier",
        }
    )

    assert link["roles"] == ["STOP_SUPPORT", "PROFIT_EXIT_SUPPORT"]
