# Research Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the approved OpenDesign prototype into a loopback-only dashboard backed by the canonical research SQLite database, with only approve/reject mutations.

**Architecture:** A Python standard-library HTTP server builds small read models from SQLite and serves one self-contained HTML application. Vanilla JavaScript renders five views and sends same-origin JSON review requests; it exposes no cycle, dry-run, or live control.

**Tech Stack:** Python 3.11 standard library, SQLite, existing Plotly package, HTML/CSS/vanilla JavaScript, pytest, browser verification.

**Spec:** `docs/superpowers/specs/2026-09-11-automated-strategy-research-design.md`

## Global Constraints

- Preserve `dashboard/DESIGN.md` and the approved Mission Control visual direction.
- Bind to `127.0.0.1` by default; do not add a public-host flag in version 1.
- SQLite reads use `mode=ro`, `immutable=1` only for snapshot reads, and `PRAGMA query_only=ON`.
- The only mutations are review `approve` and `reject`, implemented as legal `state_events` transitions.
- Every review POST requires JSON content type, exact same-origin header, hypothesis ID, action, and non-empty reason.
- Never expose credentials, arbitrary SQL, artifact paths outside the research artifact root, or commands that start Pi/Freqtrade.
- All sample values disappear from production data rendering; honest empty/loading/error states remain.

---

### Task 1: Dashboard read model and review service

**Files:**
- Create: `research_runtime/dashboard.py`
- Create: `tests/test_research_dashboard.py`

**Interfaces:**
- Consumes: `ResearchStore`, seven SQLite tables, and `transition_hypothesis`.
- Produces: `DashboardReadModel(db_path: Path, artifact_root: Path)` methods `overview()`, `sources()`, `hypotheses()`, `experiments()`, `review_queue()`, and `record_review(hypothesis_id, action, reason)`.

- [ ] **Step 1: Write failing read-model tests**

```python
@pytest.fixture
def seeded_store(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    now = "2026-09-11T08:00:00Z"
    with store.connect() as connection:
        connection.execute(
            "INSERT INTO cycles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("C-1", "RUNNING", "VALIDATING", 1, 3, 0, None, now, now),
        )
        connection.execute(
            "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("S-1", "C-1", "openalex", "https://example.test/1", None,
             "source", "evidence", "CC-BY", now, "fingerprint-1", "{}"),
        )
        hypothesis = (
            "thesis", "mechanism", "crypto perpetuals 30m", '["OHLCV"]',
            "stressed OOS profit <= 0", 20, 20, 15, 5, 10, 70,
        )
        connection.execute(
            "INSERT INTO hypotheses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("H-QUEUED", "C-1", *hypothesis, "QUEUED", None, None, "{}", now, now),
        )
        connection.execute(
            "INSERT INTO hypotheses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("H-TESTING", "C-1", *hypothesis, "TESTING", None, None, "{}", now, now),
        )
        connection.execute(
            "INSERT INTO hypotheses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("H-READY", "C-1", *hypothesis, "NEEDS_REVIEW", None, None, "{}", now, now),
        )
    return store


def test_overview_reports_pipeline_and_current_cycle(seeded_store, tmp_path):
    view = DashboardReadModel(seeded_store.path, tmp_path / "artifacts").overview()
    assert view["counts"] == {"sources": 1, "hypotheses": 3, "queued": 1, "testing": 1, "review": 1}
    assert view["current_cycle"]["stage"] == "VALIDATING"


def test_review_requires_needs_review_state(seeded_store, tmp_path):
    model = DashboardReadModel(seeded_store.path, tmp_path / "artifacts")
    with pytest.raises(ValueError, match="illegal transition"):
        model.record_review("H-TESTING", "approve", "looks stable")
```

Add tests for source provenance, supporting/contradicting evidence, parent/candidate comparison, fold ordering, absent candidate, empty database, and artifact links constrained below the configured artifact root.

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `uv run pytest tests/test_research_dashboard.py -v`

Expected: FAIL because `DashboardReadModel` is missing.

- [ ] **Step 3: Implement parameterized read queries**

Open read connections with a URI:

```python
connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
connection.row_factory = sqlite3.Row
connection.execute("PRAGMA query_only=ON")
```

Return JSON-compatible dictionaries only. Decode known JSON columns explicitly and reject malformed stored JSON rather than returning partial metrics. Sort sources by retrieval time, hypotheses by score then creation time, experiments/runs chronologically, and state events newest first.

