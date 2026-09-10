from __future__ import annotations

from src.strategies.SMC_FVG_Confirmation_Freqtrade import SMC_FVG_Confirmation_Freqtrade


class SMC_FVG_1h_Baseline_Freqtrade(SMC_FVG_Confirmation_Freqtrade):
    """H021 diagnostic: pure 1h FVG confirmation without the 30m hybrid layer."""

    timeframe = "1h"
    startup_candle_count = 4

    def __init__(self, config: dict):
        if "candle_type_def" not in config:
            config = {**config, "candle_type_def": "futures"}
        super().__init__(config)

    @property
    def protections(self) -> list[dict[str, int | str]]:
        return [{"method": "CooldownPeriod", "stop_duration_candles": 1}]
