# Dry-run Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible historical validation gate and persisted dry-run safety state for the frozen SMC baseline.

**Architecture:** A pure-Python validation core owns the fixed policy, OOS folds, verdicts, deterministic bootstrap metrics, and audit SQLite. A thin runner invokes Freqtrade and writes immutable artifacts. Native Freqtrade protections own temporary PairLocks. V1 requires human review to reopen a red `PAUSED` state; only normal time-bounded locks reopen automatically.

**Tech Stack:** Python 3.11, pytest, pandas, NumPy, SQLite, Freqtrade CLI and native protections.

**Spec:** `docs/superpowers/specs/2026-09-10-dry-run-validation-design.md`

## Global Constraints

- Freeze entry/exit logic and the accepted six-pair basket during validation.
- Require matching strategy commit, config hash, and data snapshot hash for every run.
- Require `1m`, `30m`, and `1h` data; missing data cannot produce `PASS`.
- Do not auto-tune, expand pairs, change leverage, or promote to live trading.
- Use 15% as the portfolio drawdown budget.
- Require three chronological non-overlapping OOS folds and 100 aggregate OOS trades for `PASS`.
- Keep runtime state gitignored; never delete earlier backtest artifacts.

---

## File Structure

- Create: `config/validation.baseline.json` — frozen policy.
- Create: `scripts/validation_core.py` — models, folds, verdicts, bootstrap and state store.
- Create: `scripts/validate_baseline.py` — CLI orchestrator and artifact writer.
- Modify: `scripts/monitor_decay.py` — shared bootstrap equity evidence.
- Modify: `src/strategies/SMC_FVG_Context30m_Freqtrade.py` — one-candle native cooldown.
- Modify: `Makefile`, `README.md`, `.research/smc_fvg_pinbar/state.md`, and `.gitignore`.
- Create: `tests/test_validation_core.py`, `tests/test_validate_baseline.py`, `tests/test_runtime_protections.py`.

### Task 1: Policy, OOS folds, and verdict core

**Files:**
- Create: `config/validation.baseline.json`
- Create: `scripts/validation_core.py`
- Test: `tests/test_validation_core.py`

**Interfaces:**
- Produces `ValidationPolicy.from_path(path: Path) -> ValidationPolicy`.
- Produces `build_oos_folds(start: pd.Timestamp, end: pd.Timestamp, policy: ValidationPolicy) -> list[OosFold]`.
- Produces `evaluate_verdict(checks: Checks, folds: list[FoldMetrics], p95_dd: float, policy: ValidationPolicy) -> str`.

- [ ] **Step 1: Write failing tests**

```python
def test_oos_folds_are_chronological_and_non_overlapping():
    policy = ValidationPolicy(120, 30, 3, 100, 0.15, 0.001, 0.0005, 7, 20_000, "2W")
    folds = build_oos_folds(pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2025-08-01", tz="UTC"), policy)
    assert len(folds) == 3
    assert folds[0].oos_end <= folds[1].oos_start

def test_verdict_fails_on_drawdown_breach():
    assert evaluate_verdict(Checks(True, True, True), [FoldMetrics(100, .02, .151)], .10, policy) == "FAIL"
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `uv run pytest tests/test_validation_core.py -v`

Expected: FAIL because `scripts.validation_core` does not exist.

- [ ] **Step 3: Implement the minimum core and frozen policy**

```python
@dataclass(frozen=True)
class OosFold:
    in_sample_start: pd.Timestamp
    in_sample_end: pd.Timestamp
    oos_start: pd.Timestamp
    oos_end: pd.Timestamp

def build_oos_folds(start, end, policy):
    cursor = start + pd.Timedelta(days=policy.in_sample_days)
    folds = []
    while cursor + pd.Timedelta(days=policy.oos_days) <= end:
        folds.append(OosFold(start, cursor, cursor, cursor + pd.Timedelta(days=policy.oos_days)))
        cursor += pd.Timedelta(days=policy.oos_days)
    return folds