- [ ] **Step 4: Implement review through the store transition API**

Map only:

```python
REVIEW_TARGETS = {
    "approve": HypothesisState.APPROVED_FOR_DRY_RUN,
    "reject": HypothesisState.REJECTED,
}
```

Require current state `NEEDS_REVIEW`, actor `local_user`, and a stripped reason. Do not issue SQL updates from the dashboard module.

- [ ] **Step 5: Run read-model and store tests**

Run: `uv run pytest tests/test_research_dashboard.py tests/test_research_store.py -v`

Expected: PASS.

- [ ] **Step 6: Commit the read model**

```bash
git add research_runtime/dashboard.py tests/test_research_dashboard.py
git commit -m "feat: add research dashboard read model"
```

### Task 2: Loopback HTTP server and constrained API

**Files:**
- Modify: `research_runtime/dashboard.py`
- Modify: `tests/test_research_dashboard.py`
- Modify: `Makefile`

**Interfaces:**
- Consumes: `DashboardReadModel` and `dashboard/index.html`.
- Produces: `build_server(db_path: Path, artifact_root: Path, port: int = 0) -> ThreadingHTTPServer`, blocking `serve(db_path, artifact_root, port)`, GET endpoints, and one review POST endpoint.

- [ ] **Step 1: Write failing HTTP contract tests**

Start the server on port `0` in a test thread and assert:

```python
def request(origin, method, path, body=None, headers=None):
    parsed = urlsplit(origin)
    connection = HTTPConnection(parsed.hostname, parsed.port, timeout=2)
    encoded = None if body is None else json.dumps(body).encode()
    connection.request(method, path, body=encoded, headers=headers or {})
    response = connection.getresponse()
    result = response.status, response.read().decode()
    connection.close()
    return result


def test_http_contract(seeded_store, tmp_path):
    server = build_server(seeded_store.path, tmp_path / "artifacts", port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        status, body = request(origin, "GET", "/api/overview")
        assert status == 200
        assert json.loads(body)["counts"]["sources"] == 1

        status, _ = request(
            origin,
            "POST",
            "/api/hypotheses/H-READY/review",
            body={"action": "approve", "reason": "reviewed WFO and bootstrap"},
            headers={"Origin": origin, "Content-Type": "application/json"},
        )
        assert status == 200
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
```

Add cases for missing/wrong Origin (`403`), non-JSON content (`415`), unknown action (`400`), illegal state (`409`), oversized body (`413`), unknown route (`404`), path traversal (`404`), and OPTIONS returning only the local origin.

- [ ] **Step 2: Run the HTTP tests and confirm failure**

Run: `uv run pytest tests/test_research_dashboard.py -v`

Expected: FAIL because no HTTP server exists.

- [ ] **Step 3: Implement routes with `ThreadingHTTPServer`**

Use an explicit route mapping:

```python
READ_ROUTES = {
    "/api/overview": read_model.overview,
    "/api/sources": read_model.sources,
    "/api/hypotheses": read_model.hypotheses,
    "/api/experiments": read_model.experiments,
    "/api/review": read_model.review_queue,
}
```

Serve `/` from `dashboard/index.html`; serve `/assets/plotly.min.js` from the already-installed Plotly package; serve only hash-verified artifacts whose resolved paths stay below `artifact_root`. Cap POST bodies at 16 KiB. Set `Content-Security-Policy: default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:` and `X-Content-Type-Options: nosniff`.

- [ ] **Step 4: Add a Make target**

```make
.PHONY: research-dashboard
research-dashboard: ## Open the local research dashboard server
	$(PYTHON) -m research_runtime.dashboard --db user_data/research.sqlite --artifacts user_data/research-artifacts --port 7400
```

- [ ] **Step 5: Run HTTP tests**

Run: `uv run pytest tests/test_research_dashboard.py -v`

Expected: PASS.

- [ ] **Step 6: Commit the server**

```bash
git add research_runtime/dashboard.py tests/test_research_dashboard.py Makefile
git commit -m "feat: serve the local research dashboard"
```

### Task 3: Wire the OpenDesign prototype to live read models

**Files:**
- Move: `dashboard/prototype/index.html` to `dashboard/index.html`
- Modify: `dashboard/index.html`
- Create: `tests/test_dashboard_markup.py`

