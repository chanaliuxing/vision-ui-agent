const REF = /\$\{([^}]+)\}/g;

export function resolveRefs(value: any, ctx: Record<string, any>): any {
  if (value == null) return value;
  if (typeof value === "string") {
    return value.replace(REF, (_, expr) => {
      try {
        const v = readRef(expr, ctx);
        return v == null ? "" : String(v);
      } catch {
        return "";
      }
    });
  }
  if (Array.isArray(value)) return value.map(v => resolveRefs(v, ctx));
  if (typeof value === "object") {
    const out: any = {};
    for (const k of Object.keys(value)) out[k] = resolveRefs(value[k], ctx);
    return out;
  }
  return value;
}

export function readRef(expr: string, ctx: Record<string, any>): any {
  // 允许 vars.* / globals.env.* / outputs.<step>.*
  if (expr.startsWith("vars.")) {
    return pick(ctx.vars || {}, expr.slice(5));
  }
  if (expr.startsWith("globals.env.")) {
    return pick(((ctx.globals || {}).env) || {}, expr.slice(12));
  }
  if (expr.startsWith("outputs.")) {
    return pick(ctx.outputs || {}, expr.slice(8));
  }
  // 直接量：true/false 或简单名字（如 vars.x）
  if (expr === "true") return true;
  if (expr === "false") return false;
  if (expr === "null") return null;
  // 简单直取：vars.x / globals.device_target
  return pick(ctx, expr);
}

function pick(obj: any, path: string) {
  const segs = path.split(".");
  let cur = obj;
  for (const s of segs) {
    if (cur == null) return undefined;
    cur = cur[s];
  }
  return cur;
}