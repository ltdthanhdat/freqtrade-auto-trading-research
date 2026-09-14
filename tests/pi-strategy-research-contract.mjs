import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(".pi/extensions/strategy-research.ts", "utf8");
const prompt = readFileSync("prompts/strategy-research.md", "utf8");

test("extension pins Luna Max and exposes one runtime tool", () => {
  assert.match(source, /openai-codex.*gpt-5\.6-luna/);
  assert.match(source, /setThinkingLevel\("max"\)/);
  assert.match(source, /ui\.setStatus\("strategy-research"/);
  assert.equal((source.match(/registerTool\(/g) ?? []).length, 1);
  assert.doesNotMatch(source, /dry-run|compose-live|freqtrade-live/);
});

test("runtime errors include the structured code and details", () => {
  assert.match(source, /if \(!response\.ok\)/);
  assert.match(source, /response\.error\.code/);
  assert.match(source, /response\.error\.details/);
});

test("runtime uses the project Python environment", () => {
  assert.match(source, /spawnSync\("uv",\s*\["run",\s*"python3?"/);
});

test("runtime tool documents its supported operations", () => {
  assert.match(
    source,
    /valid operations: start_or_resume_cycle, heartbeat_cycle, reconcile_cycle, load_context, .*collect_sources, record_source_assessment, .*propose_hypothesis, .*write_candidate, start_validation, record_interpretation, finalize_cycle/,
  );
});

test("research command does not message the agent without the lease", () => {
  assert.match(source, /response\.acquired\s*===\s*false/);
  assert.match(source, /return/);
  assert.match(source, /sendUserMessage/);
});

test("research command carries the prepared snapshot into the cycle", () => {
  assert.match(source, /RESEARCH_DATASET/);
  assert.match(source, /RESEARCH_TIMERANGE/);
  assert.match(source, /data preflight completed successfully/);
});

test("canonical prompt contains the bounded research protocol", () => {
  assert.match(prompt, /openalex, arxiv, and crossref/);
  assert.match(prompt, /do not use semantic_scholar/);
  assert.match(prompt, /list_source_views/);
  assert.match(prompt, /seal_hypothesis_ranking/);
  assert.match(prompt, /complete.*exit|exit.*evidence/i);
  assert.match(prompt, /OOS.*consum|consum.*OOS/i);
  assert.match(prompt, /no post-OOS tuning/i);
  assert.match(prompt, /entry_plan.*sizing_plan|sizing_plan.*entry_plan/i);
  assert.match(prompt, /role-specific claim-level evidence/i);
  assert.match(prompt, /shell.*SQL|SQL.*shell/i);
  assert.match(prompt, /parameter sweeps/i);
});

test("research prompt requires the complete sealed protocol", () => {
  for (const phrase of [
    "list_source_views",
    "seal_hypothesis_ranking",
    "role-specific claim-level",
    "entry_plan",
    "exit_designs",
    "sizing_plan",
    "cost_model",
    "development_protocol",
    "outer_acceptance_policy",
    "full_text_available",
    "parameter sweep",
    "post-OOS",
    "shell",
    "SQL",
    "TradingView",
    "record_interpretation",
    "finalize_cycle",
  ]) {
    assert.match(prompt, new RegExp(phrase.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&"), "i"));
  }
  assert.match(prompt, /required_data.*exactly.*OHLCV/i);
  assert.match(prompt, /explicit.*NONE/i);
  assert.match(prompt, /no automatic promotion|automatic.*promotion/i);
});

test("canonical prompt requires structured source assessments", () => {
  assert.match(prompt, /assessment.*relevance.*asset.*timeframe.*mechanism/);
  assert.match(prompt, /full_text_available/);
  assert.doesNotMatch(prompt, /full_text_available\s*:\s*true/);
  assert.match(prompt, /assessment.*relevance.*asset.*timeframe.*mechanism/);
});

test("runtime and manual command use the canonical prompt and explicit paths", () => {
  assert.match(source, /RESEARCH_DB/);
  assert.match(source, /RESEARCH_ARTIFACT_ROOT/);
  assert.match(source, /readFileSync\(new URL\("\.\.\/\.\.\/prompts\/strategy-research\.md", import\.meta\.url\), "utf8"\)/);
  assert.match(source, /\{\{CYCLE_ID\}\}/);
  assert.match(source, /\{\{VALIDATION_CONTEXT\}\}/);
  assert.doesNotMatch(source, /Run exactly one bounded research cycle through strategy_research_runtime\./);
});
