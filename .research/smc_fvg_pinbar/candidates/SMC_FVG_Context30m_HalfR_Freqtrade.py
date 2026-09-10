from __future__ import annotations

from src.strategies.SMC_FVG_Context30m_Freqtrade import SMC_FVG_Context30m_Freqtrade


class SMC_FVG_Context30m_HalfR_Freqtrade(SMC_FVG_Context30m_Freqtrade):
    """H018 candidate: keep entries/stops but target half of the initial risk."""

    def custom_roi(
        self,
        pair: str,
        trade,
        current_time,
        trade_duration: int,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float | None:
        target_roi = super().custom_roi(
            pair,
            trade,
            current_time,
            trade_duration,
            entry_tag,
            side,
            **kwargs,
        )
        return None if target_roi is None else float(target_roi) * 0.5
