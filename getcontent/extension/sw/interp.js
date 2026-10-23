// Tiny mustache-like interpolation: "{{foo}}" -> ctx.foo ; supports deep "a.b.c".
export function renderString(tpl, ctx = {}) {
  if (typeof tpl !== 'string') return tpl;
  return tpl.replace(/\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}/g, (_m, path) => {
    const val = getPath(ctx, path);
    return val == null ? '' : String(val);
  });
}

export function renderDeep(obj, ctx = {}) {
  if (obj == null) return obj;
  if (Array.isArray(obj)) return obj.map(v => renderDeep(v, ctx));
  if (typeof obj === 'object') {
    const out = {};
    for (const k of Object.keys(obj)) out[k] = renderDeep(obj[k], ctx);
    return out;
  }
  if (typeof obj === 'string') return renderString(obj, ctx);
  return obj;
}

function getPath(obj, path) {
  const parts = String(path).split('.');
  let cur = obj;
  for (const p of parts) {
    if (cur == null) return undefined;
    cur = cur[p];
  }
  return cur;
}