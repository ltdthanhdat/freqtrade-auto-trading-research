import pytest

from research_runtime.core import (
    HypothesisState,
    canonical_json,
    next_state_allowed,
    score_hypothesis,
)


def test_score_is_sum_of_frozen_dimensions():
    assert score_hypothesis(
        evidence_quality=30,
        reproducibility=20,
        ohlcv_transferability=15,
        novelty=10,
        falsifiability=5,
    ) == 80


def test_score_rejects_a_dimension_above_its_weight():
    with pytest.raises(ValueError, match="evidence_quality"):
        score_hypothesis(31, 20, 15, 10, 5)


def test_score_rejects_boolean_dimensions():
    with pytest.raises(ValueError, match="evidence_quality"):
        score_hypothesis(True, 20, 15, 10, 5)


def test_review_is_the_only_path_to_dry_run_eligibility():
    assert next_state_allowed(HypothesisState.NEEDS_REVIEW, HypothesisState.APPROVED_FOR_DRY_RUN)
    assert not next_state_allowed(HypothesisState.TESTING, HypothesisState.APPROVED_FOR_DRY_RUN)


def test_terminal_states_cannot_be_reopened():
    assert not next_state_allowed(HypothesisState.REJECTED, HypothesisState.QUEUED)
    assert not next_state_allowed(HypothesisState.APPROVED_FOR_DRY_RUN, HypothesisState.TESTING)


def test_canonical_json_is_stable():
    assert canonical_json({"b": 1, "a": [True, None]}) == '{"a":[true,null],"b":1}'