```

The JSON policy sets the exact accepted basket, 120 IS days, 30 OOS days, 3 folds, 100 OOS trades, DD `0.15`, stress fee `0.001`, slippage `0.0005` per side, seed `7`, 20,000 samples, and `2W` blocks.

- [ ] **Step 4: Run focused verification**

Run: `uv run pytest tests/test_validation_core.py -v && uv run ruff check scripts/validation_core.py tests/test_validation_core.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add config/validation.baseline.json scripts/validation_core.py tests/test_validation_core.py
git commit -m "feat: add validation policy and verdict core"
```

### Task 2: Immutable Freqtrade runner

**Files:**
- Create: `scripts/validate_baseline.py`
- Test: `tests/test_validate_baseline.py`

**Interfaces:**
- Consumes the Task 1 policy, folds, and verdict function.
- Produces `run_validation(args: argparse.Namespace, executor=subprocess.run) -> ValidationRun`.
- Produces `manifest.json` and `report.md` in `.research/smc_fvg_pinbar/runs/20260910T120000Z/`.

- [ ] **Step 1: Write failing tests with a fake executor**

```python
def test_runner_rejects_snapshot_without_1m_data(tmp_path):
    result = run_validation(make_args(tmp_path), executor=FakeExecutor())
    assert result.verdict == "FAIL"
    assert "missing timeframe 1m" in result.reasons

