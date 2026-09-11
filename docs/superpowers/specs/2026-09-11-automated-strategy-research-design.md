# Automated Strategy Research Design

## Purpose

Build a bounded research system that discovers trading ideas from external
sources, turns the best supported idea into one Freqtrade candidate, validates
it, and stops for human review before dry-run. The system replaces the active
Markdown research workflow with SQLite and exposes its state through a local
dashboard.

The system may discover ideas from crypto, equities, forex, futures, and
commodities. Version 1 only validates ideas that can be expressed with the
project's existing crypto OHLCV data and Freqtrade engine.

## Invariants

- SQLite is the only machine-readable source of truth for new research.
- A cycle creates at most three hypotheses and validates at most one candidate.
- One hypothesis tests one new mechanism or market assumption. Parameter sweeps
  do not count as new hypotheses.
- A failed OOS result is evidence, not permission to tune the same candidate.
- The model cannot write SQL, mutate research state, or run arbitrary commands.
- All accepted evidence retains its canonical URL or DOI, source metadata, and
  exact retrieval time.
- No component starts dry-run or live trading automatically.
- Human approval records eligibility for dry-run; it does not start a bot.

## Architecture

```text
OpenAlex / Semantic Scholar / CORE / arXiv / Crossref
GitHub with allowed licenses / Quantitative Finance Stack Exchange
                              |
                              v
                    Python source collectors
                              |
                              v
                    user_data/research.sqlite
                              |
                              v
             Pi strategy-research extension (Luna Max)
                              |
                 structured runtime operations
                              |
                              v
              candidate -> correctness -> smoke
                    -> WFO -> stress -> bootstrap
                              |
                              v
             REJECTED / INCONCLUSIVE / NEEDS_REVIEW
                              |
                              v
                  loopback-only dashboard
```

Python owns collection, persistence, validation, and state transitions. Pi
interprets bounded source packets, proposes structured hypotheses, generates
candidate source text, and explains results. The dashboard reads the same
SQLite database and only permits explicit review decisions.

There is one orchestrator process. Version 1 has no Redis, task queue, daemon,
or concurrent workers.

## Persistence model

The canonical database is `user_data/research.sqlite`. Heavy output lives under
`user_data/research-artifacts/<cycle_id>/`. Both paths are local and ignored by
Git.

Seven tables are sufficient:

| Table | Responsibility |
|---|---|
| `cycles` | Cycle identity, budget, status, timestamps, and resume cursor. |
| `sources` | Canonical URL/DOI, provider, title, excerpt/content reference, license, retrieval time, and fingerprint. |
| `hypotheses` | Thesis, mechanism, required data, falsifier, score, state, and candidate identity. |
| `hypothesis_sources` | Many-to-many support or contradiction links between sources and hypotheses. |
| `experiments` | Immutable test specification: parent, single changed variable, pairs, timeframes, timerange, and policy hash. |
| `runs` | Individual correctness, smoke, WFO, stress, or bootstrap attempt with status, summary metrics JSON, and artifact manifest. |
| `state_events` | Append-only state transition and review audit log. |

Artifact manifests contain relative paths, sizes, and SHA-256 hashes. Summary
metrics are stored in `runs.metrics_json`; raw Freqtrade exports remain files.
SQLite foreign keys are enabled for every connection. Schema changes use
`PRAGMA user_version` migrations rather than a migration framework.

## Source acquisition and evidence rules

The initial automated source set is:

- OpenAlex for academic discovery.
- Semantic Scholar for citation and related-paper expansion.
- CORE and arXiv for abstracts or available full text.
- Crossref for DOI normalization and deduplication.
- GitHub for implementation cross-checks when an SPDX license is identified
  and allowed.
- Quantitative Finance Stack Exchange for failure modes and falsifiers, not as
  evidence of profitability.

TradingView is not an automated source in version 1. A manually supplied URL
may be retained for human reading, but the system does not scrape or
machine-process TradingView content.

Sources are deduplicated by DOI, then canonical URL, then content fingerprint.
Abstract-only sources may create a hypothesis but cannot alone justify a
candidate implementation. A candidate needs a sufficiently explicit method
from full text or corroborating independent sources. An idea that requires
fundamentals, an options chain, order-book events, or macro series is placed in
`BACKLOG`; the system does not invent an OHLCV proxy.

## Hypothesis extraction and ranking

Pi converts the collected source packet into a structured proposal containing:

