/**
 * Universal DOM reducer for ext.extract payloads.
 * ESM compatible. Drop-in for MV3 SW (type: "module") or Node.
 */

/** @typedef {[number, number, number, number]} BBox */

const defaultOptions = {
  maxElements: 60,
  allowedRoles: ["a","button","input","textarea","select","span","p","label"],
  dupIoU: 0.88,
  dropDigitsShort: true,
  keepSpansWithText: true,
  minTextLenSpan: 2,      // drop single-char spans like "如/何/自/己"
  minAreaPx: 8 * 8,       // tiny dots are ignored
  preferAboveFoldY: 200,  // boost for elements near top
  // Generic noise patterns across languages
  noiseRegexps: [
    /ICP备|ICP\b|公网安备|备案|许可证|资格证|平台备字/i,
    /cookie|privacy|terms|免责声明|隐私|条款|协议|GDPR/i,
    /subscribe|newsletter|关注我们|站点地图|site\s*map/i,
    /©|copyright|版权所有/i,
    /客服|联系我们|联系\s*我们|about\s*us/i
  ],
  // Label normalization
  labelMaxLen: 120,
  // action inference
  inferAction: true,
  // Optional site profiles map (hostname -> partial options)
  profiles: {}
};

function deepMerge(base, patch) {
  if (!patch) return base;
  const out = { ...base };
  for (const k of Object.keys(patch)) {
    const v = patch[k];
    if (v && typeof v === "object" && !Array.isArray(v)) {
      out[k] = deepMerge(base[k] || {}, v);
    } else {
      out[k] = v;
    }
  }
  return out;
}

function optionsForUrl(url, opts) {
  try {
    const u = new URL(url);
    const host = u.hostname;
    const prof = opts.profiles?.[host] || null;
    return prof ? deepMerge(opts, prof) : opts;
  } catch {
    return opts;
  }
}

function normalizeText(t = "") {
  return (t || "")
    .replace(/\s+/g, " ")
    .trim();
}

function clipLen(s, n) {
  if (!s) return s;
  return s.length > n ? s.slice(0, n) + "…" : s;
}

function isDigitsOnly(t) {
  return /^[0-9]+$/.test(t);
}

function iou(a, b) {
  const [ax1, ay1, ax2, ay2] = a;
  const [bx1, by1, bx2, by2] = b;
  const ix1 = Math.max(ax1, bx1);
  const iy1 = Math.max(ay1, by1);
  const ix2 = Math.min(ax2, bx2);
  const iy2 = Math.min(ay2, by2);
  const iw = Math.max(0, ix2 - ix1);
  const ih = Math.max(0, iy2 - iy1);
  const inter = iw * ih;
  if (inter <= 0) return 0;
  const aArea = (ax2 - ax1) * (ay2 - ay1);
  const bArea = (bx2 - bx1) * (by2 - by1);
  return inter / (aArea + bArea - inter);
}

function centerOf(bbox) {
  const [x1, y1, x2, y2] = bbox;
  return [Math.round((x1 + x2) / 2), Math.round((y1 + y2) / 2)];
}

function areaOf(b) {
  return Math.max(0, (b[2] - b[0])) * Math.max(0, (b[3] - b[1]));
}

function looksLikeNoise(text, noiseRegexps) {
  if (!text) return false;
  return noiseRegexps.some(re => re.test(text));
}

function tokens(s) {
  return new Set(
    normalizeText(s)
      .toLowerCase()
      .split(/[^\p{L}\p{N}]+/u)
      .filter(Boolean)
  );
}

// Simple token Jaccard similarity (language-agnostic-ish)
function textSim(a, b) {
  const A = tokens(a), B = tokens(b);
  if (!A.size && !B.size) return 1;
  let inter = 0;
  for (const t of A) if (B.has(t)) inter++;
  const uni = A.size + B.size - inter;
  return inter / Math.max(1, uni);
}

function pickLabel(item, opts) {
  // we only have text/id/href; keep extensible
  const text = normalizeText(item.text || "");
  if (text) return clipLen(text, opts.labelMaxLen);
  if (item.id) return clipLen(item.id, opts.labelMaxLen);
  if (item.role === "input" || item.role === "textarea" || item.role === "select") return "输入框";
  if (item.href) return "链接";
  return "元素";
}

