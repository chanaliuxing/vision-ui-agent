import { resolveRefs } from "./strings.js";

export interface SimCtx {
  vars: Record<string, any>;
  globals: Record<string, any>;
  outputs: Record<string, any>; // stepId -> outputs
}

export interface SimActionResult {
  ok: boolean;
  outputs?: Record<string, any>;
  duration_ms?: number;
  warning?: string;
}

export async function simulateAction(
  uses: string,
  params: any,
  ctx: SimCtx
): Promise<SimActionResult> {
  // 变量替换（深度）
  const p = resolveRefs(params || {}, ctx);

  switch (uses) {
    case "ext.open_url": {
      const url = p.url || "";
      const host = safeHost(url);
      return {
        ok: true,
        duration_ms: Math.max(200, Math.min(1200, (p.wait_dom_quiet_ms ?? 800))),
        outputs: { page: host, ready: true }
      };
    }
    case "ext.click": {
      return {
        ok: true,
        duration_ms: 100,
        outputs: {
          clicked: true,
          selector: p.selector || "",
          click_type: p.click_type || "single"
        }
      };
    }
    case "ext.key": {
      return {
        ok: true,
        duration_ms: 50,
        outputs: {
          sent: p.key,
          modifiers: p.modifiers || []
        }
      };
    }
    case "type_text": {
      const text = String(p.text ?? "");
      const per = Math.max(0, Math.min(15, p.delay_ms ?? 50));
      const dur = Math.min(2000, text.length * (per || 5));
      return {
        ok: true,
        duration_ms: dur,
        outputs: {
          typed_len: text.length,
          mode: p.mode || "auto",
          text: text
        }
      };
    }
    case "vision.find_element": {
      return {
        ok: true,
        duration_ms: Math.max(1000, Math.min(5000, 3000)),
        outputs: {
          found: true,
          description: p.description || "",
          confidence: 0.85,
          position: { x: 100, y: 200 }
        }
      };
    }
    case "llm.plan": {
      const goal = String(p.goal || "");
      const estimatedTokens = Math.max(100, Math.min(2000, goal.length * 4));
      return {
        ok: true,
        duration_ms: Math.max(2000, Math.min(10000, 5000)),
        outputs: {
          plan: `Generated plan for: ${goal}`,
          model: p.model || "gpt-4",
          tokens_used: estimatedTokens
        }
      };
    }
    case "llm.reply": {
      const prompt = String(p.prompt || "");
      const estimatedTokens = Math.max(50, Math.min(1000, prompt.length * 2));
      return {
        ok: true,
        duration_ms: Math.max(1000, Math.min(8000, 3000)),
        outputs: {
          reply: `Generated reply for: ${prompt.slice(0, 50)}...`,
          model: p.model || "gpt-4",
          tokens_used: estimatedTokens
        }
      };
    }
    case "ext.click": {
      // 支持 selector / (x,y) / ref（在 resolveRefs 后都变成具体值）
      const at = ("selector" in p)
        ? { selector: p.selector }
        : ("x" in p && "y" in p)
          ? { x: p.x, y: p.y }
          : { ref: p.ref };
      return { ok: true, duration_ms: 80, outputs: { clicked: true, at } };
    }
    case "vision.find_element_with_image_check": {
      // 产出 bbox/center/score/fingerprint_id（占位）
      const bbox = p.search_region || { x: 100, y: 200, w: 120, h: 36 };
      const center = [bbox.x + Math.round(bbox.w/2), bbox.y + Math.round(bbox.h/2)];
      const score = Math.max(0.76, p.threshold ?? 0.75);
      return {
        ok: true,
        duration_ms: 120,
        outputs: { bbox, center, score, fingerprint_id: p.anchor_image_id }
      };
    }
    case "ocr.extract_region": {
      const text = "Hello, world"; // 占位
      const lang = p.lang || "en";
      return { ok: true, duration_ms: 180, outputs: { text, lang } };
    }
    default:
      // 未定义的动作：返回通用 ok
      return {
        ok: true,
        duration_ms: 50,
        warning: `no simulator for action "${uses}"`,
        outputs: { ok: true }
      };
  }
}

function safeHost(url: string) {
  try {
    return new URL(url).host;
  } catch {
    return "";
  }
}