- the claimed edge and causal mechanism;
- market and regime assumptions;
- entry, exit, and risk rules;
- required inputs and timeframes;
- a condition that would falsify the thesis;
- supporting and contradicting source identifiers.

Deterministic code rejects proposals with missing provenance, unsupported data,
no falsifiable rule, or a duplicate mechanism. A duplicate attaches its new
evidence to the existing hypothesis instead of creating another record.

Eligible proposals receive a 0-100 score:

| Dimension | Weight |
|---|---:|
| Evidence quality | 30 |
| Reproducibility as explicit rules | 25 |
| Transferability to crypto OHLCV | 20 |
| Novelty against prior tested mechanisms | 15 |
| Clear falsifier | 10 |

Each cycle queues at most the three highest-scoring new hypotheses. It
implements and validates only the highest-ranked eligible item.

## Pi extension

The project-local extension lives at
`.pi/extensions/strategy-research.ts`. It targets the installed Pi 0.85.1
packages and registers:

- `/research-cycle`, which starts or resumes one bounded cycle;
- one typed `strategy_research_runtime` tool, which passes JSON-lines requests
  to the Python runtime and returns structured results;
- a compact TUI status showing the current cycle and stage.

The command selects `openai-codex/gpt-5.6-luna` with thinking level `max`
before starting agent work. If that model or its authentication is unavailable,
the command fails before creating a cycle. There is no silent model fallback.

The runtime tool exposes only these operations:

- `load_context`
- `collect_sources`
- `record_source_assessment`
- `propose_hypothesis`
- `write_candidate`
- `start_validation`
- `record_interpretation`
- `finalize_cycle`

The TypeScript extension is an adapter, not a second business-logic layer. Each
operation is validated and executed by Python. During a research cycle, Pi does
not need direct SQL or unrestricted shell access. `write_candidate` is confined
to the current artifact directory, and `start_validation` invokes only the
predefined validation runner. Pi session history is diagnostic only; SQLite is
the resumable state.

## Candidate boundary

One candidate is generated from one frozen parent and one declared change. Its
source, parent identity, effective configuration, validation policy, data
snapshot, and dependencies are hashed before performance testing.

Candidate code remains under the cycle artifact directory. It is not copied to
`src/strategies/` during automated research. Promotion is a later explicit
workflow after review.

Changing a rule or parameter after a result creates a new hypothesis revision
and experiment. The previous candidate and results are never overwritten.

## Validation pipeline

Validation reuses the repository's existing Freqtrade validation primitives and
`config/validation.baseline.json` where applicable.

1. Validate the hypothesis and immutable experiment specification.
2. Load the strategy and run focused tests of its signal mechanics.
3. Run lookahead and recursive analysis.
4. Run a short, single-pair smoke backtest. This checks mechanics only and
   cannot establish profitability.
5. Run chronological WFO on the accepted basket with 120 in-sample days,
   30 out-of-sample days, at least three folds, and `1m` timeframe detail.
6. Apply the frozen fee and per-side slippage stress.
7. Run the existing 20,000-sample, two-week block bootstrap Monte Carlo.

A candidate reaches `NEEDS_REVIEW` only if:

- correctness, lookahead, and recursive checks pass;
- at least three OOS folds and 100 aggregate OOS trades exist;
- stressed aggregate OOS profit is positive;
- at least two of three OOS folds have positive stressed profit;
- no OOS fold exceeds 15% maximum drawdown;
- bootstrap p95 maximum drawdown is at most 15%; and
- result attribution is not dependent on only one pair or entry tag.

Missing history or insufficient trades yields `INCONCLUSIVE`, not `REJECTED`.
A correctness failure, broken identity, drawdown breach, or negative stressed
aggregate yields `REJECTED`. Infrastructure and temporary provider failures are
`RETRYABLE` and do not become research conclusions.

## State model

```text
DRAFT -> SCORED
          |-> BACKLOG
          |-> REJECTED
          `-> QUEUED -> IMPLEMENTING -> TESTING
                                      |-> REJECTED
                                      |-> INCONCLUSIVE
                                      `-> NEEDS_REVIEW
                                             |-> REJECTED
                                             `-> APPROVED_FOR_DRY_RUN
