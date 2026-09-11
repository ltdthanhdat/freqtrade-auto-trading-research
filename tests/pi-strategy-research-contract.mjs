import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(".pi/extensions/strategy-research.ts", "utf8");

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
