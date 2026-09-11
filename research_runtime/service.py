from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .core import HypothesisState
from .store import ResearchStore


class ResearchService:
    """Typed application boundary used by Pi and the local dashboard."""

    OPERATION_FIELDS = {
        "start_or_resume_cycle": {"now"},
        "load_context": {"cycle_id"},
        "record_source_assessment": {"cycle_id", "source_id", "assessment"},
        "propose_hypothesis": {
            "cycle_id",
            "thesis",
            "mechanism",
            "market_scope",
            "required_data",
            "falsifier",
            "scores",
            "supporting_source_ids",
            "contradicting_source_ids",
            "metadata",
        },
        "record_interpretation": {"cycle_id", "hypothesis_id", "interpretation"},
        "finalize_cycle": {"cycle_id", "status", "reason"},
    }

    REQUIRED_FIELDS = {
        "start_or_resume_cycle": set(),
        "load_context": {"cycle_id"},
        "record_source_assessment": {"cycle_id", "source_id", "assessment"},
        "propose_hypothesis": {
            "cycle_id",
            "thesis",
            "mechanism",
            "market_scope",
            "required_data",
            "falsifier",
            "scores",
        },
        "record_interpretation": {"cycle_id", "hypothesis_id", "interpretation"},
        "finalize_cycle": {"cycle_id", "status", "reason"},
    }

    def __init__(
        self,
        store: ResearchStore,
        artifact_root: str | Path,
        collectors: dict[str, Callable[..., Any]] | None = None,
        validator: Callable[..., Any] | None = None,
    ):
        self.store = store
        self.artifact_root = Path(artifact_root)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.collectors = collectors or {}
        self.validator = validator

    def call(self, tool: str, payload: dict[str, Any]) -> dict[str, Any]:
        if tool not in self.OPERATION_FIELDS:
            raise KeyError(tool)
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        unknown = sorted(set(payload) - self.OPERATION_FIELDS[tool])
        if unknown:
            raise ValueError(f"unknown fields: {', '.join(unknown)}")
        missing = sorted(self.REQUIRED_FIELDS[tool] - set(payload))
        if missing:
            raise ValueError(f"missing fields: {', '.join(missing)}")
        return getattr(self, tool)(payload)

    def start_or_resume_cycle(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.store.start_or_resume_cycle((payload or {}).get("now"))

    def load_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        cycle_id = payload["cycle_id"]
        cycle = self.store.get_cycle(cycle_id)
        if cycle is None:
            raise ValueError(f"unknown cycle: {cycle_id}")
        hypotheses = self.store.list_hypotheses(cycle_id)
        return {
            "cycle": cycle,
            "hypotheses": hypotheses,
            "budgets": {"sources": 100, "hypotheses": 3, "candidates": 1},
            "usage": {
                "sources": cycle["source_count"],
                "hypotheses": cycle["hypothesis_count"],
                "candidates": cycle["candidate_count"],
            },
        }

    def record_source_assessment(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_id = payload["source_id"]
        source = self.store.get_source(source_id)
        if source is None or source["cycle_id"] != payload["cycle_id"]:
            raise ValueError(f"unknown source: {source_id}")
        self.store.update_source_metadata(source_id, {"assessment": payload["assessment"]})
        return {"source_id": source_id, "recorded": True}

    def propose_hypothesis(self, payload: dict[str, Any]) -> dict[str, Any]:
        cycle_id = payload["cycle_id"]
        required_data = payload["required_data"]
        if not isinstance(required_data, list) or not required_data:
            raise ValueError("required_data must be a non-empty list")
        source_ids = list(payload.get("supporting_source_ids", [])) + list(
            payload.get("contradicting_source_ids", [])
        )
        for source_id in source_ids:
            source = self.store.get_source(source_id)
            if source is None or source["cycle_id"] != cycle_id:
                raise ValueError(f"source provenance missing: {source_id}")
        mechanism = str(payload["mechanism"]).strip()
        if not mechanism:
            raise ValueError("mechanism is required")
        existing = self.store.find_hypothesis_by_mechanism(cycle_id, mechanism)
        if existing is not None:
            for source_id in payload.get("supporting_source_ids", []):
                self.store.add_hypothesis_source(existing["id"], source_id, "SUPPORT", "new evidence")
            for source_id in payload.get("contradicting_source_ids", []):
                self.store.add_hypothesis_source(existing["id"], source_id, "CONTRADICT", "new evidence")
            return {"hypothesis": existing, "duplicate": True}
        unsupported = {str(item).upper() for item in required_data} - {"OHLCV"}
        state = HypothesisState.BACKLOG if unsupported else HypothesisState.SCORED
        hypothesis = self.store.insert_hypothesis(cycle_id, {**payload, "state": state})
        for source_id in payload.get("supporting_source_ids", []):
            self.store.add_hypothesis_source(hypothesis["id"], source_id, "SUPPORT", "supporting evidence")
        for source_id in payload.get("contradicting_source_ids", []):
            self.store.add_hypothesis_source(hypothesis["id"], source_id, "CONTRADICT", "contradicting evidence")
        return {"hypothesis": hypothesis, "duplicate": False}

    def record_interpretation(self, payload: dict[str, Any]) -> dict[str, Any]:
        hypothesis = self.store.get_hypothesis(payload["hypothesis_id"])
        if hypothesis is None or hypothesis["cycle_id"] != payload["cycle_id"]:
            raise ValueError(f"unknown hypothesis: {payload['hypothesis_id']}")
        event = self.store.append_cycle_event(
            payload["cycle_id"],
            to_state=hypothesis["state"],
            actor="runtime",
            reason="interpretation",
            payload={"hypothesis_id": hypothesis["id"], "interpretation": payload["interpretation"]},
        )
        return {"recorded": True, "event_id": event}

    def finalize_cycle(self, payload: dict[str, Any]) -> dict[str, Any]:
        cycle = self.store.set_cycle_status(payload["cycle_id"], payload["status"], payload["reason"])
        return {"cycle": cycle}
