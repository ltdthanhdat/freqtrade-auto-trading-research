import pytest

from scripts.validation_core import ValidationStateStore
from src.strategies.SMC_FVG_Context30m_Freqtrade import SMC_FVG_Context30m_Freqtrade


def test_paused_state_requires_review_to_reopen(tmp_path):
    store = ValidationStateStore(tmp_path / "validation_state.sqlite")
    store.transition("global", "PAUSED", "drawdown", {}, None, "r1")

    with pytest.raises(ValueError, match="review"):
        store.transition("global", "ACTIVE", "timer", {}, None, "r1")


def test_strategy_declares_one_candle_cooldown():
    assert SMC_FVG_Context30m_Freqtrade({}).protections == [
        {"method": "CooldownPeriod", "stop_duration_candles": 1}
    ]