def test_manifest_binds_config_and_snapshot_hashes(tmp_path):
    result = run_validation(make_complete_args(tmp_path), executor=FakeExecutor())
    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["config_sha256"] and manifest["snapshot_sha256"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_validate_baseline.py -v`

Expected: FAIL because `scripts.validate_baseline` does not exist.

- [ ] **Step 3: Implement runner stages**

Use `--cache none --timeframe-detail 1m --export trades` and a unique `--backtest-filename` for every fold. Execute lookahead and recursive analysis before folds. Hash the config, strategy source, and snapshot files. Write artifacts only to the run directory.

```python
def run_validation(args, executor=subprocess.run):
    identity = collect_identity(args.config, args.strategy_file, args.datadir)
    ensure_required_timeframes(args.datadir, ("1m", "30m", "1h"))
    checks = run_correctness_checks(args, executor)
    folds = run_oos_folds(args, executor)
    return write_result(identity, checks, folds, args.policy)
```

- [ ] **Step 4: Run focused verification**

Run: `uv run pytest tests/test_validate_baseline.py tests/test_validation_core.py -v`

Expected: PASS without exchange credentials or network access.

- [ ] **Step 5: Commit**

```bash
git add scripts/validate_baseline.py tests/test_validate_baseline.py
git commit -m "feat: add immutable baseline validation runner"
```

### Task 3: Monte Carlo evidence and decay monitor

**Files:**
- Modify: `scripts/validation_core.py`
- Modify: `scripts/monitor_decay.py`
- Test: `tests/test_validation_core.py`

**Interfaces:**
- Produces `bootstrap_equity_paths(trades: pd.DataFrame, policy: ValidationPolicy) -> BootstrapSummary`.
- `BootstrapSummary` has `p95_max_drawdown`, `p05_net_profit`, and `p95_losing_streak`.

- [ ] **Step 1: Write failing deterministic test**

```python
def test_bootstrap_equity_paths_are_deterministic():
    trades = pd.DataFrame({"open_date": pd.date_range("2026-01-01", periods=8, freq="D"), "profit_ratio": [.01, -.02] * 4})
    assert bootstrap_equity_paths(trades, policy) == bootstrap_equity_paths(trades, policy)
```

- [ ] **Step 2: Run test to verify failure**

Run: `uv run pytest tests/test_validation_core.py::test_bootstrap_equity_paths_are_deterministic -v`

Expected: FAIL because `bootstrap_equity_paths` is undefined.

- [ ] **Step 3: Implement time-block resampling**

Resample whole `2W` blocks using NumPy seed `7`; subtract `2 * slippage_per_side` from each trade before each stressed equity path; calculate peak-to-trough DD and consecutive losses. Make `monitor_decay.py` print these values and return nonzero only on its red alert.

- [ ] **Step 4: Run focused verification**

Run: `uv run pytest tests/test_validation_core.py -v && uv run ruff check scripts/validation_core.py scripts/monitor_decay.py tests/test_validation_core.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/validation_core.py scripts/monitor_decay.py tests/test_validation_core.py
git commit -m "feat: add bootstrap equity risk evidence"
```

### Task 4: Persisted state and native cooldown

**Files:**
- Modify: `scripts/validation_core.py`
- Modify: `src/strategies/SMC_FVG_Context30m_Freqtrade.py`
- Modify: `.gitignore`
- Test: `tests/test_runtime_protections.py`

**Interfaces:**
- Produces `ValidationStateStore(path: Path)` with `transition(scope, state, reason, metrics, lock_until, run_id)`.
- The strategy produces a `protections` property with one `CooldownPeriod` candle.

- [ ] **Step 1: Write failing state and protection tests**

```python
def test_paused_state_requires_review_to_reopen(tmp_path):
    store = ValidationStateStore(tmp_path / "validation_state.sqlite")
    store.transition("global", "PAUSED", "drawdown", {}, None, "r1")
    with pytest.raises(ValueError, match="review"):
        store.transition("global", "ACTIVE", "timer", {}, None, "r1")

def test_strategy_declares_one_candle_cooldown():
    assert SMC_FVG_Context30m_Freqtrade({}).protections == [
        {"method": "CooldownPeriod", "stop_duration_candles": 1}
    ]
```

- [ ] **Step 2: Run test to verify failure**

Run: `uv run pytest tests/test_runtime_protections.py -v`

Expected: FAIL because the store and `protections` property are absent.

- [ ] **Step 3: Implement only validated v1 behavior**

Create `current_state` and append-only `state_events` with `CREATE TABLE IF NOT EXISTS`. Only allow `PAUSED -> ACTIVE` for reason `review-approved`. Add `user_data/validation_state.sqlite*` to `.gitignore`. Do not implement automatic red pauses or reopening: no OOS-validated regime predicate exists.

- [ ] **Step 4: Run focused verification**

Run: `uv run pytest tests/test_runtime_protections.py -v && uv run ruff check src/strategies/SMC_FVG_Context30m_Freqtrade.py scripts/validation_core.py tests/test_runtime_protections.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .gitignore src/strategies/SMC_FVG_Context30m_Freqtrade.py scripts/validation_core.py tests/test_runtime_protections.py
git commit -m "feat: persist validation audit state"
```

### Task 5: Operator commands and gate documentation

**Files:**
- Modify: `Makefile`
- Modify: `README.md`
- Modify: `.research/smc_fvg_pinbar/state.md`
- Test: `tests/test_validate_baseline.py`

**Interfaces:**
- Produces `make validate-snapshot DATASET=accepted_6pair_2026q3`.
- Produces `make monitor-decay BASELINE=user_data/backtest_results/baseline.zip DB=user_data/tradesv3.demo.sqlite`.

- [ ] **Step 1: Write failing command-surface test**

```python
def test_makefile_exposes_validate_snapshot():
    makefile = Path("Makefile").read_text()
    assert "validate-snapshot:" in makefile
    assert "scripts/validate_baseline.py" in makefile
```

- [ ] **Step 2: Run test to verify failure**

Run: `uv run pytest tests/test_validate_baseline.py::test_makefile_exposes_validate_snapshot -v`

Expected: FAIL because the target is absent.

- [ ] **Step 3: Add operator commands and documentation**

The target passes base config, named snapshot datadir, policy, strategy class/path, and `.research/smc_fvg_pinbar/runs`. Document that only `PASS` starts dry-run, while `WARN` and `FAIL` retain artifacts and block it. Update research state to `validation gate pending`; do not claim a validation run completed.

- [ ] **Step 4: Run full static verification**

Run: `uv run pytest tests -v && uv run ruff check scripts src tests && git diff --check`

Expected: PASS. Do not claim Freqtrade integration passes until a named snapshot exists and the runner succeeds.

- [ ] **Step 5: Commit**

```bash
git add Makefile README.md .research/smc_fvg_pinbar/state.md tests/test_validate_baseline.py
git commit -m "docs: add dry-run validation workflow"
```

## Final verification

- [ ] Seed a named accepted-six-pair snapshot with `1m,30m,1h` data.
- [ ] Run `make validate-snapshot DATASET=accepted_6pair_2026q3` and retain its manifest and Freqtrade exports.
- [ ] Start `make dry-run` only after a `PASS` verdict.
- [ ] For `WARN` or `FAIL`, retain evidence and create a new hypothesis; do not alter thresholds in the same loop.
