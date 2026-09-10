import os
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from scripts.validation_core import (
    Checks,
    FoldMetrics,
    ValidationPolicy,
    ValidationStateStore,
    evaluate_verdict,
    time_blocks,
)
from scripts.validate_baseline import _fold_metrics


@pytest.mark.parametrize("module", ["scripts.validate_baseline", "scripts.monitor_decay"])
def test_documented_module_help_without_pythonpath(module):
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    result = subprocess.run([sys.executable, "-m", module, "--help"], env=env, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert f"-m {module}" in Path("Makefile").read_text()


@pytest.mark.parametrize("state", ["YELLOW", "PAIR_OR_SIDE_LOCKED", "ACTIVE"])
def test_paused_cannot_escape_through_intermediate_state(tmp_path, state):
    store = ValidationStateStore(tmp_path / "state.sqlite")
    store.transition("global", "PAUSED", "red", {}, None, "run")
    with pytest.raises(ValueError, match="review"):
        store.transition("global", state, "timer", {}, None, "run")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_evidence_never_passes(value):
    policy = ValidationPolicy(1, 1, 3, 100, .15, .001, .0005, 7, 10, "2W")
    folds = [FoldMetrics(100, value, 0) for _ in range(3)]
    assert evaluate_verdict(Checks(True, True, True), folds, 0, policy) == "FAIL"


def test_fold_includes_initial_equity_and_uses_absolute_profit():
    trades = pd.DataFrame({"profit_ratio": [-.2, .5], "profit_abs": [-200, 50],
                           "close_date": ["2025-01-01", "2025-01-02"]})
    trades.attrs["starting_balance"] = 1000
    metrics = _fold_metrics(trades)
    assert metrics.max_drawdown == pytest.approx(.2)
    assert metrics.net_profit == pytest.approx(-.15)


def test_two_week_blocks_are_fixed_monday_anchored_intervals():
    dates = pd.Series(pd.to_datetime(["1970-01-05", "1970-01-18", "1970-01-19"], utc=True))

    assert time_blocks(dates).tolist() == [0, 0, 1]
