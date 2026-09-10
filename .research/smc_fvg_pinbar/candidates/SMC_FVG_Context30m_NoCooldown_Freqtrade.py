from __future__ import annotations

from src.strategies.SMC_FVG_Context30m_Freqtrade import SMC_FVG_Context30m_Freqtrade


class SMC_FVG_Context30m_NoCooldown_Freqtrade(SMC_FVG_Context30m_Freqtrade):
    """H019 candidate: remove only the one-candle cooldown protection."""

    @property
    def protections(self) -> list[dict[str, int | str]]:
        return []
