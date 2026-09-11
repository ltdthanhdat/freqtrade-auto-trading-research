# Pi Automated Research Cycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bounded external-source collection, Pi/Luna-Max hypothesis generation, candidate writing, and reuse of the existing Freqtrade validation gate through typed runtime operations.

**Architecture:** Python collectors and the research runtime own network I/O, persistence, file writes, and subprocess execution. A project-local Pi extension selects Luna Max, exposes one typed runtime tool, and drives exactly one resumable research cycle without direct SQL or unrestricted shell access.

**Tech Stack:** Python 3.11 standard library, SQLite, existing Freqtrade/Plotly environment, Pi 0.85.1, TypeScript 5.9, pytest, Node test runner.

**Spec:** `docs/superpowers/specs/2026-09-11-automated-strategy-research-design.md`

## Global Constraints

- Pi model is exactly `openai-codex/gpt-5.6-luna` with thinking `max`; missing model/auth fails before cycle creation and never falls back.
- Python validates all runtime requests and is the only writer of SQLite and research artifacts.
- A cycle stores no more than 100 new sources, proposes no more than three hypotheses, and validates no more than one candidate.
- A temporary acquisition failure is retried at most twice; completed operations remain idempotent on resume.
- TradingView is excluded from automated acquisition.
- Abstract-only evidence cannot by itself authorize candidate generation.
- Candidate writes stay below `user_data/research-artifacts/<cycle_id>/candidate/`.
- Only the existing validation runner may execute Freqtrade commands.
- Validation uses the accepted six-pair basket, 120 in-sample days, 30 out-of-sample days, at least three OOS folds, and `1m` timeframe detail.
- Eligibility requires at least 100 aggregate OOS trades, positive stressed aggregate profit, at least two positive stressed folds, maximum per-fold drawdown at most 15%, and bootstrap p95 drawdown at most 15%.
- Stress remains fee `0.001` plus slippage `0.0005` per side; bootstrap remains 20,000 samples with seed `7` and two-week blocks.
- Automated work stops at `NEEDS_REVIEW`; no dry-run/live command is exposed.

---

### Task 1: Source collectors with provenance and deduplication

**Files:**
- Create: `research_runtime/collectors.py`
- Create: `tests/test_research_collectors.py`
- Modify: `research_runtime/service.py`
- Modify: `research_runtime/cli.py`

**Interfaces:**
- Consumes: `ResearchStore.insert_source`, cycle source budget, query strings, optional environment credentials.
- Produces: `collect_sources(provider, query, limit, opener=urlopen) -> list[SourceRecord]` and runtime operation `collect_sources`.

- [ ] **Step 1: Write failing provider-normalization tests**

```python
from io import BytesIO


class FakeResponse(BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def test_openalex_result_keeps_canonical_provenance():
    payload = b'{"results":[{"title":"RSI divergence","doi":"https://doi.org/10.1234/EXAMPLE","id":"https://openalex.org/W1","abstract_inverted_index":{"signal":[0]}}]}'
    records = collect_openalex(
        "RSI divergence", limit=2, opener=lambda _request: FakeResponse(payload)
    )
    assert records[0].provider == "openalex"
    assert records[0].doi == "10.1234/example"
    assert records[0].canonical_url == "https://doi.org/10.1234/example"
    assert records[0].retrieved_at.endswith("Z")
    assert records[0].fingerprint


def test_tradingview_is_not_a_provider():
    with pytest.raises(ValueError, match="unsupported provider"):
        collect_sources("tradingview", "RSI", 10)
```

Use the same `FakeResponse` seam for table-driven fixtures covering Semantic Scholar, CORE, arXiv Atom, Crossref, GitHub SPDX license metadata, and Stack Exchange. Assert DOI -> canonical URL -> fingerprint deduplication order, malformed response classification, HTTP 429 retryability, HTTP 403 provider failure, and that Quant Stack Exchange records are tagged `falsifier_only=True`.

- [ ] **Step 2: Run collector tests and confirm failure**

Run: `uv run pytest tests/test_research_collectors.py -v`

Expected: FAIL because collector functions do not exist.

- [ ] **Step 3: Implement small provider functions using the standard library**

