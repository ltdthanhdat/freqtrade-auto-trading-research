from pathlib import Path

import pandas as pd
import pytest

from scripts.validation_core import (
    Checks,
    FoldMetrics,
    ValidationPolicy,
    complete_plan_metrics,
    bootstrap_equity_paths,
    build_oos_folds,
    evaluate_verdict,
)


@pytest.fixture
def policy() -> ValidationPolicy:
    return ValidationPolicy(120, 30, 3, 100, 0.15, 0.001, 0.0005, 7, 20_000, "2W")


def test_policy_loads_frozen_values():
    loaded = ValidationPolicy.from_path(Path("config/validation.baseline.json"))

    assert loaded.in_sample_days == 120
    assert loaded.oos_days == 30
    assert loaded.required_folds == 3
    assert loaded.min_positive_oos_folds == 2
    assert loaded.min_oos_trades == 100
    assert loaded.max_drawdown == 0.15
    assert loaded.stress_fee == 0.001
    assert loaded.slippage_per_side == 0.0005
    assert loaded.bootstrap_seed == 7
    assert loaded.bootstrap_samples == 20_000
    assert loaded.bootstrap_block == "2W"
    assert loaded.accepted_pairs == (
        "PLAY/USDT:USDT",
        "BIO/USDT:USDT",
        "SPACE/USDT:USDT",
        "PENDLE/USDT:USDT",
        "BR/USDT:USDT",
        "YGG/USDT:USDT",
    )


def test_oos_folds_are_chronological_and_non_overlapping(policy):
    folds = build_oos_folds(
        pd.Timestamp("2025-01-01", tz="UTC"),
        pd.Timestamp("2025-08-01", tz="UTC"),
        policy,
    )
    assert len(folds) == 3
    assert folds[0].oos_end <= folds[1].oos_start
    assert all(folds[index].oos_end <= folds[index + 1].oos_start for index in range(2))


def test_bootstrap_equity_paths_are_deterministic(policy):
    trades = pd.DataFrame(
        {
            "open_date": pd.date_range("2026-01-01", periods=8, freq="D"),
            "profit_ratio": [0.01, -0.02] * 4,
        }
    )

    assert bootstrap_equity_paths(trades, policy) == bootstrap_equity_paths(trades, policy)


def test_bootstrap_equity_paths_resamples_stressed_whole_blocks():
    policy = ValidationPolicy(120, 30, 3, 100, 0.15, 0.001, 0.0005, 7, 1, "2W")
    trades = pd.DataFrame(
        {
            "open_date": pd.to_datetime(
                ["2026-01-01", "2026-01-02", "2026-01-20", "2026-01-21", "2026-01-22"]
            ),
            "profit_ratio": [0.04, 0.03, 0.01, -0.02, 0.02],
        }
    )

    summary = bootstrap_equity_paths(trades, policy)

    assert summary.p95_max_drawdown == pytest.approx(0.021)
    assert summary.p05_net_profit == pytest.approx(0.0132021066227888)
    assert summary.p95_losing_streak == 1


def test_complete_plan_metrics_are_deterministic_and_cover_risk_exit_fields(policy):
    trades = pd.DataFrame(
        {
            "exit_reason": ["STOP_LOSS", "PROFIT_TARGET"],
            "planned_loss": [1.0, 2.0],
            "realized_r": [-1.5, 1.0],
            "open_rate": [10.0, 10.0],
            "initial_stop_rate": [9.0, 11.0],
            "is_short": [False, True],
            "open_date": pd.to_datetime(["2026-01-01", "2026-01-02"], utc=True),
            "close_date": pd.to_datetime(["2026-01-03", "2026-01-04"], utc=True),
            "stake_amount": [100.0, 200.0],
            "fee_open": [1.0, 2.0],
            "fee_close": [1.0, 2.0],
            "mae": [-0.1, -0.2],
            "mfe": [0.2, 0.4],
        }
    )
    metrics = complete_plan_metrics(trades, policy)

    assert metrics["exit_coverage"] == pytest.approx(1.0)
    assert metrics["risk_ledger"]["coverage"] == pytest.approx(1.0)
    assert metrics["risk_ledger"]["concurrent_planned_risk"] == pytest.approx(3.0)
    assert metrics["net_realized_r"] == pytest.approx(-0.5)
    assert metrics["loss_overrun_p95"] == pytest.approx(0.475)
    assert metrics["risk_safety"]["wrong_side_or_missing_initial_stops"] == 0
    assert metrics["costs"]["fees"] == pytest.approx(6.0)
    assert metrics["holding_duration"]["count"] == 2
    assert metrics == complete_plan_metrics(trades, policy)


def test_verdict_fails_on_drawdown_breach(policy):
    assert evaluate_verdict(
        Checks(True, True, True), [FoldMetrics(100, 0.02, 0.151)], 0.10, policy
    ) == "FAIL"


def test_verdict_passes_when_all_frozen_gates_pass(policy):
    folds = [FoldMetrics(100, 0.02, 0.15) for _ in range(3)]
    assert evaluate_verdict(Checks(True, True, True), folds, 0.15, policy) == "PASS"


def test_verdict_requires_two_positive_stressed_folds(policy):
    folds = [
        FoldMetrics(34, 0.03, 0.08),
        FoldMetrics(33, -0.01, 0.09),
        FoldMetrics(33, 0.00, 0.07),
    ]
    assert evaluate_verdict(Checks(True, True, True), folds, 0.10, policy) == "FAIL"


def test_zero_aggregate_stressed_profit_fails(policy):
    folds = [
        FoldMetrics(34, 0.01, 0.08),
        FoldMetrics(33, -0.01, 0.08),
        FoldMetrics(33, 0.0, 0.08),
    ]
    assert evaluate_verdict(Checks(True, True, True), folds, 0.10, policy) == "FAIL"


@pytest.mark.parametrize("value", [0, 4, True])
def test_policy_rejects_invalid_positive_fold_threshold(value):
    with pytest.raises(ValueError, match="min_positive_oos_folds"):
        ValidationPolicy(120, 30, 3, 100, 0.15, 0.001, 0.0005, 7, 20_000, "2W", min_positive_oos_folds=value)


def test_verdict_warns_when_evidence_is_insufficient(policy):
    assert evaluate_verdict(
        Checks(True, True, True), [FoldMetrics(99, 0.02, 0.02)], 0.10, policy
    ) == "WARN"
