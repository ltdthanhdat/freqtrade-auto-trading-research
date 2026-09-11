from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from .collectors import COLLECTORS, ProviderError, ProviderRetryableError
from .core import HypothesisState
from .store import CANDIDATE_BUDGET, HYPOTHESIS_BUDGET, SOURCE_BUDGET, ResearchStore


class ResearchService:
    """Typed application boundary used by Pi and the local dashboard."""

    OPERATION_FIELDS = {
        "start_or_resume_cycle": {"now"},
        "load_context": {"cycle_id"},
        "collect_sources": {"cycle_id", "provider", "query", "limit"},
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
        "collect_sources": {"cycle_id", "provider", "query", "limit"},
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
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.store = store
        self.artifact_root = Path(artifact_root)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.collectors = COLLECTORS if collectors is None else collectors
        self.validator = validator
        self.sleeper = sleeper

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
            "budgets": {
                "sources": SOURCE_BUDGET,
                "hypotheses": HYPOTHESIS_BUDGET,
                "candidates": CANDIDATE_BUDGET,
            },
            "usage": {
                "sources": cycle["source_count"],
                "hypotheses": cycle["hypothesis_count"],
                "candidates": cycle["candidate_count"],
            },
        }

    def collect_sources(self, payload: dict[str, Any]) -> dict[str, Any]:
        cycle_id = payload["cycle_id"]
        cycle = self.store.get_cycle(cycle_id)
        if cycle is None:
            raise ValueError(f"unknown cycle: {cycle_id}")
        provider = payload["provider"]
        query = payload["query"]
        limit = payload["limit"]
        if not isinstance(provider, str) or not provider.strip():
            raise ValueError("provider is required")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query is required")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= SOURCE_BUDGET:
            raise ValueError(f"limit must be between 1 and {SOURCE_BUDGET}")
        remaining = SOURCE_BUDGET - cycle["source_count"]
        if limit > remaining:
            raise ValueError(f"source budget remaining: {remaining}")
        collector = self.collectors.get(provider.strip())
        if collector is None:
            raise ValueError(f"unsupported provider: {provider}")

        records = None
        for attempt in range(3):
            try:
                records = collector(query.strip(), limit)
                break
            except ProviderRetryableError as exc:
                if attempt == 2:
                    return self._provider_failure(cycle_id, provider, "retry_exhausted", exc, attempt + 1)
                self.sleeper(float(attempt + 1))
            except ProviderError as exc:
                return self._provider_failure(cycle_id, provider, "provider_error", exc, attempt + 1)
        if records is None:
            return self._provider_failure(cycle_id, provider, "provider_error", RuntimeError("no result"), 3)

        accepted_ids: list[str] = []
        duplicate_ids: list[str] = []
        for record in list(records)[:remaining]:
            result = self.store.insert_source(cycle_id, record)
            if result["inserted"]:
                accepted_ids.append(result["id"])
            else:
                duplicate_ids.append(result["id"])
        return {
            "accepted_ids": accepted_ids,
            "duplicate_ids": duplicate_ids,
            "provider_errors": [],
        }

    def _provider_failure(
        self, cycle_id: str, provider: str, code: str, error: Exception, attempts: int
    ) -> dict[str, Any]:
        details = str(error) or type(error).__name__
        self.store.append_cycle_event(
            cycle_id,
            to_state=self.store.get_cycle(cycle_id)["status"],
            actor="runtime",
            reason="source collection failed",
            payload={"provider": provider, "code": code, "attempts": attempts, "details": details},
        )
        return {
            "accepted_ids": [],
            "duplicate_ids": [],
            "provider_errors": [{"provider": provider, "code": code, "details": [details]}],
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
