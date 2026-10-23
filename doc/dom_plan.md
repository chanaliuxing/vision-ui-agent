阶段1:
完全可以做成**站点无关**的通用 reducer。下面这版是“默认通用 + 可选站点 profile 覆盖”的设计，不绑死小红书，适用于多数网站；需要特殊规则时只加一个小小的 `profile` 配置即可。

我给你一份可直接落地的 **reducer.js**（ESM，可在 MV3 Service Worker 直接 `import`；也可 Node 用）。要点：

* 只保留对自动化有用的字段：`label, role, bbox, center, id?, href?`
* 自动推断 `action`：`navigate | click | type | select`
* 文本来源优先级：`text`（已给）→（可扩展：ariaLabel/title/placeholder）
* 强去重：同义文本 + 高 IoU 的重叠元素合并
* 语言无关噪声过滤：可配置 `noiseRegexps`（默认含 ICP/备案/隐私/条款/subscribe/cookie 等多语言关键词）
* 兼容“拆字 span”（单字/极短文本）过滤
* 允许用 `profiles[hostname]` 覆盖默认参数（比如新闻站/商城/社区）

---

### reducer.js

```js
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
  minTextLenSpan: 2,      // drop single-char spans like “如/何/自/己”
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
```

---

### 可选：按域名覆盖（完全非必需）

```js
import { reduceDomPayload } from "./reducer.js";

const compact = reduceDomPayload(payload, {
  maxElements: 50,
  profiles: {
    "www.youtube.com": {
      // 例：YouTube 评论区数字较多，放宽 digits 过滤
      dropDigitsShort: false,
      minTextLenSpan: 1
    },
    "news.ycombinator.com": {
      // 例：更偏文本链接，放宽 span/p
      keepSpansWithText: true,
      minTextLenSpan: 1
    }
  }
});
```

---

### 在插件端怎么接（SW 里做最稳）

```js
// sw/bootstrap.js
import { reduceDomPayload } from "../reducer.js";

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "EXT_EXTRACT_RAW") {
    const reduced = reduceDomPayload(msg.payload, {
      maxElements: 45
      // profiles: { ... }  // 需要时再配
    });
    console.log("[DOM REDUCED]", reduced);
    // 把 reduced 串给你的执行器/后端/LLM
    // fetch("http://127.0.0.1:8787/ingest", { method: "POST", body: JSON.stringify(reduced) });
    sendResponse?.(reduced);
  }
  return true;
});
```

---

### 这版为什么“站点无关”

* 过滤规则只基于**通用语义**（role、是否可导航/可输入、文本是否有意义、尺寸/位置、重复 IoU），而非页面特定结构。
* 噪声规则用了**多语言通用关键词**（可增减），避免绑定单一站点。
* 保留 **profile 钩子**：真的遇到个别站点需要特例，你只改一个小对象，不要 fork reducer。

---

阶段2:
我把“通用版 reducer”的**整套 MV3 集成样例**给你——按这个落地后，你传出去的就会是精简 JSON（带 `_reduced: true` 标记）。直接复制到你的插件里即可。

---

### 1) `manifest.json`

```json
{
  "manifest_version": 3,
  "name": "Auto Runner (with DOM Reducer)",
  "version": "0.3.0",
  "background": { "service_worker": "sw/bootstrap.js", "type": "module" },
  "permissions": ["storage", "activeTab", "scripting", "tabs"],
  "host_permissions": ["<all_urls>"],
  "content_scripts": [
    {
      "matches": ["<all_urls>"],
      "js": ["content/extract-bridge.js"],
      "run_at": "document_idle"
    }
  ]
}
```

---

### 2) `sw/bootstrap.js`（在 SW 里做精简）

```js
// sw/bootstrap.js
import { reduceDomPayload } from "../lib/reducer.js";

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg?.type === "EXT_EXTRACT_RAW") {
    try {
      const reduced = reduceDomPayload(msg.payload, {
        maxElements: 50,
        dupIoU: 0.9,
        minTextLenSpan: 2,
        // profiles: { "example.com": { dropDigitsShort:false } } // 需要时再加
      });
      // 可选：保存最近一次，方便调试/回放
      chrome.storage.session.set({ LAST_DOM_REDUCED: reduced });
      // 你自己的后端/执行器（可选）
      // fetch("http://127.0.0.1:8787/ingest", { method:"POST", body: JSON.stringify(reduced) });
      sendResponse(reduced);      // 回给 content 或调用方
      console.log("[DOM REDUCED]", reduced);
    } catch (e) {
      console.error("[REDUCE FAILED]", e);
      sendResponse({ _reduced: false, error: String(e) });
    }
    return true; // 允许异步
  }
});
```

---

### 3) `content/extract-bridge.js`（把原始 ext.extract 结果发给 SW）

```js
// content/extract-bridge.js
// ⚠️ 这里假设你已有 ext.extract 的调用；只需要在拿到“原始 payload”时调用 sendRaw() 即可。

async function sendRaw(payload) {
  try {
    const reduced = await chrome.runtime.sendMessage({ type: "EXT_EXTRACT_RAW", payload });
    // 之后的流程请改用 reduced（而不是原始 payload）
    // 比如：window.postMessage({ type:"DOM_REDUCED", data: reduced }, "*");
    console.debug("[content] reduced:", reduced);
  } catch (e) {
    console.error("[content] send raw failed", e);
  }
}

// ✅ 给你一个全局桥，方便在现有代码里直接调用：
window.__ext_extract_onDone__ = (payload) => {
  // payload 就是你现在打印的那个原始大 JSON
  sendRaw(payload);
};

// 也可以直接在你 ext.extract 的回调里调：
// onExtractDone(payload) { sendRaw(payload) }
```

