from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable

from .candidates import write_candidate
from .collectors import COLLECTORS, ProviderError, ProviderRetryableError
from .core import HypothesisState
from .store import CANDIDATE_BUDGET, HYPOTHESIS_BUDGET, SOURCE_BUDGET, ResearchStore
from .validation import ResearchVerdict, validate_candidate


class ResearchService:
    """Typed application boundary used by Pi and the local dashboard."""

    OPERATION_FIELDS = {
        "start_or_resume_cycle": {
            "now", "dataset", "requested_timerange", "policy_sha256", "search_cohort",
            "holdout_start", "holdout_end",
        },
        "load_context": {"cycle_id"},
        "collect_sources": {"cycle_id", "provider", "query", "limit"},
        "write_candidate": {"cycle_id", "hypothesis_id", "strategy_name", "source"},
        "start_validation": {
            "cycle_id", "hypothesis_id", "experiment",
            "id", "parent_strategy", "parent_sha256", "changed_variable",
            "parent_strategy_path",
            "config_path", "config_sha256", "pairs", "timeframes", "timeframe_detail",
            "snapshot_path", "snapshot_sha256", "policy_path", "policy_sha256",
            "strategy_name", "strategy_path", "strategy_file", "candidate_path",
            "start_at", "end_at", "runs_dir", "artifact_root",
        },
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
        "write_candidate": {"cycle_id", "hypothesis_id", "strategy_name", "source"},
        "start_validation": {"cycle_id", "hypothesis_id"},
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
        values = dict(payload or {})
        if values.get("dataset") and values.get("requested_timerange") and not values.get("policy_sha256"):
            policy_path = Path("config/validation.baseline.json")
            if policy_path.is_file():
                values["policy_sha256"] = hashlib.sha256(policy_path.read_bytes()).hexdigest()
        return self.store.start_or_resume_cycle(values)

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
        assessment = payload["assessment"]
        if isinstance(assessment, dict):
            missing = [key for key in ("relevance", "asset", "timeframe", "mechanism") if not assessment.get(key)]
            if missing:
                raise ValueError(f"source assessment missing fields: {', '.join(missing)}")
            if str(assessment["relevance"]).casefold() not in {
                "direct", "directly_relevant", "relevant", "indirect", "contradicting", "falsifier", "irrelevant"
            }:
                raise ValueError("invalid source assessment relevance")
        self.store.update_source_metadata(
            source_id, assessment if isinstance(assessment, dict) else {"assessment": assessment}
        )
        return {"source_id": source_id, "recorded": True}

    def write_candidate(self, payload: dict[str, Any]) -> dict[str, Any]:
        cycle_id = payload["cycle_id"]
        cycle = self.store.get_cycle(cycle_id)
        if cycle is None:
            raise ValueError(f"unknown cycle: {cycle_id}")
        hypothesis = self.store.get_hypothesis(payload["hypothesis_id"])
        if hypothesis is None or hypothesis["cycle_id"] != cycle_id:
            raise ValueError(f"unknown hypothesis: {payload['hypothesis_id']}")
        if not self._hypothesis_data_supported(hypothesis):
            raise ValueError("candidate requires OHLCV-supported required data")
        if not self._has_candidate_evidence(hypothesis["id"]):
            raise ValueError("candidate requires full-text or corroborating independent evidence")
        eligible = [
            item
            for item in self.store.list_hypotheses(cycle_id)
            if item["state"] in {HypothesisState.SCORED, HypothesisState.IMPLEMENTING}
            and self._hypothesis_data_supported(item)
            and self._has_candidate_evidence(item["id"])
        ]
        if not eligible or eligible[0]["id"] != hypothesis["id"]:
            raise ValueError("only the highest-scoring eligible hypothesis may create a candidate")
        if hypothesis["state"] == HypothesisState.SCORED:
            self.store.transition_hypothesis(
                hypothesis["id"], HypothesisState.QUEUED, "runtime", "selected highest-scoring hypothesis", cycle_id
            )
            self.store.transition_hypothesis(
                hypothesis["id"], HypothesisState.IMPLEMENTING, "runtime", "writing candidate", cycle_id
            )
        identity = write_candidate(
            self.artifact_root,
            cycle_id,
            payload["strategy_name"],
            payload["source"],
        )
        updated = self.store.set_candidate(hypothesis["id"], identity.path, identity.sha256)
        return {
            "candidate": {
                "path": str(identity.path),
                "sha256": identity.sha256,
                "strategy_name": identity.strategy_name,
            },
            "hypothesis": updated,
        }

    def _hypothesis_data_supported(self, hypothesis: dict[str, Any]) -> bool:
        try:
            required_data = json.loads(hypothesis["required_data_json"])
        except (KeyError, json.JSONDecodeError):
            return False
        return isinstance(required_data, list) and bool(required_data) and all(
            str(item).upper() == "OHLCV" for item in required_data
        )

    def _has_candidate_evidence(self, hypothesis_id: str) -> bool:
        supporting = [
            source
            for source in self.store.list_hypothesis_sources(hypothesis_id)
            if source["stance"] == "SUPPORT"
        ]
        if not supporting:
            return False
        providers: set[str] = set()
        hardening_metadata = False
        direct_support = False
        for source in supporting:
            try:
                metadata = json.loads(source["metadata_json"])
            except json.JSONDecodeError:
                continue
            if not isinstance(metadata, dict) or metadata.get("falsifier_only") is True:
                continue
            hardening_metadata = hardening_metadata or any(
                key in metadata for key in ("relevance", "asset", "timeframe", "mechanism")
            )
            if str(metadata.get("relevance", "")).casefold() in {
                "direct", "directly_relevant", "relevant"
            }:
                direct_support = True
            if metadata.get("full_text") is True or metadata.get("full_text_available") is True:
                direct_support = True
            providers.add(str(source["provider"]))
        if not hardening_metadata:
            return len(providers) >= 2 or direct_support
        if not direct_support:
            return False
        contradicting = [
            source
            for source in self.store.list_hypothesis_sources(hypothesis_id)
            if source["stance"] == "CONTRADICT"
        ]
        return any(
            str(metadata.get("relevance", "")).casefold()
            in {"direct", "directly_relevant", "relevant", "contradicting", "falsifier"}
            and not metadata.get("irrelevant")
            for source in contradicting
            if isinstance(metadata := self._source_metadata(source), dict)
        )

    @staticmethod
    def _source_metadata(source: dict[str, Any]) -> dict[str, Any]:
        try:
            value = json.loads(source.get("metadata_json", "{}"))
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    def start_validation(self, payload: dict[str, Any]) -> dict[str, Any]:
        cycle_id = payload["cycle_id"]
        hypothesis = self.store.get_hypothesis(payload["hypothesis_id"])
        if hypothesis is None or hypothesis["cycle_id"] != cycle_id:
            raise ValueError(f"unknown hypothesis: {payload['hypothesis_id']}")
        if not hypothesis["candidate_path"] or not hypothesis["candidate_sha256"]:
            raise ValueError("candidate identity is required before validation")
        candidate_file = Path(hypothesis["candidate_path"])
        if not candidate_file.is_file():
            raise ValueError("candidate path does not exist")
        if hashlib.sha256(candidate_file.read_bytes()).hexdigest() != hypothesis["candidate_sha256"]:
            raise ValueError("candidate identity changed after registration")
        cycle = self.store.get_cycle(cycle_id)
        if cycle is None:
            raise ValueError(f"unknown cycle: {cycle_id}")
        existing = self.store.find_experiment(cycle_id, hypothesis["id"])
        if existing is None:
            experiment = self._experiment_payload(payload, cycle_id, hypothesis)
            existing = self.store.insert_experiment(experiment)
        runs = self.store.list_runs(existing["id"])
        if runs and hypothesis["state"] != HypothesisState.TESTING:
            latest = runs[-1]
            if latest["status"] != "RETRYABLE":
                return self._validation_result(latest, hypothesis["state"], existing["id"])
        if hypothesis["state"] in {
            HypothesisState.NEEDS_REVIEW,
            HypothesisState.INCONCLUSIVE,
            HypothesisState.REJECTED,
            HypothesisState.APPROVED_FOR_DRY_RUN,
        }:
            return {"state": hypothesis["state"], "experiment_id": existing["id"]}
        if hypothesis["state"] == HypothesisState.IMPLEMENTING:
            self.store.transition_hypothesis(
                hypothesis["id"], HypothesisState.TESTING, "runtime", "validation started", cycle_id
            )
        elif hypothesis["state"] != HypothesisState.TESTING:
            raise ValueError(f"hypothesis is not ready for validation: {hypothesis['state']}")

        try:
            validation_experiment = {
                **existing,
                "candidate_path": hypothesis["candidate_path"],
                "cycle_id": cycle_id,
                "hypothesis_id": hypothesis["id"],
            }
            result = (
                self.validator(validation_experiment)
                if self.validator is not None
                else validate_candidate(validation_experiment, artifact_root=self.artifact_root)
            )
        except Exception as exc:  # pragma: no cover - validator boundary is tested through the wrapper
            result = ResearchVerdict(
                verdict="RETRYABLE", state="RETRYABLE", metrics={}, artifacts={},
                error_code="validation_exception", details=(f"{type(exc).__name__}: {exc}",),
            )
        normalized = self._normalize_validation_result(result)
        contaminated = self.store.window_is_contaminated(
            dataset=cycle.get("dataset"),
            requested_timerange=cycle.get("requested_timerange"),
            policy_sha256=cycle.get("policy_sha256"),
        )
        if contaminated and normalized["verdict"] == "PASS":
            normalized["verdict"] = "WARN"
            normalized["state"] = "INCONCLUSIVE"
            normalized["metrics"] = {**normalized.get("metrics", {}), "research_only": True}
            normalized["artifacts"] = {**normalized.get("artifacts", {}), "research_only": True}
            self._mark_manifest_research_only(normalized["artifacts"])
        run_id = f"RUN-{existing['id']}-attempt-{len(runs) + 1:02d}"
        run = self.store.record_run(
            {
                "id": run_id,
                "experiment_id": existing["id"],
                "kind": "validation",
                "status": normalized["state"],
                "verdict": normalized["verdict"],
                "metrics": normalized["metrics"],
                "artifact_manifest": normalized["artifacts"],
                "error_code": normalized.get("error_code"),
            }
        )
        self.store.record_validation_window(
            cycle_id=cycle_id,
            dataset=cycle.get("dataset"),
            requested_timerange=cycle.get("requested_timerange"),
            policy_sha256=cycle.get("policy_sha256"),
            verdict=normalized["verdict"],
        )
        if normalized["state"] == "RETRYABLE":
            return self._validation_result(run, "RETRYABLE", existing["id"])
        target = HypothesisState(normalized["state"])
        updated = self.store.transition_hypothesis(
            hypothesis["id"], target, "runtime", f"validation verdict {normalized['verdict']}", cycle_id, run_id,
            payload={"verdict": normalized["verdict"], "metrics": normalized["metrics"]},
        )
        return self._validation_result(run, updated["state"], existing["id"])

    def _experiment_payload(
        self, payload: dict[str, Any], cycle_id: str, hypothesis: dict[str, Any]
    ) -> dict[str, Any]:
        spec = dict(payload.get("experiment") or {})
        for key in self.OPERATION_FIELDS["start_validation"] - {"cycle_id", "hypothesis_id", "experiment"}:
            if key in payload:
                spec[key] = payload[key]
        candidate_path = Path(hypothesis["candidate_path"])
        if not spec:
            if self.validator is None:
                raise ValueError("experiment identity is required before validation")
            digest = hypothesis["candidate_sha256"]
            spec = {
                "id": f"EXP-{hypothesis['id']}",
                "parent_strategy": "fixture",
                "parent_sha256": digest,
                "changed_variable": "research-generated",
                "config_path": "fixture-config",
                "config_sha256": digest,
                "pairs": [],
                "timeframes": ["30m"],
                "timeframe_detail": "1m",
                "snapshot_path": "fixture-snapshot",
                "snapshot_sha256": digest,
                "policy_path": "fixture-policy",
                "policy_sha256": digest,
                "strategy_name": candidate_path.stem,
                "strategy_path": str(candidate_path.parent),
                "candidate_path": str(candidate_path),
                "start_at": hypothesis["created_at"],
                "end_at": hypothesis["updated_at"],
                "status": "PENDING",
            }
        spec.update(
            {
                "cycle_id": cycle_id,
                "hypothesis_id": hypothesis["id"],
                "strategy_name": spec.get("strategy_name") or candidate_path.stem,
                "strategy_path": spec.get("strategy_path") or str(candidate_path.parent),
                "strategy_file": spec.get("strategy_file") or str(candidate_path),
                "candidate_path": spec.get("candidate_path") or str(candidate_path),
                "status": spec.get("status", "PENDING"),
                "start_at": spec.get("start_at", hypothesis["created_at"]),
                "end_at": spec.get("end_at", hypothesis["updated_at"]),
            }
        )
        required = (
            "parent_strategy", "parent_sha256", "changed_variable", "config_path", "config_sha256",
            "pairs", "timeframes", "timeframe_detail", "snapshot_path", "snapshot_sha256",
            "policy_path", "policy_sha256", "strategy_name", "strategy_path", "start_at", "end_at",
        )
        missing = [
            key
            for key in required
            if key not in spec
            or spec[key] is None
            or (isinstance(spec[key], str) and not spec[key].strip())
        ]
        if missing:
            raise ValueError(f"missing experiment fields: {', '.join(missing)}")
        return spec

    @staticmethod
    def _normalize_validation_result(result: Any) -> dict[str, Any]:
        if isinstance(result, ResearchVerdict):
            return {
                "verdict": result.verdict,
                "state": result.state,
                "metrics": result.metrics,
                "artifacts": {
                    **result.artifacts,
                    "manifest_path": str(result.manifest_path) if result.manifest_path else None,
                    "report_path": str(result.report_path) if result.report_path else None,
                    "manifest_sha256": result.manifest_hash,
                    "report_sha256": result.report_hash,
                },
                "error_code": result.error_code,
            }
        value = dict(result) if isinstance(result, dict) else {
            "verdict": getattr(result, "verdict", "RETRYABLE"),
            "metrics": getattr(result, "metrics", {}),
            "artifacts": getattr(result, "artifacts", {}),
        }
        verdict = str(value.get("verdict", "RETRYABLE"))
        state = {"PASS": "NEEDS_REVIEW", "WARN": "INCONCLUSIVE", "FAIL": "REJECTED"}.get(verdict, "RETRYABLE")
        value["verdict"] = verdict
        value["state"] = state
        value.setdefault("metrics", {})
        value.setdefault("artifacts", {})
        return value

    @staticmethod
    def _mark_manifest_research_only(artifacts: dict[str, Any]) -> None:
        path = artifacts.get("manifest_path")
        if not path:
            return
        manifest_path = Path(str(path))
        if not manifest_path.is_file():
            return
        try:
            manifest = json.loads(manifest_path.read_text())
            if isinstance(manifest, dict):
                manifest["research_only"] = True
                manifest["research_window_contaminated"] = True
                manifest_path.write_text(json.dumps(manifest, indent=2, default=str) + "\n")
                artifacts["manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        except (OSError, json.JSONDecodeError):
            return

    @staticmethod
    def _validation_result(run: dict[str, Any], state: str, experiment_id: str) -> dict[str, Any]:
        try:
            metrics = json.loads(run["metrics_json"])
            artifacts = json.loads(run["artifact_manifest_json"])
        except (KeyError, json.JSONDecodeError):
            metrics, artifacts = {}, {}
        return {
            "state": state,
            "verdict": run.get("verdict"),
            "run_id": run.get("id"),
            "experiment_id": experiment_id,
            "metrics": metrics,
            "artifacts": artifacts,
            "error_code": run.get("error_code"),
        }

    def propose_hypothesis(self, payload: dict[str, Any]) -> dict[str, Any]:
        cycle_id = payload["cycle_id"]
        cycle = self.store.get_cycle(cycle_id)
        if cycle is None:
            raise ValueError(f"unknown cycle: {cycle_id}")
        required_data = payload["required_data"]
        if not isinstance(required_data, list) or not required_data:
            raise ValueError("required_data must be a non-empty list")
        if cycle.get("search_cohort") and [str(item).upper() for item in required_data] != ["OHLCV"]:
            raise ValueError("identity-bound hypothesis requires required_data exactly [OHLCV]")
        source_ids = list(payload.get("supporting_source_ids", [])) + list(
            payload.get("contradicting_source_ids", [])
        )
        if cycle.get("search_cohort") and (
            not payload.get("supporting_source_ids") or not payload.get("contradicting_source_ids")
        ):
            raise ValueError("identity-bound hypothesis requires structured evidence")
        for source_id in source_ids:
            source = self.store.get_source(source_id)
            if source is None or source["cycle_id"] != cycle_id:
                raise ValueError(f"source provenance missing: {source_id}")
            if cycle.get("search_cohort"):
                metadata = self._source_metadata(source)
                if any(not metadata.get(key) for key in ("relevance", "asset", "timeframe", "mechanism")):
                    raise ValueError(f"structured evidence assessment missing: {source_id}")
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
            to_state=self.store.get_cycle(payload["cycle_id"])["status"],
            actor="runtime",
            reason="interpretation",
            payload={"hypothesis_id": hypothesis["id"], "interpretation": payload["interpretation"]},
        )
        return {"recorded": True, "event_id": event}

    def finalize_cycle(self, payload: dict[str, Any]) -> dict[str, Any]:
        cycle = self.store.set_cycle_status(payload["cycle_id"], payload["status"], payload["reason"])
        return {"cycle": cycle}