```

Every transition appends a `state_events` row containing previous and next
state, actor, reason, timestamp, and related cycle/run identifiers. Transitions
are checked in Python; the model cannot choose an illegal next state.

`APPROVED_FOR_DRY_RUN` is an eligibility record only. It does not execute
Freqtrade or bypass the existing dry-run identity gate.

## Cycle execution and recovery

`make research-cycle` opens one SQLite write transaction to acquire the cycle
lease. If a live lease exists, the command exits without launching another
worker. An expired `RUNNING` lease becomes `INTERRUPTED`, after which the cycle
resumes from its last completed stage.

Default hard budgets per cycle are:

- at most 100 newly stored source records;
- at most three new hypotheses;
- exactly zero or one candidate validation;
- at most two retries for a temporary network failure.

Failure of one source provider is recorded and does not stop other providers.
The cycle finishes as `COMPLETED`, `NEEDS_REVIEW`, `INCOMPLETE`, or `FAILED`.
It never loops indefinitely. Version 1 is manually invoked; a daily systemd
timer is considered only after repeated manual cycles resume and finish
correctly.

## Dashboard

The dashboard is a local research control room, not a trading terminal. It is
dark, information-dense, and uses green only for `PASS`, red for `FAIL`, and
amber for review or inconclusive states. Profit is always shown beside stressed
OOS profit and drawdown; win rate is not the primary metric.

The five views are:

1. **Overview**: current cycle, pipeline counts, best candidate, blockers, and
   recent state events.
2. **Sources**: provenance, quality, license, retrieval status, and duplicates.
3. **Hypotheses**: mechanism, score components, required data, support, and
   contradiction.
4. **Experiments**: parent comparison, folds, equity, drawdown, stress,
   bootstrap, and original artifacts.
5. **Review**: side-by-side candidate/parent evidence with explicit approve and
   reject actions.

The server binds only to `127.0.0.1`. It is read-mostly: GET endpoints read
SQLite, while approve and reject append validated review transitions. Review
actions require same-origin requests and explicit confirmation. There is no
pause, start-cycle, dry-run, or live action in the dashboard.

The backend uses Python's standard library and SQLite. Charts reuse the Plotly
dependency already present in the project. No frontend or backend framework is
added unless the approved prototype demonstrates a concrete need.

## OpenDesign workflow

Use the official OpenDesign project from `open-design.ai` for the visual design
phase after this architecture is approved:

1. Feed this spec, the dashboard information hierarchy, and representative
   fixture data into OpenDesign.
2. Select a dashboard design system and generate a runnable prototype plus
   `DESIGN.md`.
3. Review desktop, tablet, mobile monitoring, keyboard navigation, contrast,
   loading, empty, error, and long-content states.
4. Approve the visual direction before implementing the production dashboard.

The prototype informs visual structure only. It does not redefine the SQLite
schema, validation gates, or dry-run safety boundary.

## Legacy `.research` migration

The current `.research/` tree is imported once and then removed from the active
checkout:

1. Parse its SMC and RSI hypotheses, experiments, decisions, candidate files,
   and run metadata.
2. Copy retained raw artifacts into a `legacy` artifact area and record their
   hashes.
3. Compare imported counts, relationships, selected records, and checksums.
4. Run SQLite integrity and foreign-key checks.
5. Create a local SQLite backup.
6. Remove `.research/` only after the migration report is accepted. The old
   files remain recoverable from Git history.

New research does not generate parallel Markdown state. The dashboard may
export a Markdown report on demand, but exported text is not authoritative.

## Verification

- Unit tests cover schemas, scoring boundaries, deduplication, legal
  transitions, budgets, lease expiry, retry classification, and the 15% gate.
- Extension tests prove JSON-lines conversion, structured error propagation,
  Luna Max selection, no silent fallback, and command resume behavior.
- Integration tests use fake collectors and a temporary SQLite database; they
  do not require Internet access or mutate the canonical database.
- Validation tests prove that missing correctness, WFO, stress, bootstrap, or
  identity evidence cannot reach `NEEDS_REVIEW`.
- Crash tests interrupt a cycle at each stage and verify idempotent resume.
- Migration tests compare current SMC and RSI records and artifact hashes before
  `.research/` removal.
- Dashboard tests cover read endpoints, the two allowed review mutations, SQL
  parameterization, same-origin enforcement, and illegal transitions.
- Browser verification covers desktop/tablet/mobile layouts, keyboard access,
  contrast, empty/error states, chart labels, and console errors.
- The existing repository test suite must remain green.

## Non-goals for version 1

- Equities or forex market-data ingestion and backtest engines.
- Automated TradingView ingestion.
- Hyperopt or unbounded parameter search.
- Concurrent research workers or agent swarms.
- Remote dashboard access, accounts, or authentication.
- Automatic daily scheduling.
- Automatic strategy promotion, dry-run, or live trading.
