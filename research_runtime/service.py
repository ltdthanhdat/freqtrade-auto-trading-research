from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from .candidates import write_candidate
from .collectors import COLLECTORS, ProviderError, ProviderRetryableError
from .core import HypothesisState
from .plan import canonical_plan_json, plan_sha256, validate_evidence_link, validate_trading_plan
from .store import CANDIDATE_BUDGET, HYPOTHESIS_BUDGET, SOURCE_BUDGET, ResearchStore
from .validation import ResearchVerdict, validate_candidate


class ResearchService:
    """Typed application boundary used by Pi and the local dashboard."""

    OPERATION_FIELDS = {
        "start_or_resume_cycle": {
            "now", "dataset", "requested_timerange", "policy_sha256", "search_cohort",
            "holdout_start", "holdout_end", "lease_owner", "airflow_run_key",
            "snapshot_sha256", "snapshot_manifest_path", "prompt_sha256",
        },
        "heartbeat_cycle": {"cycle_id", "lease_owner", "now"},
        "reconcile_cycle": {
            "cycle_id", "observed_status", "reason", "observed_task_id",
            "observed_container_id", "lease_owner", "now",
        },
        "load_context": {"cycle_id"},
        "list_source_views": {"cycle_id", "limit", "after"},
        "seal_hypothesis_ranking": {"cycle_id"},
        "create_evaluation_cohort": {"cohort", "id", "dataset", "config_sha256", "policy_sha256", "snapshot_sha256", "comparison_start_at", "comparison_end_at", "holdout_start_at", "holdout_end_at", "selection_rule", "members"},
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
            "family_id",
            "trading_plan",
            "evidence_links",
        },
        "record_interpretation": {"cycle_id", "hypothesis_id", "interpretation"},
        "finalize_cycle": {"cycle_id", "status", "reason"},
    }

    REQUIRED_FIELDS = {
        "start_or_resume_cycle": set(),
        "heartbeat_cycle": {"cycle_id", "lease_owner"},
        "reconcile_cycle": {"cycle_id", "observed_status", "reason"},
        "load_context": {"cycle_id"},
        "list_source_views": {"cycle_id"},
        "seal_hypothesis_ranking": {"cycle_id"},
        "create_evaluation_cohort": set(),
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
    ):
        self.store = store
        self.artifact_root = Path(artifact_root)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.collectors = COLLECTORS if collectors is None else collectors
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
        values = dict(payload or {})
        if values.get("dataset") and values.get("requested_timerange") and not values.get("policy_sha256"):
            policy_path = Path("config/validation.baseline.json")
            if policy_path.is_file():
                values["policy_sha256"] = hashlib.sha256(policy_path.read_bytes()).hexdigest()
        return self.store.start_or_resume_cycle(values)

    def heartbeat_cycle(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.store.heartbeat_cycle(
            payload["cycle_id"],
            lease_owner=payload["lease_owner"],
            now=payload.get("now"),
        )

    def reconcile_cycle(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.store.reconcile_cycle(
            payload["cycle_id"],
            observed_status=payload["observed_status"],
            reason=payload["reason"],
            observed_task_id=payload.get("observed_task_id"),
            observed_container_id=payload.get("observed_container_id"),
            lease_owner=payload.get("lease_owner"),
            now=payload.get("now"),
        )

    def load_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        cycle_id = payload["cycle_id"]
        cycle = self.store.get_cycle(cycle_id)
        if cycle is None:
            raise ValueError(f"unknown cycle: {cycle_id}")
        hypotheses = self.store.list_hypotheses(cycle_id)
        return {
            "cycle": cycle,
            "hypotheses": hypotheses,
            "ranking_sealed": bool(cycle.get("ranking_sealed_at")),
            "ranking_sha256": cycle.get("ranking_sha256"),
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

    def list_source_views(self, payload: dict[str, Any]) -> dict[str, Any]:
        values = {key: payload[key] for key in ("limit", "after") if key in payload}
        return self.store.list_source_views(payload["cycle_id"], **values)

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

        try:
            records = collector(query.strip(), limit)
        except (ProviderRetryableError, ProviderError) as exc:
            return self._provider_failure(cycle_id, provider, "provider_error", exc, 1)

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
        cycle_id = payload["cycle_id"]
        source = self.store.get_source(source_id)
        if source is None:
            raise ValueError(f"unknown source: {source_id}")
        with self.store.connect() as connection:
            observed = connection.execute(
                "SELECT 1 FROM cycle_sources WHERE cycle_id = ? AND source_id = ?",
                (cycle_id, source_id),
            ).fetchone()
        if observed is None:
            raise ValueError(f"source provenance missing: {source_id}")
        assessment = payload["assessment"]
        cycle = self.store.get_cycle(cycle_id)
        if cycle is not None and cycle.get("search_cohort") and not isinstance(assessment, dict):
            raise ValueError(
                "structured source assessment required: relevance, asset, timeframe, mechanism"
            )
        normalized = assessment if isinstance(assessment, dict) else {"assessment": assessment}
        if isinstance(assessment, dict):
            missing = [key for key in ("relevance", "asset", "timeframe", "mechanism") if not assessment.get(key)]
            if missing:
                raise ValueError(f"source assessment missing fields: {', '.join(missing)}")
            if str(assessment["relevance"]).casefold() not in {
                "direct", "directly_relevant", "relevant", "indirect", "contradicting", "falsifier", "irrelevant"
            }:
                raise ValueError("invalid source assessment relevance")
            immutable = {
                "provider", "canonical_url", "doi", "title", "excerpt", "license", "retrieved_at",
                "fingerprint", "full_text", "full_text_available", "collector_metadata",
            }
            if immutable.intersection(assessment):
                raise ValueError("immutable collector facts cannot be assessed")
        self.store.insert_source_assessment(cycle_id, source_id, normalized, actor="runtime")
        return {"source_id": source_id, "recorded": True}

    def seal_hypothesis_ranking(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.store.seal_hypothesis_ranking(payload["cycle_id"])

    def create_evaluation_cohort(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.store.create_evaluation_cohort(payload)

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
            if hypothesis.get("plan_json"):
                raise ValueError("candidate requires claim-level exit evidence")
            raise ValueError("candidate requires full-text or corroborating independent evidence")
        ranking = self.store.seal_hypothesis_ranking(cycle_id)
        eligible_ids = [item["hypothesis_id"] for item in ranking["ranking"] if item["eligible"]]
        if not eligible_ids or eligible_ids[0] != hypothesis["id"]:
            raise ValueError("only the highest-scoring sealed rank-1 eligible hypothesis may create a candidate")
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
        hypothesis = self.store.get_hypothesis(hypothesis_id)
        links = self.store.list_hypothesis_sources(hypothesis_id)
        if hypothesis is not None and hypothesis.get("plan_json"):
            support_roles: set[str] = set()
            contradicting = False
            for link in links:
                try:
                    evidence = json.loads(link.get("evidence_json", "{}"))
                except json.JSONDecodeError:
                    continue
                if not isinstance(evidence, dict):
                    continue
                roles = {str(role) for role in evidence.get("roles", [])}
                if link["stance"] == "SUPPORT":
                    support_roles.update(roles)
                elif link["stance"] == "CONTRADICT" and {"CONTRADICTION", "FALSIFIER"}.intersection(roles):
                    contradicting = True
            return {
                "ENTRY_SUPPORT",
                "STOP_SUPPORT",
                "PROFIT_EXIT_SUPPORT",
            }.issubset(support_roles) and contradicting

        supporting = [source for source in links if source["stance"] == "SUPPORT"]
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
        contradicting = [source for source in links if source["stance"] == "CONTRADICT"]
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
        try:
            planned_partitions = json.loads(existing.get("oos_partitions_json") or "[]")
        except json.JSONDecodeError as exc:
            raise ValueError("invalid OOS partition plan") from exc
        if not isinstance(planned_partitions, list):
            raise ValueError("OOS partition plan must be a list")
        if hypothesis.get("plan_json") and not planned_partitions:
            raise ValueError("identity-bound validation requires a non-empty OOS plan")
        cohort_owner = self._cohort_owner_for_partitions(
            hypothesis["id"], existing["snapshot_sha256"], planned_partitions, existing.get("owner_id")
        )
        if cohort_owner and existing.get("owner_id") != cohort_owner:
            raise ValueError("experiment owner does not match evaluation cohort")
        self.store.assert_oos_partitions_available(
            snapshot_sha256=existing["snapshot_sha256"],
            partitions=planned_partitions,
            owner_id=existing.get("owner_id"),
        )
        if hypothesis["state"] == HypothesisState.IMPLEMENTING:
            self.store.transition_hypothesis(
                hypothesis["id"], HypothesisState.TESTING, "runtime", "validation started", cycle_id
            )
        elif hypothesis["state"] != HypothesisState.TESTING:
            raise ValueError(f"hypothesis is not ready for validation: {hypothesis['state']}")

        try:
            trading_plan = None
            if hypothesis.get("plan_json"):
                trading_plan = json.loads(hypothesis["plan_json"])
            validation_experiment = {
                **existing,
                "candidate_path": hypothesis["candidate_path"],
                "candidate_sha256": hypothesis["candidate_sha256"],
                "identity_bound": bool(hypothesis.get("plan_json")),
                "plan_sha256": hypothesis.get("plan_sha256"),
                "trading_plan": trading_plan,
                "cycle_id": cycle_id,
                "hypothesis_id": hypothesis["id"],
            }
            result = (
                self.validator(validation_experiment)
                if self.validator is not None
                else validate_candidate(validation_experiment, artifact_root=self.artifact_root)
            )
        except (OSError, TimeoutError, ConnectionError) as exc:  # infrastructure boundary
            result = ResearchVerdict(
                verdict="RETRYABLE", state="RETRYABLE", metrics={}, artifacts={},
                error_code="validation_exception", details=(f"{type(exc).__name__}: {exc}",),
            )
        except Exception as exc:  # invalid validation evidence is not retryable
            result = ResearchVerdict(
                verdict="FAIL", state="REJECTED", metrics={}, artifacts={},
                error_code="validation_error", details=(f"{type(exc).__name__}: {exc}",),
            )
        normalized = self._normalize_validation_result(result)
        verified_partitions = self._verified_oos_partitions(normalized.get("artifacts", {}))
        if normalized["state"] == "RETRYABLE" and verified_partitions:
            normalized["verdict"] = "FAIL"
            normalized["state"] = "REJECTED"
            normalized["error_code"] = "retryable_after_oos_output"
        elif normalized["state"] == "RETRYABLE" and len(runs) >= 1:
            normalized["state"] = "INCONCLUSIVE"
        oos_evidence_valid = True
        planned_keys: set[tuple[str, str, str]] = set()
        verified_keys: set[tuple[str, str, str]] = set()
        try:
            planned_keys = {self._partition_key(partition) for partition in planned_partitions}
            verified_keys = {self._partition_key(partition) for partition in verified_partitions}
        except ValueError:
            oos_evidence_valid = False
        if len(verified_keys) != len(verified_partitions):
            oos_evidence_valid = False
        if normalized["verdict"] in {"PASS", "WARN", "FAIL"} and planned_partitions:
            if verified_keys != planned_keys:
                oos_evidence_valid = False
        if normalized["verdict"] in {"PASS", "WARN", "FAIL"} and planned_partitions and not oos_evidence_valid:
            normalized["verdict"] = "FAIL"
            normalized["state"] = "REJECTED"
            normalized["error_code"] = "missing_oos_evidence"
            normalized["details"] = ("conclusive validation did not verify planned OOS partitions",)
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
        run_payload = {
            "id": run_id,
            "experiment_id": existing["id"],
            "kind": "validation",
            "status": normalized["state"],
            "verdict": normalized["verdict"],
            "metrics": normalized["metrics"],
            "artifact_manifest": normalized["artifacts"],
            "error_code": normalized.get("error_code"),
        }
        consumption = None
        if normalized["verdict"] in {"PASS", "WARN", "FAIL"} and verified_partitions and oos_evidence_valid:
            consumption = {
                "dataset": cycle.get("dataset") or "unknown",
                "snapshot_sha256": existing["snapshot_sha256"],
                "cycle_id": cycle_id,
                "experiment_id": existing["id"],
                "verdict": normalized["verdict"],
                "partitions": verified_partitions,
                "owner_id": existing.get("owner_id"),
            }
        if consumption:
            normalized["artifacts"] = {
                **normalized.get("artifacts", {}),
                "oos_consumption": {
                    "status": "consumed",
                    "partitions": verified_partitions,
                    "owner_id": existing.get("owner_id"),
                },
            }
            run_payload["artifact_manifest"] = normalized["artifacts"]
        target = None if normalized["state"] == "RETRYABLE" else HypothesisState(normalized["state"])
        run, updated = self.store.record_validation_bundle(
            run=run_payload,
            cycle_id=cycle_id,
            hypothesis_id=hypothesis["id"],
            target_state=target,
            actor="runtime",
            reason=f"validation verdict {normalized['verdict']}",
            transition_payload={"verdict": normalized["verdict"], "metrics": normalized["metrics"]},
            validation_window={
                "dataset": cycle.get("dataset"),
                "requested_timerange": cycle.get("requested_timerange"),
                "policy_sha256": cycle.get("policy_sha256"),
                "verdict": normalized["verdict"],
            },
            consumption=consumption,
        )
        return self._validation_result(
            run,
            updated["state"] if updated is not None else normalized["state"],
            existing["id"],
        )

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
        owner = self._cohort_owner_for_partitions(
            hypothesis["id"], spec["snapshot_sha256"], spec.get("oos_partitions", []), spec.get("owner_id")
        )
        if owner:
            spec["owner_id"] = owner
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

    def _cohort_owner_for_partitions(
        self,
        hypothesis_id: str,
        snapshot_sha256: str,
        partitions: Any,
        requested_owner: str | None,
    ) -> str | None:
        if not isinstance(partitions, list):
            return requested_owner
        owner = requested_owner
        for partition in partitions:
            if not isinstance(partition, dict) or partition.get("kind") not in {"COMPARISON_OOS", "HOLDOUT"}:
                continue
            expected = self.store.authorize_cohort_partition(hypothesis_id, partition, snapshot_sha256)
            if owner not in (None, expected):
                raise ValueError("experiment owner does not match evaluation cohort")
            owner = expected
        return owner

    def _verified_oos_partitions(self, artifacts: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(artifacts, dict):
            return []
        value = artifacts.get("oos_partitions")
        manifest_path = artifacts.get("manifest_path")
        if value is None and manifest_path:
            try:
                manifest = json.loads(Path(str(manifest_path)).read_text())
            except (OSError, json.JSONDecodeError):
                return []
            if isinstance(manifest, dict):
                value = manifest.get("oos_partitions")
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            return []
        return value

    def _partition_key(self, partition: dict[str, Any]) -> tuple[str, str, str]:
        return self.store._validate_partition(partition)

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
        if cycle.get("ranking_sealed_at") is not None:
            raise ValueError("ranking sealed")
        required_data = payload["required_data"]
        if not isinstance(required_data, list) or not required_data:
            raise ValueError("required_data must be a non-empty list")
        identity_bound = bool(cycle.get("search_cohort"))
        if identity_bound and [str(item).upper() for item in required_data] != ["OHLCV"]:
            raise ValueError("identity-bound hypothesis requires required_data exactly [OHLCV]")

        supporting = list(payload.get("supporting_source_ids", []))
        contradicting = list(payload.get("contradicting_source_ids", []))
        if any(not isinstance(source_id, str) or not source_id.strip() for source_id in supporting + contradicting):
            raise ValueError("source IDs must be non-empty strings")
        if len(set(supporting)) != len(supporting) or len(set(contradicting)) != len(contradicting):
            raise ValueError("source IDs must be unique")
        if set(supporting).intersection(contradicting):
            raise ValueError("source stance overlap")
        if identity_bound and (not supporting or not contradicting):
            raise ValueError("identity-bound hypothesis requires structured evidence")

        source_ids = supporting + contradicting
        for source_id in source_ids:
            source = self.store.get_source(source_id)
            if source is None:
                raise ValueError(f"source provenance missing: {source_id}")
            with self.store.connect() as connection:
                observed = connection.execute(
                    "SELECT 1 FROM cycle_sources WHERE cycle_id = ? AND source_id = ?",
                    (cycle_id, source_id),
                ).fetchone()
            if observed is None:
                raise ValueError(f"source provenance missing: {source_id}")
            if identity_bound:
                assessment = self.store.get_source_assessment(cycle_id, source_id)
                if not isinstance(assessment, dict) or any(
                    not assessment.get(key) for key in ("relevance", "asset", "timeframe", "mechanism")
                ):
                    raise ValueError(f"structured evidence assessment missing: {source_id}")

        plan_json = None
        plan_hash = None
        if identity_bound:
            if not isinstance(payload.get("trading_plan"), dict):
                raise ValueError("identity-bound hypothesis requires a complete trading plan")
            plan = validate_trading_plan(payload["trading_plan"], identity_bound=True)
            plan_json = canonical_plan_json(plan)
            plan_hash = plan_sha256(plan)

        links = self._normalize_evidence_links(payload, supporting, contradicting, identity_bound)
        mechanism = str(payload["mechanism"]).strip()
        if not mechanism:
            raise ValueError("mechanism is required")
        existing = self.store.find_hypothesis_by_mechanism(cycle_id, mechanism)
        if existing is not None:
            if identity_bound and existing.get("plan_sha256") not in {None, plan_hash}:
                raise ValueError("hypothesis plan is immutable")
            for link in links:
                self.store.add_hypothesis_source(
                    existing["id"], link["source_id"], link["stance"], link["note"], link["evidence"]
                )
            return {"hypothesis": self.store.get_hypothesis(existing["id"]), "duplicate": True}

        unsupported = {str(item).upper() for item in required_data} - {"OHLCV"}
        state = HypothesisState.BACKLOG if unsupported else HypothesisState.SCORED
        hypothesis = self.store.insert_hypothesis(
            cycle_id,
            {
                **payload,
                "state": state,
                "family_id": payload.get("family_id"),
                "plan_json": plan_json,
                "plan_sha256": plan_hash,
            },
            source_links=links,
        )
        return {"hypothesis": hypothesis, "duplicate": False}

    @staticmethod
    def _normalize_evidence_links(
        payload: dict[str, Any],
        supporting: list[str],
        contradicting: list[str],
        identity_bound: bool,
    ) -> list[dict[str, Any]]:
        raw_links = payload.get("evidence_links")
        if raw_links is None:
            if identity_bound:
                raise ValueError("identity-bound hypothesis requires claim-level evidence links")
            return [
                {"source_id": source_id, "stance": "SUPPORT", "note": "supporting evidence", "evidence": {}}
                for source_id in supporting
            ] + [
                {"source_id": source_id, "stance": "CONTRADICT", "note": "contradicting evidence", "evidence": {}}
                for source_id in contradicting
            ]
        if not isinstance(raw_links, list) or not raw_links:
            raise ValueError("evidence_links must be a non-empty list")
        expected_stance = {source_id: "SUPPORT" for source_id in supporting}
        expected_stance.update({source_id: "CONTRADICT" for source_id in contradicting})
        links: list[dict[str, Any]] = []
        seen: set[str] = set()
        roles: set[str] = set()
        for raw in raw_links:
            if not isinstance(raw, dict):
                raise ValueError("evidence link must be an object")
            source_id = raw.get("source_id")
            stance = raw.get("stance")
            if source_id not in expected_stance or expected_stance[source_id] != stance:
                raise ValueError("evidence link stance does not match source lists")
            if source_id in seen:
                raise ValueError("duplicate evidence link")
            evidence = validate_evidence_link(raw.get("evidence")) if identity_bound else raw.get("evidence", {})
            if not isinstance(evidence, dict):
                raise ValueError("evidence must be an object")
            seen.add(source_id)
            roles.update(str(role) for role in evidence.get("roles", []))
            links.append(
                {
                    "source_id": source_id,
                    "stance": stance,
                    "note": str(raw.get("note") or "evidence").strip(),
                    "evidence": evidence,
                }
            )
        if identity_bound and seen != set(expected_stance):
            raise ValueError("evidence links must cover every cited source")
        return links

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
