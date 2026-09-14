import inspect
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures" / "rsi_candidates"))

from src.strategies.SMC_FVG_Confirmation_Freqtrade import SMC_FVG_Confirmation_Freqtrade
from src.strategies.SMC_FVG_Context30m_Freqtrade import SMC_FVG_Context30m_Freqtrade
from FuturesRiskBase_Freqtrade import FuturesRiskBase_Freqtrade
from scripts.validate_baseline import collect_identity
from RSI_Divergence30m_Freqtrade import RSI_Divergence30m_Freqtrade


class Wallet:
    def get_available_stake_amount(self):
        return 1000.0

    def get_total_stake_amount(self):
        raise AssertionError("context sizing must not use total historical stake")


class NoCandleDataProvider:
    def get_analyzed_dataframe(self, **_kwargs):
        raise AssertionError("context callbacks must not read the current candle")


class Trade:
    is_short = False
    enter_tag = "pin_bar|95.0"
    open_rate = 100.0
    leverage = 5.0

    def __init__(self):
        self.custom = {}

    def get_custom_data(self, key, default=None):
        return self.custom.get(key, default)

    def set_custom_data(self, key, value):
        self.custom[key] = value


def config():
    return json.loads(Path("config/config.futures.json").read_text())


def test_smc_strategies_load_and_expose_stable_validation_metadata():
    base = SMC_FVG_Confirmation_Freqtrade(config())
    context = SMC_FVG_Context30m_Freqtrade(config())

    base_metadata = base.validation_metadata()
    context_metadata = context.validation_metadata()

    assert base_metadata == base.validation_metadata()
    assert base_metadata["strategy_name"] == "SMC_FVG_Confirmation_Freqtrade"
    assert context_metadata["strategy_name"] == "SMC_FVG_Context30m_Freqtrade"
    assert len(base_metadata["config_sha256"]) == 64
    assert len(context_metadata["config_sha256"]) == 64
    assert context_metadata == context.validation_metadata()
    assert base_metadata["risk_formula_version"] == "smc-risk-v1"
    assert base_metadata["plan_version"] == 1
    assert base_metadata["exit_plan_version"] == 1


def test_smc_load_gate_rejects_missing_or_nonfinite_risk_configuration():
    broken = config()
    broken.pop("smc_stop_slippage_rate")
    with pytest.raises(ValueError, match="SMC risk configuration"):
        SMC_FVG_Confirmation_Freqtrade(broken)

    broken = config()
    broken["smc_entry_fee_rate"] = float("nan")
    with pytest.raises(ValueError, match="SMC risk configuration"):
        SMC_FVG_Confirmation_Freqtrade(broken)


def test_identity_collection_rejects_missing_smc_config_before_validation(tmp_path):
    broken = config()
    broken.pop("smc_entry_fee_rate")
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(broken))
    policy_path = tmp_path / "policy.json"
    policy_path.write_text("{}")

    with pytest.raises(ValueError, match="SMC risk configuration"):
        collect_identity(
            config_path,
            Path("src/strategies/SMC_FVG_Confirmation_Freqtrade.py"),
            None,
            policy_path,
            "SMC_FVG_Confirmation_Freqtrade",
            Path("src/strategies"),
        )


def test_context_preserves_timeframe_informative_filter_and_protection_contract():
    context = SMC_FVG_Context30m_Freqtrade(config())
    source = inspect.getsource(SMC_FVG_Context30m_Freqtrade)

    assert context.timeframe == "30m"
    assert context.can_short is True
    assert hasattr(context, "populate_indicators_1h")
    assert context.protections == [{"method": "CooldownPeriod", "stop_duration_candles": 1}]
    assert "close_1h" in source
    assert "ema20_slope_1h" in source
    assert 'startswith("displacement|")' in source


def test_context_tag_reaches_inherited_callbacks_without_candle_lookup():
    context = SMC_FVG_Context30m_Freqtrade(config())
    context.wallets = Wallet()
    context.dp = NoCandleDataProvider()

    stake = context.custom_stake_amount(
        pair="PLAY/USDT:USDT",
        current_time=None,
        current_rate=100.0,
        proposed_stake=499.0,
        min_stake=1.0,
        max_stake=500.0,
        leverage=5.0,
        entry_tag="pin_bar|95.0",
        side="long",
    )
    trade = Trade()
    roi = context.custom_roi(
        "PLAY/USDT:USDT", trade, None, 1, trade.enter_tag, "long"
    )

    assert stake > 0
    assert roi == 0.25


def test_smc_exit_contract_is_explicit_and_not_shared_with_unrelated_fixtures():
    source = inspect.getsource(SMC_FVG_Confirmation_Freqtrade)

    assert SMC_FVG_Confirmation_Freqtrade.stoploss == -0.99
    assert SMC_FVG_Confirmation_Freqtrade.use_exit_signal is False
    assert "return min(proposed_stake, max_stake)" not in source
    assert "get_analyzed_dataframe" not in source
    assert not issubclass(FuturesRiskBase_Freqtrade, SMC_FVG_Confirmation_Freqtrade)
    assert not issubclass(RSI_Divergence30m_Freqtrade, SMC_FVG_Confirmation_Freqtrade)
    assert not hasattr(FuturesRiskBase_Freqtrade, "_smc_risk_inputs")
    assert not hasattr(RSI_Divergence30m_Freqtrade, "_smc_risk_inputs")