```python
COLLECTORS = {
    "openalex": collect_openalex,
    "semantic_scholar": collect_semantic_scholar,
    "core": collect_core,
    "arxiv": collect_arxiv,
    "crossref": collect_crossref,
    "github": collect_github,
    "stackexchange": collect_stackexchange,
}


def collect_sources(provider, query, limit, opener=urlopen):
    if provider not in COLLECTORS:
        raise ValueError(f"unsupported provider: {provider}")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    return COLLECTORS[provider](query, limit, opener)
```

Use `urllib.parse.urlencode`, `urllib.request.Request`, `json`, and
`xml.etree.ElementTree`. Do not add an HTTP dependency. Read optional credentials from `CORE_API_KEY` and `GITHUB_TOKEN`; never log their values. Normalize DOI to lowercase without the `https://doi.org/` prefix and calculate SHA-256 over provider, normalized DOI/URL, title, and excerpt.

- [ ] **Step 4: Add the typed `collect_sources` runtime operation**

Require `cycle_id`, `provider`, `query`, and `limit`. Enforce remaining cycle budget before the request and on insertion. Return accepted IDs, duplicate IDs, and provider errors separately so absence of results is not confused with acquisition failure.
Retry HTTP 429/5xx and timeouts at most twice with injected `sleep`; never retry 4xx other than 429. Add a test whose fake opener always raises 429 and assert exactly three total calls and one persisted provider-error event.

- [ ] **Step 5: Run collector, CLI, and store tests**

Run: `uv run pytest tests/test_research_collectors.py tests/test_research_cli.py tests/test_research_store.py -v`

Expected: PASS with no network access.

- [ ] **Step 6: Commit source acquisition**

```bash
git add research_runtime/collectors.py research_runtime/service.py research_runtime/cli.py tests/test_research_collectors.py
git commit -m "feat: collect strategy research sources"
```

### Task 2: Strengthen the research eligibility verdict

**Files:**
- Modify: `config/validation.baseline.json`
- Modify: `scripts/validation_core.py`
- Modify: `scripts/validate_baseline.py`
- Modify: `tests/test_validation_core.py`
- Modify: `tests/test_validate_baseline.py`

**Interfaces:**
- Consumes: existing `ValidationPolicy`, `FoldMetrics`, and validation manifests.
- Produces: `min_positive_oos_folds=2` policy and fail-closed positive-stressed-fold enforcement.

- [ ] **Step 1: Write failing verdict boundary tests**

```python
def test_verdict_requires_two_positive_stressed_folds(policy):
    folds = [
        FoldMetrics(34, 0.03, 0.08),
        FoldMetrics(33, -0.01, 0.09),
        FoldMetrics(33, 0.00, 0.07),
    ]
    assert evaluate_verdict(Checks(True, True, True), folds, 0.10, policy) == "FAIL"


def test_zero_aggregate_stressed_profit_fails(policy):
    folds = [FoldMetrics(34, 0.01, 0.08), FoldMetrics(33, -0.01, 0.08), FoldMetrics(33, 0.0, 0.08)]
    assert evaluate_verdict(Checks(True, True, True), folds, 0.10, policy) == "FAIL"
```

Update the policy fixture to include `min_positive_oos_folds=2`. Add a manifest test asserting the reason `requires at least 2 positive stressed OOS folds`.

- [ ] **Step 2: Run focused validation tests and confirm failure**

Run: `uv run pytest tests/test_validation_core.py tests/test_validate_baseline.py -v`

Expected: FAIL because zero aggregate and one-positive-fold cases currently pass.

- [ ] **Step 3: Add the frozen policy field and checks**

Add to `ValidationPolicy` and `config/validation.baseline.json`:

```json
"min_positive_oos_folds": 2
```

Validate it as a positive integer no greater than `required_folds`. In `evaluate_verdict`, fail when aggregate stressed profit is `<= 0` or the number of folds with `net_profit > 0` is below the policy value. Add the same human-readable reasons to `validate_baseline.py` so manifests explain the failure.

- [ ] **Step 4: Run the full validation regression set**

Run:

```bash
uv run pytest tests/test_validation_core.py tests/test_validate_baseline.py \
  tests/test_validation_manifest.py tests/test_validation_regressions.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit the stronger gate**

```bash
git add config/validation.baseline.json scripts/validation_core.py scripts/validate_baseline.py tests/test_validation_core.py tests/test_validate_baseline.py
git commit -m "test: require positive OOS fold majority"
```

### Task 3: Candidate confinement and validation runtime operation

**Files:**
- Create: `research_runtime/candidates.py`
- Create: `research_runtime/validation.py`
- Create: `tests/test_research_candidates.py`
- Create: `tests/test_research_validation.py`
- Modify: `research_runtime/service.py`
- Modify: `research_runtime/cli.py`

**Interfaces:**
- Consumes: candidate text, experiment identity, `collect_identity`, `run_validation`, and the current cycle budget.
- Produces: `write_candidate(...) -> CandidateIdentity`, `validate_candidate(...) -> ResearchVerdict`, and runtime operations `write_candidate` and `start_validation`.

- [ ] **Step 1: Write failing candidate path and syntax tests**

```python
def test_candidate_writer_confines_output(tmp_path):
    identity = write_candidate(tmp_path, "cycle-1", "CandidateA", VALID_STRATEGY)
    assert identity.path == tmp_path / "cycle-1" / "candidate" / "CandidateA.py"
    assert len(identity.sha256) == 64


def test_candidate_writer_rejects_path_escape(tmp_path):
    with pytest.raises(ValueError, match="strategy name"):
        write_candidate(tmp_path, "cycle-1", "../outside", VALID_STRATEGY)


def test_candidate_writer_rejects_invalid_python(tmp_path):
    with pytest.raises(ValueError, match="syntax"):
        write_candidate(tmp_path, "cycle-1", "Broken", "class :")
```

Also prove a second candidate in the same cycle is rejected and an existing candidate cannot be overwritten with different content.
Add fail-closed cases proving abstract-only evidence, falsifier-only evidence, unsupported non-OHLCV data, or missing parent/config/snapshot/policy hashes cannot create a candidate or reach `NEEDS_REVIEW`.
Assert `write_candidate` rejects every hypothesis except the highest-scoring eligible hypothesis in the cycle; equal scores break by earlier creation time, then hypothesis ID.

- [ ] **Step 2: Run candidate tests and confirm failure**

Run: `uv run pytest tests/test_research_candidates.py -v`

Expected: FAIL because the module is missing.

- [ ] **Step 3: Implement minimal candidate validation**

Accept strategy names matching `^[A-Za-z][A-Za-z0-9_]{0,79}$`; parse source with `ast.parse`; require exactly one class with the requested name; resolve the final path and verify it remains below the cycle's candidate directory; write only through a temporary sibling followed by `Path.replace`; store SHA-256 in the experiment record.

- [ ] **Step 4: Write failing validation-wrapper tests**

Inject fake `collect_identity` and `run_validation` functions. Assert the wrapper:

```python
identity = collect_identity(...)
result = run_validation(args_with_approved_identity(asdict(identity)))
```

Maps `PASS -> NEEDS_REVIEW`, `WARN -> INCONCLUSIVE`, validation `FAIL -> REJECTED`, and subprocess/provider exceptions to `RETRYABLE`. Assert the runtime records manifest/report hashes and transitions in one short transaction after the subprocess ends.

- [ ] **Step 5: Implement the wrapper without weakening dry-run validation**

Do not add a bypass flag to `scripts.validate_baseline`. Build the candidate identity immediately before validation and supply that exact dictionary through its existing `approved_identity` argument. Use the experiment's fixed config, snapshot, policy, start/end, strategy name/path, and artifact directory.

- [ ] **Step 6: Add typed runtime operations and run tests**

Run:

```bash
uv run pytest tests/test_research_candidates.py tests/test_research_validation.py \
  tests/test_research_cli.py tests/test_validate_baseline.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit candidate validation**

```bash
git add research_runtime/candidates.py research_runtime/validation.py research_runtime/service.py research_runtime/cli.py tests/test_research_candidates.py tests/test_research_validation.py
git commit -m "feat: validate generated strategy candidates"
```

### Task 4: Project-local Pi extension with Luna Max preset

**Files:**
- Create: `.pi/extensions/strategy-research.ts`
- Create: `package.json`
- Create: `tsconfig.pi.json`
- Create: `tests/pi-strategy-research-contract.mjs`

