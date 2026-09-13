from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .core import canonical_json


_EXIT_TYPES = frozenset(
    {
        "ATR",
        "FIXED_PERCENT",
        "FVG_ABSOLUTE",
        "REGIME",
        "R_MULTIPLE",
        "SIGNAL",
        "TIME",
        "TRAILING",
        "NONE",
    }
)
_CLAIM_ROLES = frozenset(
    {
        "ENTRY_SUPPORT",
        "STOP_SUPPORT",
        "PROFIT_EXIT_SUPPORT",
        "TIME_EXIT_SUPPORT",
        "TRAILING_EXIT_SUPPORT",
        "REGIME_EXIT_SUPPORT",
        "SIZING_SUPPORT",
        "CONTRADICTION",
        "FALSIFIER",
    }
)
_EXIT_PRECEDENCE = frozenset(
    {
        "PROTECTIVE_STOP",
        "PROFIT_TARGET",
        "TIME_EXIT",
        "TRAILING_EXIT",
        "REGIME_EXIT",
        "SIGNAL_EXIT",
        "EMERGENCY_EXIT",
        "LIQUIDATION",
    }
)


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return dict(value)


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _reject_ranges(value: object, path: str = "plan") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key).casefold()
            if "range" in key_text:
                raise ValueError(f"{path}.{key} must contain an exact value, not a range")
            _reject_ranges(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_ranges(child, f"{path}[{index}]")


def _validate_exit_design(value: object, index: int) -> dict[str, Any]:
    field = f"exit_designs[{index}]"
    design = _object(value, field)
    _nonempty_text(design.get("name"), f"{field}.name")
    for component in (
        "protective_stop",
        "profit_exit",
        "time_exit",
        "trailing_exit",
        "regime_exit",
    ):
        component_value = _object(design.get(component), f"{field}.{component}")
        exit_type = _nonempty_text(component_value.get("type"), f"{field}.{component}.type")
        if exit_type not in _EXIT_TYPES:
            raise ValueError(f"{field}.{component}.type is invalid")
        if component == "protective_stop" and exit_type == "NONE":
            raise ValueError("protective_stop cannot be NONE")
        if exit_type != "NONE":
            _nonempty_text(component_value.get("formula"), f"{field}.{component}.formula")
    precedence = design.get("exit_precedence")
    if not isinstance(precedence, list) or not precedence:
        raise ValueError(f"{field}.exit_precedence is required")
    if any(item not in _EXIT_PRECEDENCE for item in precedence):
        raise ValueError(f"{field}.exit_precedence contains an invalid exit")
    for component in ("gap_behavior", "stop_update_policy", "emergency_behavior"):
        _nonempty_text(design.get(component), f"{field}.{component}")
    return design


def validate_evidence_link(value: object) -> dict[str, Any]:
    link = _object(value, "evidence link")
    roles = link.get("roles")
    if not isinstance(roles, list) or not roles or any(role not in _CLAIM_ROLES for role in roles):
        raise ValueError("evidence link roles are invalid")
    if len(set(roles)) != len(roles):
        raise ValueError("evidence link roles must be unique")
    for field in ("supported_claim", "transfer_assumption", "limitations"):
        _nonempty_text(link.get(field), f"evidence link {field}")
    return link


def validate_trading_plan(value: object, *, identity_bound: bool) -> dict[str, Any]:
    plan = _object(value, "trading_plan")
    _reject_ranges(plan)
    if plan.get("schema_version") != 1:
        raise ValueError("trading_plan schema_version must be 1")
    required_data = plan.get("required_data")
    if not isinstance(required_data, list) or not required_data:
        raise ValueError("trading_plan required_data must be a non-empty list")
    if identity_bound and [str(item).upper() for item in required_data] != ["OHLCV"]:
        raise ValueError("trading_plan required_data must be exactly [OHLCV]")

    entry_plan = _object(plan.get("entry_plan"), "entry_plan")
    for field in (
        "signal_definition",
        "confirmation",
        "timestamp_semantics",
        "order_assumption",
        "validity_window",
        "duplicate_signal_policy",
        "pre_fill_invalidation",
    ):
        _nonempty_text(entry_plan.get(field), f"entry_plan.{field}")

    exit_designs = plan.get("exit_designs")
    if not isinstance(exit_designs, list) or not 1 <= len(exit_designs) <= 2:
        raise ValueError("exit_designs must contain one or two designs")
    normalized_designs = [_validate_exit_design(item, index) for index, item in enumerate(exit_designs)]

    for section in (
        "sizing_plan",
        "cost_model",
        "development_protocol",
        "outer_acceptance_policy",
    ):
        section_value = _object(plan.get(section), section)
        if not section_value:
            raise ValueError(f"{section} is required")
    falsifiers = plan.get("falsifiers")
    if not isinstance(falsifiers, list) or not falsifiers:
        raise ValueError("falsifiers must be a non-empty list")
    if any(not isinstance(item, str) or not item.strip() for item in falsifiers):
        raise ValueError("falsifiers must contain non-empty text")

    evidence_map = _object(plan.get("evidence_map"), "evidence_map")
    for claim in ("entry", "stop", "profit_exit"):
        sources = evidence_map.get(claim)
        if not isinstance(sources, list) or not sources:
            raise ValueError(f"evidence_map.{claim} is required")

    normalized = dict(plan)
    normalized["required_data"] = list(required_data)
    normalized["entry_plan"] = entry_plan
    normalized["exit_designs"] = normalized_designs
    normalized["falsifiers"] = list(falsifiers)
    normalized["evidence_map"] = evidence_map
    return normalized


def canonical_plan_json(value: Mapping[str, Any]) -> str:
    try:
        return canonical_json(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("trading_plan is not canonicalizable JSON") from exc


def plan_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_plan_json(value).encode("utf-8")).hexdigest()
