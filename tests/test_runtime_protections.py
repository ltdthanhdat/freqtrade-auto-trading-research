import sqlite3

import pytest

from scripts.validation_core import ValidationStateStore
from src.strategies.SMC_FVG_Context30m_Freqtrade import SMC_FVG_Context30m_Freqtrade


def test_paused_state_requires_review_to_reopen(tmp_path):
    store = ValidationStateStore(tmp_path / "validation_state.sqlite")
    store.transition("global", "PAUSED", "drawdown", {}, None, "r1")

    with pytest.raises(ValueError, match="review"):
        store.transition("global", "ACTIVE", "timer", {}, None, "r1")


def test_review_approved_reopen_appends_history_and_updates_current_state(tmp_path):
    path = tmp_path / "validation_state.sqlite"
    store = ValidationStateStore(path)
    store.transition("global", "PAUSED", "drawdown", {}, None, "r1")
    store.transition(
        "global", "ACTIVE", "review-approved", {"max_drawdown": 0.16}, None, "r2"
    )

    with sqlite3.connect(path) as connection:
        events = connection.execute(
            "SELECT state, reason, metrics, run_id FROM state_events ORDER BY id"
        ).fetchall()
        current = connection.execute(
            "SELECT state, reason, metrics, run_id FROM current_state WHERE scope = ?", ("global",)
        ).fetchone()

    assert events == [
        ("PAUSED", "drawdown", "{}", "r1"),
        ("ACTIVE", "review-approved", '{"max_drawdown": 0.16}', "r2"),
    ]
    assert current == ("ACTIVE", "review-approved", '{"max_drawdown": 0.16}', "r2")


def test_strategy_declares_one_candle_cooldown():
    assert SMC_FVG_Context30m_Freqtrade({}).protections == [
        {"method": "CooldownPeriod", "stop_duration_candles": 1}
    ]