**Interfaces:**
- Consumes: `python3 -m research_runtime.cli`, Pi `ExtensionAPI`, and exact runtime response JSON.
- Produces: `/research-cycle` and tool `strategy_research_runtime`.

- [ ] **Step 1: Write a failing static extension contract test**

```javascript
test("extension pins Luna Max and exposes one runtime tool", () => {
  const source = readFileSync(".pi/extensions/strategy-research.ts", "utf8");
  assert.match(source, /openai-codex.*gpt-5\.6-luna/);
  assert.match(source, /setThinkingLevel\("max"\)/);
  assert.match(source, /ui\.setStatus\("strategy-research"/);
  assert.equal((source.match(/registerTool\(/g) ?? []).length, 1);
  assert.doesNotMatch(source, /dry-run|compose-live|freqtrade-live/);
});
```

Add a subprocess fixture proving runtime `ok: false` becomes a thrown tool error with the runtime error code/details.

- [ ] **Step 2: Run Node and TypeScript checks and confirm failure**

Run: `node --test tests/pi-strategy-research-contract.mjs`

Expected: FAIL because the extension does not exist.

- [ ] **Step 3: Add pinned development dependencies**

```json
{
  "private": true,
  "devDependencies": {
    "@earendil-works/pi-ai": "0.85.1",
    "@earendil-works/pi-coding-agent": "0.85.1",
    "typescript": "5.9.2"
  },
  "scripts": {
    "check:pi-extension": "tsc --noEmit --project tsconfig.pi.json",
    "test:pi-extension": "node --test tests/pi-strategy-research-contract.mjs"
  }
}
```

Limit `tsconfig.pi.json#include` to `.pi/extensions/**/*.ts`.

- [ ] **Step 4: Implement the thin extension**

```typescript
function invoke(tool: string, payload: Record<string, unknown>) {
  const result = spawnSync("python3", ["-m", "research_runtime.cli"], {
    input: `${JSON.stringify({ tool, payload })}\n`,
    encoding: "utf8",
  });
  if (result.status !== 0) throw new Error(result.stderr || "research runtime failed");
  const response = JSON.parse(result.stdout);
  if (!response.ok) throw new Error(`${response.error.code}: ${response.error.details.join("; ")}`);
  return response;
}
```

Register `strategy_research_runtime` with `tool` and open payload TypeBox fields. In `/research-cycle`, resolve `ctx.modelRegistry.find("openai-codex", "gpt-5.6-luna")`; require `await pi.setModel(model)` to return true; set thinking to `max`; then invoke `start_or_resume_cycle`. Only after it succeeds, restrict active tools to `strategy_research_runtime` and call `pi.sendUserMessage` with the fixed cycle prompt.
Set `ctx.ui.setStatus("strategy-research", cycle.id + " · " + cycle.stage)` after start/resume and after each successful runtime response; clear it when the cycle reaches a terminal state.

- [ ] **Step 5: Typecheck and test the extension**

Run:

```bash
npm install
npm run check:pi-extension
npm run test:pi-extension
```

Expected: all commands exit 0.

- [ ] **Step 6: Verify Pi discovers the project extension**

Run: `pi --approve --no-builtin-tools --list-models luna`

Expected: output includes `openai-codex  gpt-5.6-luna` with thinking support. Then start Pi from the repo, run `/reload`, and confirm `/research-cycle` appears in command completion without starting a cycle.

- [ ] **Step 7: Commit the Pi extension**

```bash
git add .pi/extensions/strategy-research.ts package.json package-lock.json tsconfig.pi.json tests/pi-strategy-research-contract.mjs
git commit -m "feat: add Pi strategy research extension"
```

### Task 5: End-to-end fake research cycle and Make target

**Files:**
- Create: `tests/test_research_cycle.py`
- Create: `prompts/strategy-research.md`
- Modify: `Makefile`
- Modify: `README.md`

**Interfaces:**
- Consumes: collectors, runtime operations, candidate writer, validation wrapper, and Pi extension command.
- Produces: `make research-cycle` and a tested resume path ending at `NEEDS_REVIEW` without dry-run.

- [ ] **Step 1: Write a failing fake-cycle integration test**