> 现在你只需要把 **ext.extract 完成的回调**改成调用 `window.__ext_extract_onDone__(payload)`（或直接调用 `sendRaw(payload)`），后面就全是精简 JSON 了。

---

### 4) `lib/reducer.js`（站点无关通用版）

把我上一条消息给你的 **“Universal reducer”** 文件另存为 `lib/reducer.js`，原样放进去即可用。它是 ESM，可直接被 SW `import`。

---

## 如何验证“已经改成精简版”

1. 在 `chrome://extensions` 里 **重新加载** 插件。
2. 打开任意目标页面，触发一次 `ext.extract`。
3. 看 **Service Worker 控制台**（扩展详情 → Service Worker → Inspect views）：

   * 能看到 `console.log("[DOM REDUCED]", reduced)`；
   * 对象里有 `_reduced: true`、`_version: "u1"`；
   * `elements` 是几十条以内的简洁项（每条仅 `label/role/bbox/center/id?/href?/action`）。
4. 你自己的后续逻辑**改用 `reduced`**（不要再把原始 `payload` 传给 LLM/执行器）。

---

## 常见坑位速查

* 还在上传原始 JSON：确认你**改用**了 `sendResponse(reduced)` 的返回。
* SW 未生效：记得“重新加载扩展”，并重新打开页面触发一次。
* content 里 import 失败：我们把 reducer 放在 **SW**，避免了 MV3 content ESM 限制。
* 需要站点特例：给 `reduceDomPayload(..., { profiles: { "foo.com": { … }}})` 加配置即可，无需改 reducer 代码。

---
棒！最后给你一份超短“落地检查清单”，照着走就能确认全链路都在用精简版 👇

### 快速检查清单

1. **接线**

   * `content` 里在 `ext.extract` 回调调用 `chrome.runtime.sendMessage({type:"EXT_EXTRACT_RAW", payload})`（或用我给的 `__ext_extract_onDone__`）。
   * `sw/bootstrap.js` 收到后 `reduceDomPayload(...)`，`sendResponse(reduced)` 回给前端或直接转发到你的执行器。

2. **验证**

   * 重新加载扩展 → 打开页面触发一次 `ext.extract`。
   * 看 SW 控制台：应打印 `[DOM REDUCED]`，对象里有 `_reduced: true`、`_version: "u1"`，`elements` 数量几十个以内。

3. **切换到精简结果**

   * 后续 LLM/执行器的输入改为 **`reduced`**（不要再用原始 `payload`）。
   * 建议加个 `featureFlag`：`useReduced = true/false`，方便 A/B 对比。

4. **最小契约（给执行器/LLM）**

   * `elements[]` 每项字段：`label, role, bbox, center, id?, href?, action?`
   * 页面级：`url, title, vw, vh, dpr, index(按label到下标)`

### 可选增强（随手就能加）

* **站点 profile**：`profiles: { "foo.com": { dropDigitsShort:false } }`
* **拆字过滤**：`minTextLenSpan: 2`（已默认）
* **日志留存**：`chrome.storage.session.set({LAST_DOM_REDUCED})`
* **回退策略**：`elements.length===0` 时回传原始或放宽过滤参数一次

phase3:
**统一的 PAV 回路**：**Plan → Act → Validate**。下面给你一套“站点无关”的落地方案：通用数据结构 + 轻量规则校验 + LLM 复核（仅在不确定时触发），外加可直接抄用的 TypeScript 接口与伪代码。

---

# 一、整体闭环

1. **Plan（LLM/策略）**

* LLM 产出一步或多步的计划，每步自带**成功判定条件**（URL/标题/元素/文本等），避免事后猜。

2. **Act（DOM 执行）**

* 插件/执行器按 reducer 的 `elements[]` 执行点击/输入/选择等。

3. **Validate（校验）**

* 先跑一轮**本地确定性校验（便宜、快）**：URL/Title/元素存在、文字包含、网络导航事件。
* 如果**明确成功/失败**，直接决定下一步或修复。
* 如果**不确定**（灰区），把“前后对比 + 历史 + 预期”发给 LLM 做**复核**，让 LLM 输出“成功/失败/不确定 + 原因 + 建议下一步”。

> 目标：**优先本地规则**，**按需 LLM**，可控成本、稳定行为。

---

# 二、通用数据结构（强烈建议固定 schema）

### 1) 计划步骤（PlanStep）

```ts
interface PlanStep {
  task_id: string;             // 任务 id
  step_no: number;             // 步序
  goal: string;                // “打开通知页”、“搜索‘苹果手机’”...
  action: "click"|"type"|"select"|"navigate";
  target: {                    // 和 reducer 输出对齐
    by: "index"|"text"|"href"|"id";
    value: number|string;
    fallback?: Array<{by:"text"|"href"|"id", value:string}>;
  };
  input_text?: string;         // type/select 时需要
  // 成功判定——由 LLM 在 Plan 阶段就给出（站点无关）
  success_criteria: {
    url_contains?: string[];
    url_regex?: string[];
    title_includes?: string[];
    must_exist?: string[];     // 文字/按钮/标签（用 reducer 的 label/text 匹配）
    must_not_exist?: string[];
    text_includes?: string[];  // 页面上出现的关键片段
    timeout_ms?: number;       // 等待上限
  };
}
```