function inferAction(role, href) {
  if (role === "a" && href) return "navigate";
  if (role === "input" || role === "textarea") return "type";
  if (role === "select") return "select";
  return "click";
}

/**
 * Main reducer (site-agnostic with optional profiles)
 * @param {any} payload - ext.extract response JSON
 * @param {object} userOpts - partial options to override defaults
 */
export function reduceDomPayload(payload, userOpts = {}) {
  const baseOpts = deepMerge(defaultOptions, userOpts);
  const url = payload?.result?.meta?.url || "";
  const opts = optionsForUrl(url, baseOpts);

  const dom = payload?.result?.dom || {};
  const { vw, vh, dpr } = dom;
  const items = Array.isArray(dom.items) ? dom.items : [];

  // 1) pre-filter
  const filtered = [];
  for (const it of items) {
    const role = (it.role || "").toLowerCase();
    if (!opts.allowedRoles.includes(role)) continue;

    const bbox = it.bbox;
    if (!Array.isArray(bbox) || bbox.length !== 4) continue;
    if (areaOf(bbox) < opts.minAreaPx) continue;

    const text = normalizeText(it.text || "");
    const hasHref = !!it.href;
    const isInputLike = role === "input" || role === "textarea" || role === "select";

    // reject empty non-actionables
    if (!isInputLike && !hasHref && !text) continue;

    // spans/p: stricter rules
    if (!isInputLike && (role === "span" || role === "p" || role === "label")) {
      if (!opts.keepSpansWithText) continue;
      if (!text) continue;
      if (opts.minTextLenSpan && text.length < opts.minTextLenSpan) continue;
      if (opts.dropDigitsShort && isDigitsOnly(text) && text.length <= 3) continue;
      if (looksLikeNoise(text, opts.noiseRegexps)) continue;
    }

    // general noise
    if (looksLikeNoise(text, opts.noiseRegexps)) {
      // allow anchors with meaningful href despite noise
      if (!(role === "a" && hasHref)) continue;
    }

    filtered.push({
      id: it.id || null,
      role,
      text,
      href: hasHref ? it.href : undefined,
      bbox
    });
  }

  // 2) transform & score
  const transformed = filtered.map(it => {
    const label = pickLabel(it, opts);
    const [cx, cy] = centerOf(it.bbox);
    let score = 0;
    if (it.role === "button" || it.role === "a") score += 1.0;
    if (it.role === "input" || it.role === "textarea" || it.role === "select") score += 0.9;
    if (it.text) score += Math.min(0.45, it.text.length / 30);
    if (opts.preferAboveFoldY && it.bbox[1] < opts.preferAboveFoldY) score += 0.2;

    const el = {
      label,
      role: it.role,
      bbox: it.bbox,
      center: [cx, cy],
      id: it.id || undefined,
      href: it.href
    };
    if (opts.inferAction) el.action = inferAction(it.role, it.href);
    return { ...el, _score: score };
  });

  // 3) dedupe by (semantic label + IoU) OR high text similarity
  const sorted = transformed.sort((a, b) => b._score - a._score);
  const finalList = [];
  for (const e of sorted) {
    let dup = false;
    for (const k of finalList) {
      const sameRole = k.role === e.role;
      const labelClose = (k.label === e.label) || textSim(k.label, e.label) >= 0.85;
      if (sameRole && labelClose && iou(k.bbox, e.bbox) >= opts.dupIoU) {
        dup = true; break;
      }
    }
    if (!dup) finalList.push(e);
  }

  // 4) cap size & strip private fields
  const elements = finalList.slice(0, opts.maxElements).map(({ _score, ...rest }) => rest);

  // 5) small lookup index by text (for quick by-text targeting)
  const index = Object.create(null);
  for (let i = 0; i < elements.length; i++) {
    const key = normalizeText(elements[i].label).toLowerCase();
    if (key && !index[key]) index[key] = i; // first occurrence
  }

  return {
    url,
    title: payload?.result?.meta?.title || "",
    vw, vh, dpr,
    elements,
    index,
    _reduced: true,
    _version: "u1"
  };
}