```python
def proposal(index):
    return {
        "thesis": f"momentum thesis {index}",
        "mechanism": "bounded momentum persistence",
        "market_scope": "crypto perpetuals 30m",
        "required_data": ["OHLCV"],
        "falsifier": "aggregate stressed OOS profit <= 0",
        "scores": {
            "evidence_quality": 20,
            "reproducibility": 20,
            "ohlcv_transferability": 15,
            "novelty": 5,
            "falsifiability": 10,
        },
    }


def test_cycle_is_bounded_resumable_and_stops_for_review(tmp_path):
    records = [
        SourceRecord(
            provider="openalex",
            title=f"source {index}",
            excerpt="full-text evidence",
            canonical_url=f"https://example.test/{index}",
            doi=None,
            license="CC-BY",
            retrieved_at="2026-09-11T08:00:00Z",
            fingerprint=f"fingerprint-{index}",
            metadata={},
        )
        for index in range(100)
    ]
    service = ResearchService(
        ResearchStore(tmp_path / "research.sqlite"),
        artifact_root=tmp_path / "artifacts",
        collectors={"openalex": lambda _query, _limit: records},
        validator=lambda _experiment: {"verdict": "PASS", "artifacts": {}, "metrics": {}},
    )
    cycle = service.start_or_resume_cycle({"now": "2026-09-11T08:00:00Z"})["cycle"]
    service.collect_sources({"cycle_id": cycle["id"], "provider": "openalex", "query": "momentum", "limit": 100})
    hypotheses = [
        service.propose_hypothesis({"cycle_id": cycle["id"], **proposal(index)})
        for index in range(3)
    ]
    with pytest.raises(ValueError, match="hypothesis budget"):
        service.propose_hypothesis({"cycle_id": cycle["id"], **proposal(4)})
    selected = hypotheses[0]["hypothesis"]
    service.write_candidate({
        "cycle_id": cycle["id"],
        "hypothesis_id": selected["id"],
        "strategy_name": "ResearchCandidate",
        "source": "class ResearchCandidate:\n    pass\n",
    })
    result = service.start_validation({"cycle_id": cycle["id"], "hypothesis_id": selected["id"]})
    assert result["state"] == "NEEDS_REVIEW"
    assert service.load_context({"cycle_id": cycle["id"]})["budgets"] == {
        "sources": 100, "hypotheses": 3, "candidates": 1
    }
    assert not any("dry" in event["reason"].lower() for event in service.events(cycle["id"]))
```

Add a parameterized resume test with `crash_after` in `("sources", "hypotheses", "candidate", "validation")`: create a fresh `ResearchService` after that stage, assert it resumes the same cycle/stage, and assert source, hypothesis, candidate, and run counts do not increase when the completed operation is replayed.

- [ ] **Step 2: Run the integration test and confirm failure**

Run: `uv run pytest tests/test_research_cycle.py -v`

Expected: FAIL until the operation sequence and budget responses are complete.

- [ ] **Step 3: Add the fixed Pi cycle prompt**

The prompt must instruct Luna Max to call `load_context`, collect bounded sources, assess provenance, propose at most three structured hypotheses, implement only the selected hypothesis, start validation once, record interpretation, finalize, and stop. Explicitly forbid shell, SQL, TradingView automation, parameter sweeps, dry-run, and live execution.

- [ ] **Step 4: Add the Make target**

```make
.PHONY: research-cycle
research-cycle: ## Start or resume one bounded Pi research cycle
	pi --approve --model openai-codex/gpt-5.6-luna --thinking max --no-builtin-tools
```

The user runs `/research-cycle` after Pi opens. Document this exact two-step flow and the local DB/artifact locations.

- [ ] **Step 5: Run focused and full verification**

Run:

```bash
uv run pytest tests/test_research_cycle.py tests/test_research_collectors.py \
  tests/test_research_candidates.py tests/test_research_validation.py -v
npm run check:pi-extension
npm run test:pi-extension
uv run pytest -q
```

Expected: all commands exit 0.

- [ ] **Step 6: Commit the complete manual cycle**

```bash
git add tests/test_research_cycle.py prompts/strategy-research.md Makefile README.md
git commit -m "feat: add bounded automated research cycle"
```
