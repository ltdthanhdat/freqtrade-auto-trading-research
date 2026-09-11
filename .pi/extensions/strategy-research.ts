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
  const result = spawnSync("python3", ["-m", "research_runtime.cli"], {
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

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "strategy_research_runtime",
    label: "Strategy research runtime",
    description: "Call one validated Python research-runtime operation; state and files stay behind the typed boundary.",
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
      const response = invokeRuntime("start_or_resume_cycle", { now: new Date().toISOString() });
      updateStatus(ctx, response);
      pi.setActiveTools(["strategy_research_runtime"]);
      pi.sendUserMessage(
        "Run exactly one bounded research cycle through strategy_research_runtime. Load context, collect sources, assess provenance, propose at most three hypotheses, write and validate one candidate, record interpretation, finalize, then stop.",
      );
    },
  });
}