### 2) 执行报告（ExecutionReport）——发给 LLM 复核用

```ts
interface ReducedDom {
  url: string;
  title: string;
  vw: number; vh: number; dpr: number;
  elements: Array<{label:string; role:string; bbox:[number,number,number,number]; center:[number,number]; id?:string; href?:string; action?:string;}>;
  index: Record<string, number>;
  _reduced: true;
  _version: string;
}

interface StepRuntime {
  ts_start: number;
  ts_end: number;
  duration_ms: number;
  nav_events: Array<{
    type: "committed"|"completed"|"error"|"redirect";
    url: string; time: number;
  }>;
  net_requests: number;       // 可选：通过 CDP 数一下
  screenshot?: string;        // 可选：dataURL/base64（小图）
  error?: string;             // 本地执行异常
}

interface ExecutionReport {
  exec_id: string;
  task_id: string;
  step_no: number;
  goal: string;
  plan_step: PlanStep;
  history: Array<{
    step_no: number;
    action: string;
    target_label?: string;
    url_after: string;
    ok: boolean;
  }>;
  pre_context: ReducedDom;          // 执行前
  action_sent: {                    // 发起的动作实参
    action: "click"|"type"|"select"|"navigate";
    target_resolved: { by:"index"|"text"|"href"|"id"; value:number|string; label?:string; };
    input_text?: string;
  };
  runtime: StepRuntime;
  post_context: ReducedDom;         // 执行后
  diff: {                           // 关键差异，先做轻量本地 diff
    url_changed: boolean;
    title_changed: boolean;
    appeared_labels: string[];      // 新增的 labels（如“通知”）
    disappeared_labels: string[];   // 消失的 labels（如“发布”）
  };
  local_validation: {               // 本地判定结果（详见下一节）
    status: "success"|"failure"|"uncertain";
    reasons: string[];
    matched_criteria: string[];     // 命中的规则名，方便可视化
    confidence: number;             // 0~1
  };
}
```

### 3) LLM 验证回包（ValidationVerdict）

```ts
interface ValidationVerdict {
  status: "success"|"failure"|"uncertain";
  confidence: number;              // 0~1
  reasoning: string[];             // 简要原因
  is_on_expected_page?: boolean;   // 是否到了预期页面
  recommended_next_steps: Array<{
    action: "proceed"|"retry"|"wait"|"scroll"|"back"|"alt_target"|"abort";
    notes?: string;
    alt_target?: { by:"text"|"href"|"id"; value:string };
  }>;
  // 可选：补充/修正成功判定条件（让后续更稳）
  refined_success_criteria?: PlanStep["success_criteria"];
}
```

---

# 三、本地确定性校验（先跑它，再决定要不要问 LLM）

**输入**：`plan_step.success_criteria + pre/post_context + runtime + diff`

**检查集（建议至少包含以下 7 条）：**

1. **URL**：`url_contains` / `url_regex` 命中数。
2. **标题**：`title_includes` 命中。
3. **元素存在**：`must_exist` 在 `post_context.elements[].label` 中存在；`must_not_exist` 不存在。
4. **文本片段**：在 `post_context.elements[].label` 或页面可见文本里是否包含（可用 reducer 的 label 聚合）。
5. **导航事件**：是否有 `webNavigation.onCommitted/completed`；有则加分。
6. **结构变化**：`diff.appeared_labels/disappeared_labels` 是否符合预期（比如“登录”→“退出登录”）。
7. **时间**：是否在 `timeout_ms` 内完成；过长则扣分。

**打分→结论（示例规则）：**

```txt
+0.4 URL 命中（contains/regex 任一）
+0.2 标题包含
+0.2 must_exist 全部满足（≥1 给 0.1，全部满足给 0.2）
+0.1 text_includes 任意命中
+0.1 有导航 committed/completed 事件
-0.3 出现 must_not_exist
-0.2 超时
≥0.6 => "success"
≤0.2 => "failure"
else => "uncertain"
```

---

# 四、何时调用 LLM 验证（降本策略）

* 只有 **local\_validation.status === "uncertain"** 才调用 LLM。
* 若 `failure` 但存在 **可恢复信号**（如需先登录/弹窗遮挡），也可调用 LLM 让它给出**修复建议**。
* 成功与失败都很明显时**不调用**，直接进入下一步或修复/回退。

---

# 五、LLM 验证 Prompt 模板（片段）

**System**（简）：

> 你是网页自动化的验证器。根据“计划目标、成功判定、执行前后上下文、历史与运行信号”，判断这一步是否达成目标，并给出后续动作建议。必须输出严格 JSON，遵循 `ValidationVerdict`。

**User**（结构化喂给 LLM）：

```json
{
  "plan_step": { ... },
  "execution_report": { ... }  // 上文的 ExecutionReport（可裁剪 elements 到前 30）
}
```

**LLM 输出（示例）：**

