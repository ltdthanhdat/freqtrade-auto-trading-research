from __future__ import annotations

import os
from pathlib import Path


_DEFAULT_STATE_DIR = Path.home() / "workspace/iac/sqlite/freqtrade-auto-trading-research"


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    if value is None:
        return None
    if not value.strip():
        raise ValueError(f"{name} must not be empty")
    return Path(value).expanduser()


def default_state_dir() -> Path:
    return _env_path("RESEARCH_STATE_DIR") or _DEFAULT_STATE_DIR


def research_db_path() -> Path:
    return _env_path("RESEARCH_DB") or default_state_dir() / "research.sqlite"


def validation_state_db_path() -> Path:
    return _env_path("VALIDATION_STATE_DB") or default_state_dir() / "validation-state.sqlite"


def research_artifact_root() -> Path:
    return _env_path("RESEARCH_ARTIFACT_ROOT") or Path("user_data/research-artifacts")
