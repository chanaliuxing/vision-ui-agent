import { evalCond } from "./cond.js";
import { simulateAction, SimCtx } from "./actions.js";
import { SimResult, SimTraceEntry } from "./types.js";
import { loadActionSchemas } from "../lib/ajv.js";
import { createDefaultProvider, createReplayProvider, createFingerprintProvider, SimEvidenceProvider, DeviceProfile } from "./providers.js";
import { resolveRefs } from "./strings.js";

type WF = {
  start: string;
  steps: Array<any>;
  edges?: Array<{ from: string; to: string; condition?: string }>;
  globals?: any;
  variables?: any;
};

function buildAdj(wf: WF) {
  const adj = new Map<string, Array<{ to: string; condition?: string }>>();
  for (const s of wf.steps) adj.set(s.id, []);
  if (wf.edges?.length) {
    for (const e of wf.edges) {
      if (!adj.has(e.from)) adj.set(e.from, []);
      adj.get(e.from)!.push({ to: e.to, condition: e.condition });
    }
  } else {
    for (let i = 0; i < wf.steps.length - 1; i++) {
      adj.get(wf.steps[i].id)!.push({ to: wf.steps[i + 1].id });
    }
  }
  return adj;
}

function findStep(wf: WF, id: string) {
  return wf.steps.find(s => s.id === id);
}

export async function simulateWorkflow(
  wf: WF,
  seed?: number,
  opts?: {
    provider?: "default"|"replay"|"fingerprint",
    device?: DeviceProfile,
    replay_trace?: any[],
    fingerprint_index?: Record<string,any>,
    explain?: boolean
  }
): Promise<SimResult & { debug?: any[] }> {
  const device: DeviceProfile = opts?.device || { width: 1440, height: 900, scale: 1, name: "web-1440x900" };

  let provider: SimEvidenceProvider;
  switch (opts?.provider) {
    case "replay": provider = createReplayProvider(opts?.replay_trace || []); break;
    case "fingerprint": provider = createFingerprintProvider(opts?.fingerprint_index || {}); break;
    default: provider = createDefaultProvider(seed ?? 1);
  }

  const ctx: SimCtx = { vars: wf.variables || {}, globals: wf.globals || {}, outputs: {} };
  const adj = buildAdj(wf);
  const trace: SimTraceEntry[] = [];
  const debug: any[] = [];
  const warnings: string[] = [];
  let estimates = { llm_tokens: 0, llm_calls: 0 };

  // Load action schemas for cost estimation
  const actionSchemas = loadActionSchemas();

  // 预算估算（非常轻量）
  for (const s of wf.steps) {
    if (s.type !== "action") continue;
    const actionDef = actionSchemas[s.uses];
    if (actionDef?.cost_estimate?.llm_tokens) {
      estimates.llm_tokens += actionDef.cost_estimate.llm_tokens;
    }
    if (String(s.uses || "").startsWith("llm.")) {
      estimates.llm_calls += 1;
      if (typeof s.params?.prompt === "string") {
        estimates.llm_tokens += Math.ceil(s.params.prompt.length / 4);
      }
    }
  }

  let cur = wf.start;
  let safety = 0;
  while (cur && safety++ < 1000) {
    const step = findStep(wf, cur);
    if (!step) break;

    // 参数替换（用于 debug 展示）
    const paramsResolved = resolveRefs(step.params || {}, { ...ctx });

    // 覆盖特定动作的占位：selector/ref/fingerprint → 用 provider 计算更真实点位
    if (step.type === "action") {
      if (step.uses === "ext.click") {
        if (paramsResolved.selector && !("x" in paramsResolved) && !("y" in paramsResolved)) {
          const pt = provider.selectorToPoint(paramsResolved.selector, device);
          if (pt) { paramsResolved.x = pt.x; paramsResolved.y = pt.y; delete paramsResolved.selector; }
        } else if (paramsResolved.ref && Array.isArray(paramsResolved.ref)) {
          // 如果 ref 解析成 [x,y] 数组，落地为 x/y
          const [x,y] = paramsResolved.ref;
          paramsResolved.x = x; paramsResolved.y = y; delete paramsResolved.ref;
        }
      }
      if (step.uses === "vision.find_element_with_image_check") {
        if (paramsResolved.anchor_image_id && !paramsResolved.search_region) {
          const b = provider.fingerprintToBox(paramsResolved.anchor_image_id, device);
          if (b) { paramsResolved.search_region = b; }
        }
      }
      if (step.uses === "ocr.extract_region") {
        // 若 ref 已解析为 bbox，把它放进 region
        if (!paramsResolved.region && typeof paramsResolved.ref === "object" &&
            "x" in paramsResolved.ref && "y" in paramsResolved.ref) {
          paramsResolved.region = paramsResolved.ref; delete paramsResolved.ref;
        }
      }
    }

    // 执行动作（传入**落地后的**参数）
    const started = Date.now();
    let entry: SimTraceEntry;
    if (step.type === "action") {
      const r = await simulateAction(step.uses, paramsResolved, ctx);
      entry = {
        id: step.id, name: step.name, uses: step.uses,
        status: r.ok ? "ok" : "error",
        started_ms: started, duration_ms: r.duration_ms ?? 0,
        outputs: r.outputs, warning: r.warning
      };
      ctx.outputs[step.id] = r.outputs || {};
      if (r.warning) warnings.push(r.warning);
    } else {
      entry = { id: step.id, name: step.name, uses: step.type, status: "ok", started_ms: started, duration_ms: 0 };
    }
    trace.push(entry);

    if (opts?.explain) {
      debug.push({
        step: step.id,
        provider: provider.name,
        device,
        params_before: step.params || {},
        params_after: paramsResolved,
      });
    }

    // 挑选下一条边（附 explain）
    const options = adj.get(step.id) || [];
    let next = "";
    let chosen: any = null;
    for (const opt of options) {
      const ok = evalCond(opt.condition, { ...ctx, step });
      if (opts?.explain) {
        debug.push({ from: step.id, to: opt.to, condition: opt.condition ?? "<default>", result: ok });
      }
      if (ok) { next = opt.to; chosen = opt; break; }
    }
    if (!next) break;
    cur = next;
  }

  const base = {
    trace,
    estimates,
    warnings,
    final_outputs: ctx.outputs,
    workflow_name: (wf as any).name,
    workflow_version: (wf as any).version
  };
  return opts?.explain ? { ...base, debug } : base;
}

// 简易 RNG（占位）
function mulberry32(a: number) {
  return function() {
    let t = (a += 0x6D2B79F5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}