```json
{
  "status": "success",
  "confidence": 0.78,
  "reasoning": [
    "URL 包含 /notification",
    "标题含有 '通知'",
    "出现了 '全部通知' 与 '未读' 标签"
  ],
  "is_on_expected_page": true,
  "recommended_next_steps": [
    { "action": "proceed", "notes": "继续执行下一步筛选未读" }
  ]
}
```

---

# 六、执行器决策（统一策略）

```ts
function decideNext(local: ExecutionReport["local_validation"], llm?: ValidationVerdict) {
  const v = llm ?? local;
  if (v.status === "success") return { do: "next" };
  if (v.status === "failure") return { do: "repair_or_abort" }; // 重试/切换候选/回退
  // uncertain
  return { do: "probe" }; // 滚动/延时/再次尝试 alternative target
}
```

---

# 七、最小实现骨架（TypeScript 伪代码）

```ts
async function runStep(plan: PlanStep, ctxBefore: ReducedDom): Promise<ExecutionReport> {
  const ts0 = Date.now();

  // 1) 解析目标
  const target = resolveTarget(plan.target, ctxBefore); // 按 index/text/href/id 找 reducer 元素

  // 2) 执行动作（click/type/select/navigate）
  const runtime: StepRuntime = await performActionAndObserve(target, plan, { timeout: plan.success_criteria?.timeout_ms ?? 8000 });

  // 3) 获取 post DOM（reducer 版）
  const ctxAfter = await getReducedDom();

  // 4) 轻量 diff
  const diff = makeDiff(ctxBefore, ctxAfter);

  // 5) 本地校验
  const local = validateLocal(plan.success_criteria, ctxAfter, diff, runtime);

  // 6) 组装报告
  const report: ExecutionReport = {
    exec_id: genId(),
    task_id: plan.task_id,
    step_no: plan.step_no,
    goal: plan.goal,
    plan_step: plan,
    history: getRecentHistory(),
    pre_context: ctxBefore,
    action_sent: { action: plan.action, target_resolved: target, input_text: plan.input_text },
    runtime,
    post_context: ctxAfter,
    diff,
    local_validation: local
  };

  // 7) 灰区时调用 LLM 复核
  if (local.status === "uncertain" || (local.status==="failure" && mayRecover(runtime))) {
    const llmVerdict = await callLLMValidator(report); // 使用上面的 Prompt 模板
    return annotate(report, { llmVerdict });
  }

  return report;
}
```

---

# 八、工程化建议

* **把 success\_criteria 下放到“计划阶段”**：让 LLM 在出步骤时就声明“如何算成功”。
* **日志 & 回放**：保存 `ExecutionReport`（可裁剪 elements 到 20–30 项）+ 小尺寸 screenshot，便于复现。
* **选择器多样性**：`target.fallback[]` 放入多种定位（text/href/id），失败时快速切换。
* **错误库**：为常见失败建库（登录态丢失、弹窗遮挡、反爬验证），配对应“修复动作模板”。
* **降本**：先本地校验，灰区再 LLM；LLM 的上下文裁剪到**与 criteria 强相关的 elements**。

phase 4:
需要“失败→介入→回退→拉黑→继续”的闭环。下面给你一套**通用可落地**的实现思路 + TypeScript骨架，直接接到你现有的 PAV（Plan→Act→Validate）里就能跑。

---

# 设计要点（站点无关）

* **两层验证**：本地规则校验 →（不通过）→ YOLO+LLM 介入再验证
* **回退策略**：二次验证仍失败 → 回退（`history.back()`/上一URL/上一步DOM快照）
* **黑名单**：将本次点击的“目标签名”按**阶段+页面指纹**加入黑名单（TTL/限次），后续同阶段不再点它
* **继续执行**：回退后等待页面稳定（`ext.wait_quiet`/DOM静默），按当前阶段继续 DOM+LLM

---

# 关键数据结构

```ts
type BBox = [number, number, number, number];

interface TargetSig {
  role: string;
  label?: string;
  href?: string;
  id?: string;
  bbox?: BBox;            // 用于近似匹配
}

interface PageSig {
  host: string;           // new URL(ctx.url).host
  urlPathHash: string;    // 归一化后的 path + query(白名单) 哈希
  domHash: string;        // reducer elements 前N项(label+role+href)哈希
}

interface PhaseKey { task_id: string; phase_id: string; }

interface BlacklistEntry {
  phase: PhaseKey;
  page: PageSig;
  target: TargetSig;
  reason: "validation_fail" | "llm_miss" | "user_abort";
  ts: number;
  ttl_ms: number;         // 例如 7天
  hits: number;           // 命中次数
  max_hits: number;       // 超过就永久拉黑
}

interface Validation {
  status: "success"|"failure"|"uncertain";
  confidence: number;     // 0~1
  reasons: string[];
}

interface ExecutionReport { /* 用你之前那套 ExecutionReport */ }
```

---

# 核心流程（伪代码）