**Interfaces:**
- Consumes: the five GET endpoints and review POST endpoint from Task 2.
- Produces: a five-view single-page dashboard preserving the approved design system.

- [ ] **Step 1: Write failing static markup tests**

```python
def test_dashboard_has_five_named_views_and_no_trading_controls():
    html = Path("dashboard/index.html").read_text()
    assert set(re.findall(r'data-view="([^"]+)"', html)) == {
        "overview", "sources", "hypotheses", "experiments", "review"
    }
    assert "Sample data" not in html
    assert not re.search(r">\s*(Start dry-run|Start live|Run cycle)\s*<", html, re.I)


def test_review_controls_require_reason_and_confirmation():
    html = Path("dashboard/index.html").read_text()
    assert 'id="reviewReason"' in html
    assert "window.confirm" in html
    assert 'Content-Type": "application/json"' in html
```

Also assert no remote assets, one same-origin `/assets/plotly.min.js` script, unique IDs, `prefers-reduced-motion`, table labels, chart title/description, loading/empty/error containers, and no inline click handlers.

- [ ] **Step 2: Run markup tests and confirm failure**

Run: `uv run pytest tests/test_dashboard_markup.py -v`

Expected: FAIL because the approved prototype is not yet wired or moved.

- [ ] **Step 3: Convert navigation into view switching**

Keep the existing shell and tokens. Add five `<section data-view="...">` regions and one delegated click handler. Update the URL hash without page reload. The active link must update `aria-current`, and the selected view heading receives focus.

- [ ] **Step 4: Add a small fetch/render layer**

```javascript
const endpoints = {
  overview: "/api/overview",
  sources: "/api/sources",
  hypotheses: "/api/hypotheses",
  experiments: "/api/experiments",
  review: "/api/review",
};

async function loadView(name) {
  setViewState(name, "loading");
  try {
    const response = await fetch(endpoints[name], { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderView(name, await response.json());
    setViewState(name, "ready");
  } catch (error) {
    renderError(name, error.message);
    setViewState(name, "error");
  }
}
```

Render all text with `textContent`, never HTML strings from the API. Build tables with DOM methods. Render fold equity/drawdown with `Plotly.newPlot` from the same-origin script and provide the same metrics in the fold table.

- [ ] **Step 5: Wire explicit review decisions**

Require a non-empty reason and `window.confirm` immediately before fetch. POST `{action, reason}` to `/api/hypotheses/<encoded-id>/review`; after success reload the review and overview views. Do not optimistically change state.

- [ ] **Step 6: Run markup and dashboard tests**

Run:

```bash
uv run pytest tests/test_dashboard_markup.py tests/test_research_dashboard.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit the wired dashboard**

```bash
git add dashboard/index.html dashboard/prototype/index.html tests/test_dashboard_markup.py
git commit -m "feat: connect research dashboard to SQLite"
```

### Task 4: Runtime and browser verification

**Files:**
- Modify: `README.md`
- Test: existing and new test suites.

**Interfaces:**
- Consumes: the migrated local database, `make research-dashboard`, and the production HTML.
- Produces: verified local usage instructions and visual evidence.

- [ ] **Step 1: Add concise dashboard instructions**

Document:

```bash
make research-dashboard
# open http://127.0.0.1:7400
```

State that it reads `user_data/research.sqlite`, exposes only review decisions, and cannot start research/dry-run/live.

- [ ] **Step 2: Run the complete automated suite**

Run:

```bash
uv run pytest -q
npm run check:pi-extension
npm run test:pi-extension
```

Expected: all commands exit 0 with zero failures.

- [ ] **Step 3: Start the server against the migrated local database**

Run: `uv run python -m research_runtime.dashboard --db user_data/research.sqlite --artifacts user_data/research-artifacts --port 7400`

Expected: `curl -fsS http://127.0.0.1:7400/api/overview` returns valid JSON and `curl -fsS http://127.0.0.1:7400/` returns the dashboard HTML.

- [ ] **Step 4: Perform browser verification**

At 1440x900, 900x1024, and 390x844 verify Overview, Sources, Hypotheses, Experiments, and Review. Check keyboard-only navigation, focus visibility, loading/empty/error states, approve/reject confirmation, chart accessible text, horizontal table handling, and browser console errors. Confirm no control or request starts Pi, dry-run, or live trading.

- [ ] **Step 5: Commit documentation after evidence is recorded**

```bash
git add README.md
git commit -m "docs: document research dashboard"
```
