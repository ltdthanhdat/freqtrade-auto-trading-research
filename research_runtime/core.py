from __future__ import annotations

import json
from enum import StrEnum
from types import MappingProxyType
from typing import Any


class HypothesisState(StrEnum):
    DRAFT = "DRAFT"
    SCORED = "SCORED"
    BACKLOG = "BACKLOG"
    QUEUED = "QUEUED"
    IMPLEMENTING = "IMPLEMENTING"
    TESTING = "TESTING"
    INCONCLUSIVE = "INCONCLUSIVE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REJECTED = "REJECTED"
    APPROVED_FOR_DRY_RUN = "APPROVED_FOR_DRY_RUN"


class CycleStatus(StrEnum):
    RUNNING = "RUNNING"
    INTERRUPTED = "INTERRUPTED"
    COMPLETED = "COMPLETED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    INCOMPLETE = "INCOMPLETE"
    FAILED = "FAILED"


SCORE_LIMITS = MappingProxyType(
    {
        "evidence_quality": 30,
        "reproducibility": 25,
        "ohlcv_transferability": 20,
        "novelty": 15,
        "falsifiability": 10,
    }
)

_TRANSITIONS = MappingProxyType(
    {
        HypothesisState.DRAFT: frozenset({HypothesisState.SCORED}),
        HypothesisState.SCORED: frozenset(
            {HypothesisState.BACKLOG, HypothesisState.REJECTED, HypothesisState.QUEUED}
        ),
        HypothesisState.QUEUED: frozenset({HypothesisState.IMPLEMENTING}),
        HypothesisState.IMPLEMENTING: frozenset({HypothesisState.TESTING}),
        HypothesisState.TESTING: frozenset(
            {HypothesisState.REJECTED, HypothesisState.INCONCLUSIVE, HypothesisState.NEEDS_REVIEW}
        ),
        HypothesisState.NEEDS_REVIEW: frozenset(
            {HypothesisState.REJECTED, HypothesisState.APPROVED_FOR_DRY_RUN}
        ),
        HypothesisState.BACKLOG: frozenset(),
        HypothesisState.INCONCLUSIVE: frozenset(),
        HypothesisState.REJECTED: frozenset(),
        HypothesisState.APPROVED_FOR_DRY_RUN: frozenset(),
    }
)

_CYCLE_TRANSITIONS = MappingProxyType(
    {
        CycleStatus.RUNNING: frozenset(
            {
                CycleStatus.INTERRUPTED,
                CycleStatus.COMPLETED,
                CycleStatus.NEEDS_REVIEW,
                CycleStatus.INCOMPLETE,
                CycleStatus.FAILED,
            }
        ),
        CycleStatus.INTERRUPTED: frozenset(
            {CycleStatus.RUNNING, CycleStatus.INCOMPLETE, CycleStatus.FAILED}
        ),
        CycleStatus.COMPLETED: frozenset(),
        CycleStatus.NEEDS_REVIEW: frozenset({CycleStatus.COMPLETED, CycleStatus.FAILED}),
        CycleStatus.INCOMPLETE: frozenset({CycleStatus.RUNNING}),
        CycleStatus.FAILED: frozenset(),
    }
)


def score_hypothesis(
    evidence_quality: int,
    reproducibility: int,
    ohlcv_transferability: int,
    novelty: int,
    falsifiability: int,
) -> int:
    values = dict(
        zip(
            SCORE_LIMITS,
            (evidence_quality, reproducibility, ohlcv_transferability, novelty, falsifiability),
            strict=True,
        )
    )
    for name, value in values.items():
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= SCORE_LIMITS[name]:
            raise ValueError(f"invalid {name}")
    return sum(values.values())


def next_state_allowed(current: HypothesisState | str, target: HypothesisState | str) -> bool:
    try:
        current_state = HypothesisState(current)
        target_state = HypothesisState(target)
    except ValueError:
        return False
    return target_state in _TRANSITIONS[current_state]


def next_cycle_state_allowed(current: CycleStatus | str, target: CycleStatus | str) -> bool:
    try:
        current_state = CycleStatus(current)
        target_state = CycleStatus(target)
    except ValueError:
        return False
    return target_state in _CYCLE_TRANSITIONS[current_state]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