```ts
async function runStepWithRecovery(planStep: PlanStep, phase: PhaseKey) {
  const pre = await getReducedDom();                        // 执行前DOM
  const target = resolveTarget(planStep, pre, phase);       // 避开黑名单
  const actResult = await performAction(target, planStep);  // click/type/select
  const post = await getReducedDom();                       // 执行后DOM

  // 1) 本地规则校验
  const local = validateLocal(planStep.success_criteria, pre, post, actResult);

  if (local.status === "success") return { ok: true, report: mkReport(pre, post, actResult, local) };

  // 2) YOLO+LLM 介入（只在失败或不确定才调）
  const yoloVerdict = await interveneWithYOLOLLM(planStep, pre, post, actResult, phase);

  if (yoloVerdict.status === "success") {
    return { ok: true, report: mkReport(pre, await getReducedDom(), actResult, yoloVerdict) };
  }

  // 3) 仍失败 → 回退 & 拉黑
  await rollbackToPrevious();                               // history.back()/直跳上URL/关闭遮罩
  await waitQuiet({ timeout: 10000, poll: 300 });

  addToBlacklist(phase, pageSignature(pre), targetSignature(target), {
    reason: "validation_fail", ttl_ms: 7*24*3600*1000, max_hits: 3
  });

  // 4) 继续：同一阶段重新“DOM+LLM”规划
  return { ok: false, action: "retry_phase" };
}
```

---

# 关键函数实现要点

### 1) 目标解析（避开黑名单）

```ts
function resolveTarget(planStep: PlanStep, ctx: ReducedDom, phase: PhaseKey) {
  const candidates = enumerateCandidates(planStep, ctx);  // 由 reducer elements 推出候选
  const page = pageSignature(ctx);
  const filtered = candidates.filter(c => !isBlacklisted(phase, page, targetSignature(c)));
  if (!filtered.length) throw new Error("All candidates blacklisted");
  return filtered[0]; // 可按置信度/位置/权重排序
}
```

### 2) YOLO+LLM 介入

* 输入：`plan_step + pre/post DOM + 最近点击历史 + 小截图（可选）`
* LLM 任务：

  1. 复核是否已满足目标（有时成功但本地规则没命中）
  2. 若未满足，**给出替代目标**（按 label/href/相邻锚点描述）
* YOLO 任务：

  * 用 LLM 给的“视觉线索/文案/图标名”在截图中定位元素（或从 reducer elements 里二次筛选）
  * 返回新的 click 坐标/候选 element，再执行并**再次本地验证**

```ts
async function interveneWithYOLOLLM(plan: PlanStep, pre: ReducedDom, post: ReducedDom, act: StepRuntime, phase: PhaseKey): Promise<Validation> {
  const llm = await callLLMValidator({ plan, pre, post, act, history: getRecentHistory(5) });

  if (llm.status === "success") return llm;  // LLM 判定其实已成功（常见：URL/标题变种）

  if (llm.status !== "failure" && llm.recommended_next_steps) {
    const alt = llm.recommended_next_steps.find(s => s.action === "alt_target" && s.alt_target);
    if (alt) {
      // 用 YOLO / 二次匹配去找这个替代目标
      const probe = await findWithYOLOOrHeuristic(alt.alt_target, await getScreenshot(), await getReducedDom());
      if (probe) {
        const act2 = await performAction(probe, plan);
        const post2 = await getReducedDom();
        const local2 = validateLocal(plan.success_criteria, post, post2, act2);
        if (local2.status === "success") return local2;
      }
    }
  }

  return { status: "failure", confidence: 0.2, reasons: ["LLM/YOLO介入仍未满足判定"] };
}
```

### 3) 回退实现优先级

1. **遮罩/弹窗**：检测 `.modal/.dialog` 直接点击关闭或 `Esc`
2. **显式返回**：若页面有“返回/Back/上一页”元素，点击
3. **浏览器回退**：`history.back()` + 兜底等待
4. **强制跳转**：记录上一个 `pre.url`，`location.assign(pre.url)`

### 4) 黑名单键与相似度

* 键：`phase( task_id, phase_id ) + pageSig( host + urlPathHash + domHash ) + targetSig( role + label/href/id + bboxRound )`
* **相似匹配**：label 文本 Jaccard ≥ 0.9 或 href 同源同 path；bbox IoU ≥ 0.85 视为命中
* **TTL**：默认 7 天；命中次数 ≥ `max_hits`（如3次）后**永久拉黑**

```ts
function addToBlacklist(phase: PhaseKey, page: PageSig, target: TargetSig, meta: Partial<BlacklistEntry>) { /* storage / DB */ }
function isBlacklisted(phase: PhaseKey, page: PageSig, target: TargetSig): boolean { /* 相似度判定 */ }
```

---

# LLM 验证 Prompt（建议）

* **System**：
  你是网页自动化的验证与修复助手。基于提供的计划目标、成功判定、动作前后DOM、历史与运行信号，判断是否达到目标；若未达到，提出一个替代点击目标（尽量用可匹配的文本/链接/提示词），或建议回退/等待/滚动。输出严格JSON（status/confidence/reasons/recommended\_next\_steps/alt\_target）。

* **User 输入**：
  `plan_step + execution_report（裁剪至关键信息） + pre/post elements（各≤30项） + 最近截图hash（可选）`

---

# 工程化小贴士

