import { spawnSync } from "node:child_process";
import { Type } from "@earendil-works/pi-ai";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

type RuntimeResponse = {
  ok: boolean;
  error?: { code: string; details: string[] };
  cycle?: { id: string; stage: string; status?: string };
  [key: string]: unknown;
};

export function invokeRuntime(tool: string, payload: Record<string, unknown>): RuntimeResponse {
  const result = spawnSync("uv", ["run", "python", "-m", "research_runtime.cli"], {
    input: `${JSON.stringify({ tool, payload })}\n`,
    encoding: "utf8",
  });
  if (result.status !== 0) {
    throw new Error(result.stderr || "research runtime failed");
  }
  let response: RuntimeResponse;
  try {
    response = JSON.parse(result.stdout) as RuntimeResponse;
  } catch (error) {
    throw new Error(`research runtime returned invalid JSON: ${String(error)}`);
  }
  if (!response.ok) {
    if (!response.error) throw new Error("runtime_error: missing error details");
    throw new Error(`${response.error.code}: ${response.error.details.join("; ")}`);
  }
  return response;
}

function updateStatus(ctx: ExtensionContext, response: RuntimeResponse): void {
  const cycle = response.cycle;
  if (!cycle) return;
  if (["COMPLETED", "NEEDS_REVIEW", "INCOMPLETE", "FAILED"].includes(cycle.status ?? "")) {
    ctx.ui.setStatus("strategy-research", undefined);
    return;
  }
  ctx.ui.setStatus("strategy-research", `${cycle.id} · ${cycle.stage}`);
}

function researchDataContext(): string {
  const dataset = process.env.RESEARCH_DATASET ?? "accepted_6pair_2026q3_full";
  const timerange = process.env.RESEARCH_TIMERANGE ?? "20260124-20260911";
  const relative = dataset.startsWith("snapshots/") ? dataset : `snapshots/${dataset}`;
  return `The data preflight completed successfully. Use datadir user_data/data/${relative} and frozen timerange ${timerange}.`;
}

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "strategy_research_runtime",
    label: "Strategy research runtime",
    description: "Call one validated Python research-runtime operation; valid operations: start_or_resume_cycle, load_context, collect_sources, record_source_assessment, propose_hypothesis, write_candidate, start_validation, record_interpretation, finalize_cycle. State and files stay behind the typed boundary.",
    promptSnippet: "Run a bounded strategy research runtime operation",
    parameters: Type.Object({
      tool: Type.String(),
      payload: Type.Object({}, { additionalProperties: true }),
    }),
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const response = invokeRuntime(params.tool, params.payload as Record<string, unknown>);
      updateStatus(ctx, response);
      return {
        content: [{ type: "text", text: JSON.stringify(response) }],
        details: response,
      };
    },
  });

  pi.registerCommand("research-cycle", {
    description: "Start or resume one bounded automated strategy research cycle",
    handler: async (_args, ctx) => {
      const model = ctx.modelRegistry.find("openai-codex", "gpt-5.6-luna");
      if (!model) throw new Error("required model openai-codex/gpt-5.6-luna is unavailable");
      if (!(await pi.setModel(model))) throw new Error("required model authentication is unavailable");
      pi.setThinkingLevel("max");
      const dataset = process.env.RESEARCH_DATASET ?? "accepted_6pair_2026q3_full";
      const timerange = process.env.RESEARCH_TIMERANGE ?? "20260124-20260911";
      const response = invokeRuntime("start_or_resume_cycle", {
        now: new Date().toISOString(),
        dataset,
        requested_timerange: timerange,
        search_cohort: "openalex|arxiv|crossref",
      });
      updateStatus(ctx, response);
      pi.setActiveTools(["strategy_research_runtime"]);
      pi.sendUserMessage(
        `Run exactly one bounded research cycle through strategy_research_runtime. ${researchDataContext()} Load context, collect at most four sources each from openalex, arxiv, and crossref (do not use semantic_scholar), then record structured source assessments. For every source call record_source_assessment with an object exactly like assessment: {relevance: "direct|indirect|contradicting", asset: "crypto", timeframe: "30m/1h", mechanism: "...", full_text_available: true, falsifier_only: false}; never pass a free-text string. Every proposed hypothesis must use required_data exactly ["OHLCV"], cite at least one direct supporting source and one direct/contradicting source, and state a falsifier. If that evidence is unavailable, keep it out of candidate generation. Propose at most three hypotheses, write and validate one candidate, record interpretation, finalize, then stop. Use only the documented runtime operations; if a provider returns a retryable error, record it and continue with another provider. Do not start trading, alter the parent strategy/config/policy, or tune after a failed validation.`,
      );
    },
  });
}
