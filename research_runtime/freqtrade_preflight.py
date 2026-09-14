from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from freqtrade.exceptions import OperationalException
from freqtrade.resolvers.strategy_resolver import StrategyResolver

from scripts.validate_baseline import _effective_config


@dataclass(frozen=True)
class CandidatePreflightResult:
    passed: bool
    strategy_name: str
    strategy_path: Path
    details: tuple[str, ...] = ()


def preflight_candidate(
    *, config_path: Path, strategy_name: str, strategy_path: Path
) -> CandidatePreflightResult:
    strategy_path = Path(strategy_path).resolve()
    details: tuple[str, ...] = ()
    try:
        config_values = _effective_config(Path(config_path))
        config_values["strategy"] = strategy_name
        config_values["strategy_path"] = str(strategy_path)
        # StrategyResolver searches user_data_dir before strategy_path. A
        # standalone candidate preflight has no Freqtrade user-data tree, so
        # constrain that search to the frozen candidate directory.
        configured_user_data_dir = config_values.get("user_data_dir")
        config_values["user_data_dir"] = (
            Path(str(configured_user_data_dir)).resolve()
            if configured_user_data_dir
            else strategy_path
        )
        strategy = StrategyResolver.load_strategy(config_values)
        StrategyResolver.validate_strategy(strategy)
        loaded_name = type(strategy).__name__
        if loaded_name != strategy_name:
            details = (f"loaded strategy name {loaded_name!r} does not match {strategy_name!r}",)
            return CandidatePreflightResult(False, strategy_name, strategy_path, details)
    except (OperationalException, ImportError, ValueError, TypeError, KeyError) as exc:
        details = (f"{type(exc).__name__}: {exc}",)
        return CandidatePreflightResult(False, strategy_name, strategy_path, details)
    return CandidatePreflightResult(True, strategy_name, strategy_path, details)