* **幂等**：输入/选择动作要带“已在目标值则跳过”的判断，回退后不会造成重复提交。
* **循环保护**：每阶段设置 `max_attempts`（如 3\~5），触发**熔断**输出人工介入原因。
* **页面稳定判定**：`webNavigation` 事件 + `ext.wait_quiet`（DOM 节点变更阈值+网络空闲）。
* **可观测性**：每次失败都记录 `pageSig + targetSig + 验证失败原因`，便于后续统计与规则微调。
* **快速探测**：失败后优先尝试“滚动/等待/重试候选#2”，再走 YOLO+LLM，最后才回退+拉黑。


phase 5:
下面给你一套“可直接落地”的**全链路日志方案**，专门解决：

* **每次把 extracted/reduced content 发送给 LLM 的记录**
* **LLM 返回了什么（含成功/失败/不确定、token/耗时）**
* 还要补齐**动作执行、验证、回退、黑名单**等关键节点

我把它分成：事件模型 → 字段/脱敏 → 插件端(MV3)实现 → 后端收集与存储 → 查看与排错 → 启用/采样/限流。所有代码都可以直接拷贝用。

---

# 1) 事件模型（Event Types）

统一用 **NDJSON**（一行一个 JSON），每条至少包含公共字段 + 事件特有字段。

**公共字段（所有事件都要带）**

* `ts`：毫秒时间戳
* `level`：`debug|info|warn|error`
* `evt`：事件名（如下）
* `exec_id`：一次完整执行的ID（你已有）
* `task_id`、`phase_id`、`step_no`：任务/阶段/步骤
* `run_id`：本次浏览器侧“子执行ID”（建议每步生成一个）
* `page`：`{url,title,host}`（url 需脱敏，详见下文）
* `ctx`：轻量运行上下文（如 `model`, `env: "ext-sw"|"content"|"server"`）

**事件类型（建议至少）**

* `EXTRACTED_RAW`：抓到的原始 ext.extract（仅记录哈希+大小！）
* `DOM_REDUCED`：reducer 输出（记录元素数、裁剪样本、哈希+大小）
* `LLM_REQUEST`：发给 LLM 的 payload（哈希+大小+要点摘要）
* `LLM_RESPONSE`：LLM 返回（状态、耗时、token、置信度、主要结论）
* `ACTION_PERFORMED`：实际执行动作（click/type/select/navigate）
* `VALIDATION_LOCAL`：本地规则校验结果
* `VALIDATION_LLM`：LLM 复核结果（如果触发）
* `BLACKLIST_ADD`：加入阶段黑名单
* `ROLLBACK`：执行回退
* `ERROR`：任何异常（带 `err.name/message/stack`）
* `FLUSH`：日志批量上传/落盘情况（成功/失败/重试）

---

# 2) 字段定义与脱敏策略

**强烈建议**：不在日志里落全量 DOM 或 LLM 原文，改为“**哈希+摘要+大小**”三件套：

* `sha256`：对字符串/Buffer 做 SHA-256（下方给浏览器端实现）
* `bytes`：序列化后字节数（`new Blob([str]).size`）
* `sample`（可选）：**只放安全字段**的小段内容（例如 reducer 的 elements 前 5 项的 `label/role`，不含 bbox/href）
* `el_count`、`bbox_count`：数量统计
* `duration_ms`、`ttfb_ms`：耗时
* `token_in`、`token_out`、`model`、`temperature`：LLM 侧信息（如可获取）

**URL 脱敏（遮蔽敏感查询参数）**

* 只保留 `protocol://host/pathname`，**剔除** `search/hash`；或仅保留白名单参数（如 `?q=`）
* 对可能含个人信息的查询参数（`email/phone/id/token/sid`）做 `***` 替换

**文本脱敏**

* 用正则去除邮箱、手机号、身份证号、cookie、JWT 等：

  * email：`/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i`
  * phone（粗略）：`/\+?\d[\d\s\-]{6,}\d/`
  * jwt：`/[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+/`
* 或者干脆不落文本，只落哈希+大小

---

# 3) 插件端（MV3）可用代码

## 3.1 `lib/hash.js`（浏览器端 SHA-256）

```js
export async function sha256Hex(str) {
  const enc = new TextEncoder();
  const buf = enc.encode(str);
  const digest = await crypto.subtle.digest("SHA-256", buf);
  const arr = Array.from(new Uint8Array(digest));
  return arr.map(b => b.toString(16).padStart(2, "0")).join("");
}
```

## 3.2 `lib/redact.js`（URL 与文本脱敏）

```js
export function redactUrl(input) {
  try {
    const u = new URL(input);
    return `${u.protocol}//${u.host}${u.pathname}`; // 丢弃 search/hash
  } catch { return input; }
}

export function redactText(s = "") {
  return s
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[email]")
    .replace(/\+?\d[\d\s\-]{6,}\d/g, "[phone]")
    .replace(/[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+/g, "[jwt]");
}
```

## 3.3 `lib/logger.js`（MV3 侧统一日志器 + 批量上报）

```js
// lib/logger.js
import { sha256Hex } from "./hash.js";
import { redactUrl, redactText } from "./redact.js";

const CFG = {
  consoleLevel: "info",               // "debug" | "info" | "warn" | "error"
  flushIntervalMs: 3000,
  maxBuffer: 200,                     // 条
  maxBytesPerEvent: 64 * 1024,        // 64KB 保护
  backendUrl: null,                   // 如: "http://127.0.0.1:8787/logs"
  storageKey: "LOG_BUFFER_V1"
};

const LEVELS = ["debug","info","warn","error"];

let buffer = [];
let timer = null;

function shouldLog(level) {
  return LEVELS.indexOf(level) >= LEVELS.indexOf(CFG.consoleLevel);
}

export function setLogConfig(partial) {
  Object.assign(CFG, partial || {});
}

export function logEvent(base = {}) {
  const evt = {
    ts: Date.now(),
    level: base.level || "info",
    env: base.env || "ext-sw", // ext-sw | content | server
    ...base
  };
  if (shouldLog(evt.level)) {
    // 控制台友好打印（不含大块字段）
    const { payload_sample, resp_sample, ...lite } = evt;
    console.log("[LOG]", lite);
  }
  buffer.push(evt);
  if (buffer.length >= CFG.maxBuffer) flushLogs();
  if (!timer) timer = setInterval(flushLogs, CFG.flushIntervalMs);
}

export async function logExtractRaw({ exec_id, task_id, phase_id, step_no, url, payload }) {
  const str = JSON.stringify(payload);
  logEvent({
    evt: "EXTRACTED_RAW",
    exec_id, task_id, phase_id, step_no,
    level: "debug",
    page: { url: redactUrl(url) },
    payload_size: new Blob([str]).size,
    payload_sha256: await sha256Hex(str)
  });
}

export async function logDomReduced({ exec_id, task_id, phase_id, step_no, url, reduced }) {
  // 仅摘取前5个 elements 的 label/role 作为 sample
  const sample = reduced.elements.slice(0, 5).map(e => ({ label: e.label, role: e.role }));
  const s = JSON.stringify(reduced);
  logEvent({
    evt: "DOM_REDUCED",
    level: "info",
    exec_id, task_id, phase_id, step_no,
    page: { url: redactUrl(url), title: redactText(reduced.title) },
    el_count: reduced.elements.length,
    payload_size: new Blob([s]).size,
    payload_sha256: await sha256Hex(s),
    payload_sample: sample
  });
}

export async function logLLMRequest({ exec_id, task_id, phase_id, step_no, model, body }) {
  const str = JSON.stringify(body);
  // 只记录概览，避免落敏感文本
  logEvent({
    evt: "LLM_REQUEST",
    level: "info",
    exec_id, task_id, phase_id, step_no,
    llm: { model },
    payload_size: new Blob([str]).size,
    payload_sha256: await sha256Hex(str)
  });
}

export async function logLLMResponse({ exec_id, task_id, phase_id, step_no, model, status, latency_ms, tokens }) {
  logEvent({
    evt: "LLM_RESPONSE",
    level: status === "ok" ? "info" : "warn",
    exec_id, task_id, phase_id, step_no,
    llm: { model },
    latency_ms,
    token_in: tokens?.in ?? null,
    token_out: tokens?.out ?? null,
    status
  });
}

export function logActionPerformed({ exec_id, task_id, phase_id, step_no, action, target }) {
  logEvent({
    evt: "ACTION_PERFORMED",
    level: "info",
    exec_id, task_id, phase_id, step_no,
    action,
    target: {
      role: target.role, label: target.label,
      href: target.href ? "[href]" : undefined   // 不落原始链接
    }
  });
}

export function logValidationLocal({ exec_id, task_id, phase_id, step_no, verdict }) {
  logEvent({
    evt: "VALIDATION_LOCAL",
    level: verdict.status === "failure" ? "warn" : "info",
    exec_id, task_id, phase_id, step_no,
    verdict
  });
}

export function logValidationLLM({ exec_id, task_id, phase_id, step_no, verdict }) {
  logEvent({
    evt: "VALIDATION_LLM",
    level: verdict.status === "failure" ? "warn" : "info",
    exec_id, task_id, phase_id, step_no,
    verdict_summary: {
      status: verdict.status,
      confidence: verdict.confidence,
      recs: verdict.recommended_next_steps?.slice(0,2) ?? []
    }
  });
}

export function logBlacklistAdd({ exec_id, task_id, phase_id, step_no, target, reason }) {
  logEvent({
    evt: "BLACKLIST_ADD",
    level: "warn",
    exec_id, task_id, phase_id, step_no,
    target: { role: target.role, label: target.label, href: target.href ? "[href]" : undefined },
    reason
  });
}

export function logRollback({ exec_id, task_id, phase_id, step_no, mode }) {
  logEvent({
    evt: "ROLLBACK",
    level: "warn",
    exec_id, task_id, phase_id, step_no,
    mode // "history.back" | "hard-navigate" | "close-modal"
  });
}

export function logError({ exec_id, task_id, phase_id, step_no, err }) {
  logEvent({
    evt: "ERROR",
    level: "error",
    exec_id, task_id, phase_id, step_no,
    error: { name: err?.name, message: String(err?.message || err), stack: String(err?.stack || "") }
  });
}

async function flushLogs() {
  if (!buffer.length) return;
  const batch = buffer.splice(0, buffer.length);
  if (!CFG.backendUrl) {
    // 没有后端就临时存在 session（环形存储）
    chrome.storage.session.get([CFG.storageKey]).then(({ [CFG.storageKey]: cur = [] }) => {
      const merged = [...cur, ...batch].slice(-1000);
      chrome.storage.session.set({ [CFG.storageKey]: merged });
    });
    return;
  }
  try {
    const body = batch.map(e => JSON.stringify(e)).join("\n");
    await fetch(CFG.backendUrl, { method: "POST", headers: { "content-type": "application/x-ndjson" }, body });
    logEvent({ evt: "FLUSH", level: "debug", sent: batch.length });
  } catch (e) {
    console.warn("[LOG] flush failed, buffering:", e);
    // 失败就塞回缓存（截断防爆）
    buffer = [...batch, ...buffer].slice(-CFG.maxBuffer * 2);
  }
}
```

## 3.4 在关键点打点

**ext.extract 完成**

```js
// content 或 SW 里
await logExtractRaw({ exec_id, task_id, phase_id, step_no, url: location.href, payload });
```

**reducer 完成**

```js
await logDomReduced({ exec_id, task_id, phase_id, step_no, url: reduced.url, reduced });
```

**LLM 调用包装**

```js
async function callLLM(model, body) {
  const t0 = performance.now();
  await logLLMRequest({ exec_id, task_id, phase_id, step_no, model, body });
  try {
    const resp = await fetch("http://127.0.0.1:8787/llm", { method: "POST", body: JSON.stringify({ model, body }) });
    const data = await resp.json();
    const latency = Math.round(performance.now() - t0);
    await logLLMResponse({
      exec_id, task_id, phase_id, step_no,
      model, status: resp.ok ? "ok" : "http-error",
      latency_ms: latency,
      tokens: data?.usage ? { in: data.usage.prompt_tokens, out: data.usage.completion_tokens } : null
    });
    return data;
  } catch (err) {
    await logLLMResponse({ exec_id, task_id, phase_id, step_no, model, status: "network-error", latency_ms: Math.round(performance.now() - t0) });
    throw err;
  }
}
```

**动作执行/验证/回退/黑名单**

```js
logActionPerformed({ exec_id, task_id, phase_id, step_no, action, target });
logValidationLocal({ exec_id, task_id, phase_id, step_no, verdict: localVerdict });
logValidationLLM({ exec_id, task_id, phase_id, step_no, verdict: llmVerdict });
logBlacklistAdd({ exec_id, task_id, phase_id, step_no, target, reason: "validation_fail" });
logRollback({ exec_id, task_id, phase_id, step_no, mode: "history.back" });
```

---

# 4) 后端收集与存储（可选但推荐）

**HTTP 接口**（Node/Express 示例，使用 pino 按行落盘）：

```js
// server/logs.js
import express from "express";
import pino from "pino";
const router = express.Router();
const logger = pino({ level: "info" }, pino.destination("./logs/runner.ndjson"));

router.post("/logs", express.text({ type: "application/x-ndjson", limit: "5mb" }), (req, res) => {
  const lines = (req.body || "").split(/\r?\n/).filter(Boolean);
  for (const line of lines) {
    try {
      const obj = JSON.parse(line);
      logger.info(obj);
    } catch (e) {
      logger.warn({ evt: "LOG_PARSE_FAIL", line });
    }
  }
  res.status(204).end();
});

export default router;
```

**数据库**（PostgreSQL，可后续接入）：

* `logs ( id bigserial pk, ts timestamptz, exec_id text, evt text, level text, payload jsonb, idx jsonb )`
* `idx` 存放可查询索引字段（`task_id/phase_id/step_no` 等），便于检索

**日志轮转**：用 `logrotate` 或 `pino-transport` 做按天切割 + 压缩。

---

# 5) 查看与排错

* **开发期**：直接在 MV3 Service Worker 的 Console 看 `[LOG]`，或从 `chrome.storage.session` 里把 `LOG_BUFFER_V1` 导出（写个 popup 按钮 `Download NDJSON`）。
* **联调期**：后端 `logs/runner.ndjson` 直接 `tail -f`。
* **定位一次执行**：按 `exec_id` 过滤；按 `evt` 顺序应该能看到：`EXTRACTED_RAW → DOM_REDUCED → LLM_REQUEST → LLM_RESPONSE → ACTION_PERFORMED → VALIDATION_* → (BLACKLIST/ROLLBACK)`。

---

# 6) 开关、采样与限流

* `setLogConfig({ consoleLevel: "debug", backendUrl: "http://127.0.0.1:8787/logs" })`
* 生产环境建议：

  * `consoleLevel: "info"`
  * LLM 请求/响应**采样**（比如每10次采1次，或只在 `uncertain/failure` 时全量记录哈希+耗时）
  * `maxBytesPerEvent` 保护避免巨大对象
  * 出错事件永远全打（至少哈希+大小）

---

# 7) 最小落地 Checklist

1. 在 SW 里引入并初始化 `logger`（设置 `backendUrl` 或先用 `storage.session`）。
2. 在 `ext.extract` 回调、reducer 完成后、LLM 请求前/后、动作执行后、本地与 LLM 验证、回退、黑名单，每处插**对应 log**。
3. 确认控制台能看到：`EXTRACTED_RAW / DOM_REDUCED / LLM_REQUEST / LLM_RESPONSE`。
4. 失败场景：确保能看到 `VALIDATION_LOCAL`→`VALIDATION_LLM`→（可能）`BLACKLIST_ADD`→`ROLLBACK`。
5. 若接入后端，确认 `logs/runner.ndjson` 正常落行且可 `grep exec_id`。

---
