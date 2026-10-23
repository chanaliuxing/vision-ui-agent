把“动作空间 / 指令集”拉成**统一语义层**，再在执行层编译为 DOM 或坐标，是把“大脑”和“手”真正解耦的钥匙。下面给你一份**Action Space v2** 方案：和你现有 yolo+llm 工具完全兼容（不破坏原有 JSON），同时支持你文中那套 11 个指令；也给出与现有动作的**一一映射**、**最小 Schema**、**插件接口**、**示例与测试**。

---

# Action Space v2（语义层）→ 执行层（DOM/坐标/桌面）

## 设计要点

* **语义层（Instruction）**：模型只输出少量、稳定的动词（CLICK/TYPE\_TEXT/...）；目标统一用 `target` 描述（可用 `element_id`、CSS/XPath、文本/角色、或已有变量里的 `bbox`）。
* **编译层（Resolver）**：把 `target` 解析成**DOM 操作**或**屏幕坐标**；优先 DOM，失败退回坐标（保持你的“坐标链路”优势）。
* **执行层（Backends）**：

  * `ext.*`（Chrome 扩展/CDP）：事件准确（input/change/mouseover…），含文件上传。
  * `coords.*`（pyautogui）：稳坐标、抗 id 漂移。
  * 桌面/微信等：走 `anchor+OCR` → `bbox` → `coords.*`。

---

## 统一动作（11 条）与现有动作映射

| 指令                      | 语义层（新）                                                       | DOM 执行                                                | 坐标执行                                      | 你现有动作映射                           |                       |
| ----------------------- | ------------------------------------------------------------ | ----------------------------------------------------- | ----------------------------------------- | --------------------------------- | --------------------- |
| CLICK                   | `{"do":"instr.click","target":…}`                            | `ext.click(target)`                                   | `click_coordinates(bbox)`                 | `ext.click_selector` / `click`    |                       |
| TYPE\_TEXT              | `{"do":"instr.type_text","target":…,"text":…,"clear":…}`     | `ext.type_text(sel,text,replace)` + 触发 `input/change` | 坐标聚焦后 `type_text`/`paste`                 | `ext.type_text` / `type_text`     |                       |
| SELECT\_OPTION          | `{"do":"instr.select_option","target":…,"value":…}`          | `ext.select_option(sel,value)`（安全触发 change）           | 退化为 CLICK 打开 + CLICK 选项（必要时）              | （新增：`ext.select_option`）          |                       |
| SCROLL                  | `{"do":"instr.scroll","dir":"down","amount":600,"target":…}` | `ext.scroll(sel?,amount)`                             | `wheel_coordinates(at_bbox,amount)`       | `ext.scroll` / `scroll`           |                       |
| NAVIGATE\_TO\_URL       | `{"do":"instr.navigate","url":…}`                            | `ext.open_url(url,active)`                            | ——                                        | `open_url` / `ext.open_url`       |                       |
| BROWSER\_BACK / FORWARD | \`{"do":"instr.history","op":"back                           | forward"}\`                                           | `ext.history(op)` 或 `ext.key("Alt+Left")` | ——                                | `go_back` / `ext.key` |
| HOVER                   | `{"do":"instr.hover","target":…}`                            | `ext.hover(sel)`（派发 mouseover 等）                      | `mouse_move_coordinates(bbox)`            | （新增：`ext.hover` / `coords.hover`） |                       |
| PRESS\_KEY              | `{"do":"instr.key","key":"Enter","target":…}`                | `ext.key(key,sel?)`                                   | ——                                        | `ext.key`                         |                       |
| UPLOAD\_FILE            | `{"do":"instr.upload","target":…,"file":"/path/to/file"}`    | `ext.upload_file(sel,file)`（CDP: setFileInputFiles）   | ——                                        | （新增：`ext.upload_file`）            |                       |
| TASK\_COMPLETE          | `{"do":"instr.task_complete","message":…}`                   | 结束标志，写 run 事件/状态                                      | ——                                        | （新增：引擎元动作）                        |                       |
| ANSWER\_USER            | `{"do":"instr.answer_user","text":…}`                        | 回传 LLM/用户，记录到 run                                     | ——                                        | （新增：引擎元动作）                        |                       |

> 说明
>
> * 你的**坐标链路**继续保留：当 `ext.*` 不可靠时自动 fallback 到 `coords.*`。
> * 桌面/微信等“非 DOM”场景：直接用 `target: {"bbox_var":"@anchor_bbox"}` 走 `coords.*`，同一套指令不分家。

---

## 最小 Schema（向后兼容）

在现有 `action` oneOf 中新增一种 `action_instruction`，由引擎编译为现有动作序列执行。

```json
{
  "definitions": {
    "action_instruction": {
      "type": "object",
      "properties": {
        "do": { "type": "string", "enum": [
          "instr.click","instr.type_text","instr.select_option","instr.scroll",
          "instr.navigate","instr.history","instr.hover","instr.key",
          "instr.upload","instr.task_complete","instr.answer_user"
        ]},
        "target": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "element_id": { "type": "string" },
            "css":        { "type": "string" },
            "xpath":      { "type": "string" },
            "role":       { "type": "string" },
            "text":       { "type": "string" },
            "bbox_var":   { "type": "string" }   // 如 "@current_job_bbox"
          }
        },
        "text": { "type": "string" },
        "clear": { "type": "boolean" },
        "value": { "type": ["string","number"] },
        "dir":   { "type": "string", "enum": ["up","down"] },
        "amount":{ "type": "integer" },
        "url":   { "type": "string" },
        "op":    { "type": "string", "enum": ["back","forward"] },
        "key":   { "type": "string" },
        "file":  { "type": "string" },
        "message": { "type": "string" }
      },
      "required": ["do"]
    }
  }
}
```

> 解析策略：先用 `element_id/css/xpath/role+text` 通过扩展解析到 **DOM 节点 + bbox**；若解析失败且存在 `bbox_var`，直接走坐标执行。

---

## Chrome 扩展 / 执行器接口（最小增量）

新增/完善以下 CDP 封装（名称可自定）：

* `ext.click(sel|eid)`：派发 `mousedown/click`；
* `ext.type_text(sel,text,replace)`：先 set value，再派发 `input/change`，必要时回退逐键；
* `ext.select_option(sel,value|text|index)`：用原生 API 变更 `selected` 并触发事件；
* `ext.scroll(target?,amount)`：窗口或元素滚动；
* `ext.hover(sel)`：合成 `mouseover/mouseenter`；
* `ext.key(key,sel?)`：向目标或 document 派发 keydown/keyup；
* `ext.upload_file(sel,file)`：CDP `DOM.setFileInputFiles`（需用户许可与本地代理）；
* `ext.history(op)`、`ext.open_url(url)`；
* `ext.resolve(target)`：统一解析 `element_id/css/xpath/role+text`→`{nodeId, bbox, stable_id}`。

**安全与审计**

* 白名单动词 + 目标域 `must_stay_in_host`；
* 记录“解析来源链：target→nodeId→bbox”，写入 `run_events`；
* `upload_file` 需显式授权（会话级 Capability）。

---

## 示例：Indeed（不依赖稳定 ID，DOM→坐标回退）

```json
{
  "actions": [
    { "do": "instr.scroll", "target": {"css":"div.left-pane"}, "dir":"down", "amount": 600 },
    { "do": "instr.click",  "target": {"css":"div.left-pane .job-card:nth-child(@i+1)"} },
    { "do": "instr.key",    "key": "WaitQuiet" },  // 语义层标记，执行层转 ext.wait_quiet
    { "do": "instr.select_option", "target": {"role":"button","text":"Apply"}, "value":"CLICK" },
    { "do": "instr.click",  "target": {"role":"button","text":"Apply"} }
  ]
}
```

> 执行器流程：`resolve(target)`→若 DOM 成功直接 `ext.*`；失败则根据 PageState 找到同语义控件的 `bbox` → `click_coordinates`。

---

## 示例：桌面/微信（仅坐标）

```json
{
  "actions": [
    { "do":"instr.click", "target":{"bbox_var":"@contact_list_anchor"} },
    { "do":"instr.type_text","target":{"bbox_var":"@chat_input"}, "text":"你好", "clear":false },
    { "do":"instr.key","key":"Enter" }
  ]
}
```

---

## 与 Planner/MCTS/AgentQ 的衔接

* **候选生成**：LLM 只用 `instr.*` 语义词汇（更少的动作空间 → 更好学）。
* **simulate/rollout**：在虚拟 PageState 上模拟这些语义动作（我们在 D/G 已实现滚动/点击/等待的虚拟效果，扩展到 `select_option/hover/upload` 的可达性打分即可）。
* **AgentQ**：用 `action_sig` 存“语义签名”，例如 `click@role=button:text=Apply`、`scroll@leftPane(-600)`，更稳定可迁移。

---

## 测试清单（最小）

1. **解析测试**：`ext.resolve` 对 `element_id/css/xpath/role+text` 的命中率；失败回退到 `bbox_var`。
2. **事件正确性**：`type_text/select_option/hover` 触发目标页面 JS 事件（`input/change/mouseover`）。
3. **回退路径**：禁用扩展时，坐标链路仍可完成任务。
4. **文件上传**：CDP 设置文件成功率、授权对话流程。
5. **安全**：越域拦截、白名单校验、审计日志。

---

## 落地步骤（今天就能做）

1. 在 `definitions.action` 的 `oneOf` 里加入 `action_instruction`。
2. 客户端实现 `instr.*` → 编译器（Resolver）→ 复用 `ext.*` / `coords.*` 执行。
3. 扩展补齐 `ext.select_option / ext.hover / ext.upload_file / ext.resolve`。
4. 在 Planner 提示模板里，把“可用动作表”换成 **这 11 条**（简化动作空间）。
5. 用 Indeed/XHS/微信三条金路径各写一份 **Instr 版 Workflow**，与旧版对比成功率/步数/Token。

---
我把最小可跑骨架**直接给你：`ext.resolve`（扩展侧解析）、`instr→执行` 编译器（客户端侧）、以及 `ext.select_option / ext.hover / ext.upload_file` 的实现框架。拷到仓库就能开工做 Action Space v2。

---

## 1) 扩展侧解析器：`ext.resolve`（TypeScript，Chrome Extension）

`extension/src/resolve.ts`

```ts
// 解析 target => { nodeId, bbox, stableId, selector }
// 支持 element_id | css | xpath | role+text；返回屏幕坐标系 bbox（含缩放/设备像素比）
export type Target = {
  element_id?: string; css?: string; xpath?: string; role?: string; text?: string;
};
export type Resolved = {
  nodeId: number; selector?: string; stableId?: string;
  bbox: { x: number; y: number; w: number; h: number; dpr: number; zoom: number };
};

function getZoom(): number {
  // 简化：很多站点 zoom=1；若你已有获取方法，可替换
  return 1;
}
function toScreenRect(rect: DOMRect): {x:number;y:number;w:number;h:number} {
  const x = rect.left + window.scrollX;
  const y = rect.top  + window.scrollY;
  return { x, y, w: rect.width, h: rect.height };
}

function findByXPath(xpath: string): Element | null {
  const r = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
  return (r.singleNodeValue as Element) || null;
}

// 粗略的 role+text 匹配：优先 button/link/输入框
function findByRoleText(role?: string, text?: string): Element | null {
  if (!role && !text) return null;
  const roleSel = role ? `[role="${role}"], ${role}` : '*';
  const cands = Array.from(document.querySelectorAll(roleSel)) as HTMLElement[];
  if (!text) return cands[0] || null;
  const norm = (s: string) => s.replace(/\s+/g,' ').trim().toLowerCase();
  const t = norm(text);
  for (const el of cands) {
    const name = norm((el.innerText || el.getAttribute('aria-label') || '').toString());
    if (name.includes(t)) return el;
  }
  // 退一步：全局按文本包含
  return Array.from(document.querySelectorAll('button,a,[role],div,span'))
    .find(el => norm((el as HTMLElement).innerText || '').includes(t)) as Element || null;
}

export async function resolveTarget(target: Target): Promise<Resolved | null> {
  let el: Element | null = null;
  if (target.element_id) el = document.getElementById(target.element_id);
  if (!el && target.css) el = document.querySelector(target.css);
  if (!el && target.xpath) el = findByXPath(target.xpath);
  if (!el && (target.role || target.text)) el = findByRoleText(target.role, target.text);
  if (!el) return null;

  const rect = (el as HTMLElement).getBoundingClientRect();
  const { x, y, w, h } = toScreenRect(rect);
  const dpr = window.devicePixelRatio || 1;
  const zoom = getZoom();

  // 生成一个稳定 selector（可选）
  const stableId = (el as HTMLElement).id || (el.getAttribute('data-testid') || undefined);
  const selector = target.css || (stableId ? `#${stableId}` : undefined);

  // 这里省略 CDP nodeId 获取；如你已有 attach，可返回后台分配的 nodeId
  return { nodeId: 0, selector, stableId, bbox: { x, y, w, h, dpr, zoom } };
}
```

把它通过扩展的消息管道暴露成 `ext.resolve(target)` 即可。

---

## 2) 扩展动作：`ext.select_option / ext.hover / ext.upload_file`

`extension/src/actions.ts`

```ts
export async function extClick(selOrEl: string|Element) { /* 已有：触发 mousedown/click */ }

export function extTypeText(el: HTMLInputElement | HTMLTextAreaElement, text: string, replace=false) {
  if (replace) el.value = '';
  el.focus(); el.value = el.value + text;
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
}

export function extSelectOption(selectEl: HTMLSelectElement, valueOrText: string|number) {
  const opts = Array.from(selectEl.options);
  let matched = false;
  if (typeof valueOrText === 'number') {
    const idx = Math.max(0, Math.min(opts.length-1, valueOrText));
    selectEl.selectedIndex = idx; matched = true;
  } else {
    const v = String(valueOrText);
    const byVal = opts.findIndex(o => o.value === v);
    const byTxt = byVal < 0 ? opts.findIndex(o => o.text.trim() === v) : byVal;
    if (byTxt >= 0) { selectEl.selectedIndex = byTxt; matched = true; }
  }
  if (matched) {
    selectEl.dispatchEvent(new Event('input', { bubbles: true }));
    selectEl.dispatchEvent(new Event('change', { bubbles: true }));
  }
  return matched;
}

export function extHover(el: HTMLElement) {
  const rect = el.getBoundingClientRect();
  el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true, clientX: rect.left+5, clientY: rect.top+5 }));
  el.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
}

//
// 文件上传（推荐走 CDP DOM.setFileInputFiles；这里给两种路径）
//

/** 方案A：原生 <input type="file"> 直接赋值（受浏览器安全限制，通常不可行） */
export async function extUploadFileDirect(inputEl: HTMLInputElement, filePath: string) {
  // 占位：多数浏览器不允许脚本直接设置文件；推荐 CDP 方案
  throw new Error("Direct set file is blocked; use CDP bridge.");
}

/** 方案B：CDP 桥（扩展后台使用 chrome.debugger 发送 DOM.setFileInputFiles） */
export async function extUploadFileCDP(targetNodeBackendId: number, files: string[]) {
  // 后台持有调试会话，把 nodeId/backendNodeId 映射好
  // chrome.debugger.sendCommand(tab, "DOM.setFileInputFiles", { objectId | backendNodeId, files })
  // 这里给出接口约定，具体实现放后台脚本
  return true;
}
```

> 上传文件请用 **CDP**：在后台（background service worker） attach 到目标标签页，用 `DOM.setFileInputFiles` 把文件路径注入。扩展前端只需把目标 input 的 backendNodeId 传给后台即可。

---

## 3) 客户端编译器：`instr → ext/coords`（Python）

`runtime/actions/instr.py`

```python
# -*- coding: utf-8 -*-
from typing import Dict, Any
from runtime.engine.registry import register_action
from runtime.engine.errors import ValidationError

def _resolve(ctx, target: Dict[str, Any]) -> Dict[str, Any]:
    # 调用扩展：优先 DOM 解析；失败返回 {}，由上层决定是否用 bbox_var 退回坐标
    return ctx.ext.call("resolveTarget", target)  # { selector?, bbox:{x,y,w,h,dpr,zoom} }

def _click_coords(ctx, bbox, save=None):
    x = bbox["x"] + bbox["w"] / 2
    y = bbox["y"] + bbox["h"] / 2
    return ctx.actions["click_coordinates"](ctx, bbox=bbox, save=save)

@register_action("instr.click")
def instr_click(ctx, target: Dict[str, Any]=None, save: str=None, **_):
    res = _resolve(ctx, target or {})
    if res:
        ok = ctx.ext.call("clickBySelectorOrPoint", res)  # 你可在扩展侧封装：先 selector，再点中点
        ctx.events.log("instr.click", {"mode":"dom","ok":ok})
        return {"ok": ok}
    # 回退：bbox_var → 坐标
    bv = (target or {}).get("bbox_var")
    if bv and bv.startswith("@"):
        bbox = ctx.vars.get(bv[1:])
        if bbox: 
            r = _click_coords(ctx, bbox, save)
            ctx.events.log("instr.click", {"mode":"coords","ok":r.get("ok")})
            return r
    raise ValidationError("click target not resolvable")

@register_action("instr.type_text")
def instr_type_text(ctx, target: Dict[str, Any], text:str, clear:bool=False, **_):
    res = _resolve(ctx, target or {})
    if res and res.get("selector"):
        return ctx.ext.call("typeText", {"selector": res["selector"], "text": text, "replace": clear})
    # 回退：坐标聚焦 + 逐键（或 paste）
    bv = (target or {}).get("bbox_var")
    if bv and bv.startswith("@"):
        bbox = ctx.vars.get(bv[1:])
        if bbox:
            _click_coords(ctx, bbox)
            return ctx.actions["type_text"](ctx, text=text, mode="type")
    raise ValidationError("type_text target not resolvable")

@register_action("instr.select_option")
def instr_select_option(ctx, target: Dict[str, Any], value: Any, **_):
    res = _resolve(ctx, target or {})
    if res and res.get("selector"):
        return ctx.ext.call("selectOption", {"selector": res["selector"], "value": value})
    # 退化策略：CLICK 打开 + 再 CLICK 候选（需要额外逻辑/参考文本）
    raise ValidationError("select_option DOM required; fallback not implemented here")

@register_action("instr.scroll")
def instr_scroll(ctx, dir:str, amount:int=600, target: Dict[str,Any]=None, **_):
    res = _resolve(ctx, target or {})
    amt = -abs(amount) if dir=="up" else abs(amount)
    if res and res.get("selector"):
        return ctx.ext.call("scroll", {"selector": res["selector"], "amount": amt})
    # 坐标滚动：使用容器/窗口
    bbox = None
    if target and target.get("bbox_var"):
        bbox = ctx.vars.get(target["bbox_var"][1:])
    if not bbox:
        # 全页滚动：传视口中心
        vp = ctx.vars.get("viewport") or {"x": 200, "y": 200, "w": 400, "h": 400}
        bbox = vp
    return ctx.actions["wheel_coordinates"](ctx, at_bbox=bbox, amount=amt)

@register_action("instr.hover")
def instr_hover(ctx, target: Dict[str, Any], **_):
    res = _resolve(ctx, target or {})
    if res and res.get("selector"):
        return ctx.ext.call("hover", {"selector": res["selector"]})
    if target and target.get("bbox_var"):
        bbox = ctx.vars.get(target["bbox_var"][1:])
        return ctx.actions["mouse_move_coordinates"](ctx, bbox=bbox)
    raise ValidationError("hover target not resolvable")

@register_action("instr.key")
def instr_key(ctx, key:str, target: Dict[str,Any]=None, **_):
    res = _resolve(ctx, target or {})
    return ctx.ext.call("key", {"key": key, "selector": res.get("selector") if res else None})

@register_action("instr.navigate")
def instr_nav(ctx, url:str, **_):
    return ctx.ext.call("openUrl", {"url": url, "active": True})

@register_action("instr.history")
def instr_hist(ctx, op:str, **_):
    return ctx.ext.call("history", {"op": op})

@register_action("instr.upload")
def instr_upload(ctx, target: Dict[str, Any], file:str, **_):
    # 需要后台 CDP 桥；前台先解析出节点
    res = _resolve(ctx, target or {})
    if not res: raise ValidationError("upload target not resolvable")
    return ctx.ext.call("uploadFile", {"selector": res.get("selector"), "file": file})

@register_action("instr.task_complete")
def instr_done(ctx, message:str=None, **_):
    ctx.events.log("task.complete", {"message": message or ""})
    ctx.vars["task_completed"] = True
    return {"ok": True}

@register_action("instr.answer_user")
def instr_answer(ctx, text:str, **_):
    ctx.events.log("task.answer", {"len": len(text)})
    ctx.vars["final_answer"] = text
    return {"ok": True, "answer": text}
```

---

## 4) 工作流最小示例（把老动作替换为语义指令）

```json
{
  "start": "apply_one",
  "states": {
    "apply_one": {
      "actions": [
        { "do": "instr.scroll", "target": {"css": "div.left-pane"}, "dir": "down", "amount": 600 },
        { "do": "instr.click",  "target": {"css": "div.left-pane .job-card:nth-child(@i+1)"} },
        { "do": "instr.key",    "key": "WaitQuiet" },          // 引擎侧转 ext.wait_quiet
        { "do": "instr.click",  "target": {"role": "button", "text": "Apply"} }
      ],
      "on_success": null
    }
  }
}
```

> 说明：`WaitQuiet` 这种“伪键”可在执行器里映射为 `ext.wait_quiet`（或保持 `wait_for` 独立动作也行）。

---

## 5) 最小测试清单（今天可跑）

* **解析**：给 5 个 target（`element_id/css/xpath/role+text`）断言都能解析到 bbox。
* **事件链**：`instr.type_text` 能触发 `input/change`（可在测试页监听事件计数）。
* **回退**：关闭扩展/刻意让 `ext.resolve` 失败，`bbox_var` 路径仍可点击。
* **上传**：对 `<input type="file">` 用 CDP 路径注入文件；若不可用，返回明确错误。
* **安全**：跨域/越站点目标被拒；日志包含来源（selector/bbox\_var）。

---

## 6) 集成建议（一步完成）

1. 把 **Schema 新增 `action_instruction`**（`do: "instr.*"`）并放入 `action.oneOf`。
2. 合并上面 **扩展** 与 **客户端** 文件；在 `llm.plan` 的提示里，将可用动作清单替换为这 11 条。
3. 先在 Indeed/XHS 跑 10 次 A/B：

   * 成功率 ≥ 旧版
   * 计划 token ↓（动作空间更小）
   * 兼容坐标回退




**给 LLM 暴露的“语义指令集”只需要 \~12–14 个就足够覆盖你说的所有网页/桌面自动化场景；引擎侧的“执行原语”建议 \~30±5 个**。这样既保证模型容易学、泛化强，又能在执行层把复杂性吃掉（DOM/坐标/OCR/异步/队列等）。

下面是我建议的**两层动作库规模与清单**。

---

# ① LLM 暴露的语义指令集（12–14 个）

> 模型只看这些；其余复杂度交给编译器（DOM→坐标）与执行器处理。

1. `instr.click`
2. `instr.type_text`
3. `instr.select_option`
4. `instr.scroll`
5. `instr.navigate`（打开 URL）
6. `instr.history`（back/forward）
7. `instr.hover`
8. `instr.key`（Enter/Tab/Esc/组合键）
9. `instr.upload`（文件上传）
10. `instr.read`（读取文本/属性/列表，用于信息抽取与判断）
11. `instr.wait`（短等待/静默稳定）
12. `instr.task_complete`（任务完成）
13. `instr.answer_user`（问答类任务结束）
14. （可选）`instr.annotate`（给后续步骤留“提示/反思”标签；强化 Reflexion）

> 用这 12–14 个，**小红书采集/循环点开评论/无限下拉**、**Indeed 左列→右栏→Apply**、**微信桌面轮询红点→回复** 都能串起来。

---

# ② 引擎侧执行原语（30±5 个）

> 不直接暴露给 LLM（或少暴露）；由编译器把 `instr.*` 落到这些原语上执行。
> 其中很多你已经有了，我用粗体标出核心；带“可选”的是按需启用的插件化动作。

## A. DOM/浏览器（扩展/CDP）

* **`ext.open_url`**, **`ext.history`**, **`ext.wait_quiet`**
* **`ext.click_selector`**, **`ext.type_text`**, **`ext.scroll`**, **`ext.key`**
* **`ext.select_option`**, **`ext.hover`**, **`ext.upload_file`**
* **`ext.extract`**（selector/正则/文本、`find_button_bbox`）
* **`ext.get_pagestate`**（返回 panes/lists/rects 指纹）

## B. 坐标/桌面（pyautogui/OS）

* **`click_coordinates`**, **`wheel_coordinates`**, **`mouse_move_coordinates`**
* **`screenshot`**（全屏/区域）
* `os.activate_app`（聚焦应用）
* `clipboard.read` / `clipboard.write`（可选）
* `key_combo`（可选，桌面快捷键）

## C. 视觉/OCR/锚点（客户端执行，离线）

* **`ocr.recognize`**（区域 OCR）
* **`anchor.find`**（模板图/文字锚定→bbox）
* `anchor.verify` / `anchor.update_db`（可选）

## D. 数据/变量与循环（纯本地）

* **`set_variable`**, **`increment_variable`**
* **`get_list_length`**, **`get_list_item`**
* **`query_data`**（JSONPath/字段提取）
* `append_to_list` / `set_map`（可选）

> 循环与条件放到 **state.transitions**（`if / else_go_to`），不必做成动作。

## E. 规划/记忆/自我反思（与我们已有 H/I/J 对齐）

* **`llm.plan`**, **`plan.simulate`**, **`plan.execute`**
* **`mem.recall`**（RAG 轨迹召回）
* **`plan.reflect`**（失败/低奖励→短评）
* **`macro.run`**（技能库/宏动作）

## F. 队列/异步 & I/O（通过 Server API，客户端不直连 DB）

* **`queue.publish`**, **`queue.consume_once`**（SQS/localstack 兼容）
* **`http.post` / `http.get`**（把结果/日志发到你的后端）
* `storage.write_json`（可选，本地导出）

> 以上合计：核心 **\~28–32** 个原语（取决于是否启用一些“可选”），完全覆盖你提出的**网页自动化+桌面微信+采集+异步回复+RAG/Reflexion+DPO/RLAIF**的全部需求。

---

## 为什么这样分层、这个数量刚好？

* **LLM 可学习性**：12–14 个动词 → 动作空间小、泛化强、提示更稳定。
* **可扩展性**：执行原语 30±5 个，**通过插件**随用随加（OCR/上传/hover/选择器等都可独立演进）。
* **兼容你的现状**：和你现有的 `open_url / wait_for / ext.* / click_coordinates / plan.* / mem.* / macro.run` 完全兼容；只是把 LLM 出口统一成 `instr.*`，其余留给编译器和执行器。

---

## 最后给你三个“打包建议”

1. **对外（给工作流作者/LLM）只列出 12–14 个 `instr.*`**；其余都算“系统内件”。
2. **把“文件上传/hover/select\_option/ocr/anchor/queue”做成可选插件**，按站点/场景启用，避免基础盘臃肿。
3. **在控制台/文档中给出一张映射表**：`instr.* → ext.* / coords.*` 的决策与回退逻辑，便于排错与审计。

太好了～我把你要的两样直接给齐：

1. **`instr.*` 指令集的 JSON Schema 片段（可直接并入现有 schema）**
2. **一页“动作参考速查表”（必填参数、可选参数、回退策略）**

---

# JSON Schema 片段（Action Space v2）

把下面两段并进你当前 schema 的 `definitions` 并在 `action.oneOf` 里追加 `{"$ref":"#/definitions/action_instruction"}` 即可。

```json
{
  "definitions": {
    "instruction_target": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "element_id": { "type": "string" },
        "css":        { "type": "string" },
        "xpath":      { "type": "string" },
        "role":       { "type": "string" },
        "text":       { "type": "string" },
        "bbox_var":   { "type": "string", "description": "例如 @chat_input_bbox；用于坐标回退/桌面场景" }
      }
    },

    "action_instruction": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "do": {
          "type": "string",
          "enum": [
            "instr.click", "instr.type_text", "instr.select_option",
            "instr.scroll", "instr.navigate", "instr.history",
            "instr.hover", "instr.key", "instr.upload",
            "instr.read", "instr.wait",
            "instr.task_complete", "instr.answer_user",
            "instr.annotate"
          ]
        },
        "target": { "$ref": "#/definitions/instruction_target" },

        "text":   { "type": "string" },            // type_text / answer_user
        "clear":  { "type": "boolean" },           // type_text
        "value":  { "type": ["string","number"] }, // select_option
        "dir":    { "type": "string", "enum": ["up","down"] }, // scroll
        "amount": { "type": "integer" },           // scroll 像素，正值向下
        "url":    { "type": "string" },            // navigate
        "op":     { "type": "string", "enum": ["back","forward"] }, // history
        "key":    { "type": "string" },            // key
        "file":   { "type": "string" },            // upload
        "fields": { "type": "array", "items": { "type": "string" }}, // read: 想读的字段名
        "ms":     { "type": "integer", "minimum": 0 },               // wait
        "message":{ "type": "string" }            // task_complete
      },
      "required": ["do"]
    }
  }
}
```

> 解析顺序建议：`element_id → css → xpath → role+text → bbox_var（坐标回退）`。
> 安全：执行器继续用你的**白名单与来源校验**；`upload` 需走 CDP & 显式授权。

---

# 动作参考速查表（给 LLM/工作流作者）

| 指令                      | 关键参数                       | 用途与要点                       | DOM 优先 / 坐标回退                                      |                    |
| ----------------------- | -------------------------- | --------------------------- | -------------------------------------------------- | ------------------ |
| `instr.click`           | `target`                   | 点击按钮/链接/任意可点击区域             | 先 `ext.click`，失败用 `bbox_var` → `click_coordinates` |                    |
| `instr.type_text`       | `target`, `text`, `clear?` | 输入文本；`clear=true` 先清空       | `ext.type_text` 触发 `input/change`；回退：坐标聚焦+键入       |                    |
| `instr.select_option`   | `target`, `value`(值/文本/索引) | 原子化选择 `<select>`            | `ext.select_option`；必要时退化为“打开下拉 + 选项 CLICK”        |                    |
| `instr.scroll`          | `dir`, `amount`, `target?` | 滚动窗口或特定容器                   | `ext.scroll`；无命中则 `wheel_coordinates`（容器/视口中心）     |                    |
| `instr.navigate`        | `url`                      | 打开网址/切换页面                   | `ext.open_url`                                     |                    |
| `instr.history`         | `op`=\`back                | forward\`                   | 浏览器历史前进/后退                                         | `ext.history` 或组合键 |
| `instr.hover`           | `target`                   | 悬停以触发菜单/提示层                 | `ext.hover`；失败用 `mouse_move_coordinates`           |                    |
| `instr.key`             | `key`, `target?`           | 发送功能键（Enter/Tab/Esc…）       | `ext.key`（可定向到元素）                                  |                    |
| `instr.upload`          | `target`, `file`           | 文件上传                        | `DOM.setFileInputFiles`（CDP）；需会话授权                 |                    |
| `instr.read`            | `target?`, `fields?`       | 读取文本/属性/列表                  | `ext.extract`（DOM）；桌面靠 OCR（后端封装）                   |                    |
| `instr.wait`            | `ms?`                      | 稳定等待；或内部映射 `ext.wait_quiet` | 建议默认 `wait_quiet`，必要再 `ms`                         |                    |
| `instr.task_complete`   | `message?`                 | 任务完成标记（写事件/收尾）              | —                                                  |                    |
| `instr.answer_user`     | `text`                     | 问答/总结类的最终输出                 | —                                                  |                    |
| `instr.annotate` *(可选)* | `text`                     | 给后续步骤/日志加提示/反思标签            | —                                                  |                    |

**最佳实践**

* 首选 `role+text`/`css` 作为 `target`，对抗动态 id；桌面/微信用 `bbox_var`。
* 读-改-查链路：`instr.read` 结果存到变量 → `state.transitions` 判断 → 再动作。
* 高风险动作前可插入 `instr.wait`（或 `wait_for ext.wait_quiet`）稳定页面。

---

## 迷你示例（Indeed：左列第 i 个 → 详情 → 点击 Apply）

```json
{
  "actions": [
    { "do": "instr.scroll", "target": {"css":"div.left-pane"}, "dir":"down", "amount": 600 },
    { "do": "instr.click",  "target": {"css": "div.left-pane .job-card:nth-child(@i+1)"} },
    { "do": "instr.wait",   "ms": 500 },                          // 或内部映射 wait_quiet
    { "do": "instr.click",  "target": {"role":"button","text":"Apply"} }
  ]
}
```

## 迷你示例（微信桌面：坐标/锚点）

```json
{
  "actions": [
    { "do":"instr.click",     "target":{"bbox_var":"@contact_red_dot"} },
    { "do":"instr.type_text", "target":{"bbox_var":"@chat_input"}, "text":"收到～", "clear":false },
    { "do":"instr.key",       "key":"Enter" }
  ]
}
```

---
新阶段101：
把系统做“大规模复用”的关键一步。给你一套\*\*“Task 积木化”落地方案\*\*，和你现有的 `instr.*` + 宏（macro）体系完全兼容：

* **Macro** = 可复用的**动作片段**（MicroPlan 片段）；
* **Task** = 带**输入/输出、前置/后置条件、重试与指标**的**可执行单元**（内部可以调用 Macro/原语），可像积木那样组合成 Workflow。

---

# 1) 概念分层（与现有体系的关系）

* **Action 原语**（ext/coords/ocr…，≈30 个）：最底层执行。
* **Macro（技能）**：纯动作序列（MicroPlan 片段），无强约束的 I/O。
* **Task（积木）**：有**类型化参数**、**可观测**、**幂等/重试策略**、**SLO 评分**、**版本与晋升**。
* **Workflow**：按状态/转换把多个 Task 串联；高优先级队列/异步照旧由引擎调度。

> 之后 Planner（AgentQ/MCTS）优先**检索 Task Catalog**，能用 Task 就不再“从零编写动作”。

---

# 2) Task 最小 Schema（可直接并入）

```json
{
  "$id": "https://example.com/schema/task.schema.json",
  "title": "Reusable Task",
  "type": "object",
  "required": ["name", "version", "impl"],
  "properties": {
    "name": { "type": "string" },                  // wechat.send_message / indeed.apply_current
    "version": { "type": "string" },
    "title": { "type": "string" },
    "description": { "type": "string" },
    "tags": { "type": "array", "items": { "type": "string" } },

    "inputs": {                                     // 类型化入参
      "type": "object",
      "properties": {
        "user_anchor": { "type": "string", "description": "@contact_bbox 等" },
        "text": { "type": "string" },
        "index": { "type": "integer" },
        "timeout_ms": { "type": "integer" }
      },
      "additionalProperties": true
    },

    "outputs": {                                    // 约定产物键（写入 ctx.vars）
      "type": "object",
      "properties": {
        "ok": { "type": "boolean" },
        "meta": { "type": "object" }
      }
    },

    "preconditions": {                              // 前置：环境/锚点/指纹
      "type": "array", "items": { "type": "string" }
    },
    "postconditions": {                             // 后置：成功信号/页面变化
      "type": "array", "items": { "type": "string" }
    },

    "policy": {                                     // 控制执行策略
      "type": "object",
      "properties": {
        "retries": { "type": "integer", "default": 1 },
        "retry_backoff_ms": { "type": "integer", "default": 500 },
        "idempotency_key": { "type": "string" },    // 去重（例如同一消息不重复发送）
        "max_runtime_ms": { "type": "integer", "default": 15000 }
      }
    },

    "impl": {                                       // 具体实现（优先 Macro，其次 instr 序列）
      "type": "object",
      "oneOf": [
        { "properties": { "macro": { "type": "string" }, "args": { "type": "object" } }, "required": ["macro"] },
        { "properties": { "steps": { "type": "array", "items": { "$ref":"#/definitions/action_instruction" } } }, "required": ["steps"] }
      ]
    }
  }
}
```

---

# 3) 运行时新增两个动作

* `task.run`：按名称+版本+参数执行 Task（内部先验 preconditions，绑定参数→运行 impl→校验 postconditions→写指标）。
* `task.compose`：把多个 Task 串成**局部子流程**（顺序/并行/超时策略）。

**最小骨架**

```python
@register_action("task.run")
def task_run(ctx, name:str, args:dict=None, save:str=None, **_):
    t = TASK_REGISTRY.get(name)              # 从服务端/本地缓存拉 Task 定义
    ctx.check_preconditions(t["preconditions"])
    res = run_with_retry(lambda: execute_impl(ctx, t, args or {}), t.get("policy"))
    ctx.check_postconditions(t["postconditions"])
    if save: ctx.vars[save] = res
    ctx.metrics.task_end(name, ok=res.get("ok"), duration=...)
    return res
```

---

# 4) Catalog & 晋升（Staging→Stable→Locked）

* 表结构（示意）：`tasks(name, version, status, schema_hash, impl, created_by)`；`task_stats_daily`（成功率、时延、p95）。
* 晋升规则（可配置）：最近 **N=200** 次执行中成功率 ≥ **95%**、平均步数 ≤ 阈值、事故 0 → 自动从 `staging` 升 `stable`；人工可 `locked`。
* 回滚：一键将默认版本切回上一个 `stable`。
* 权限/计费：沿用你的市场/设备授权；**客户端不直连 DB**，只用 API。

---

# 5) 示例 Task（可直接用）

### 5.1 微信：发送消息

```json
{
  "name": "wechat.send_message",
  "version": "1.0.0",
  "title": "向当前会话发送文本",
  "inputs": { "user_anchor": { "type":"string" }, "text": { "type":"string" } },
  "preconditions": ["app:WeChat.front", "anchor:chat_input_ready"],
  "postconditions": ["ocr:chat_view_contains(@text)"],
  "policy": { "retries": 1, "idempotency_key": "wx:send:@text:@user_anchor" },
  "impl": {
    "steps": [
      { "do":"instr.click",     "target":{"bbox_var":"@user_anchor"} },
      { "do":"instr.type_text", "target":{"bbox_var":"@chat_input_bbox"}, "text":"@text" },
      { "do":"instr.key", "key":"Enter" },
      { "do":"instr.wait", "ms": 300 }
    ]
  }
}
```

### 5.2 Indeed：点击左列第 i 个并点击 Apply

```json
{
  "name": "indeed.apply_current",
  "version": "1.0.0",
  "inputs": { "i": {"type":"integer","default":0} },
  "preconditions": ["host:indeed.com", "ps:left_list_ready"],
  "postconditions": ["dom:text_any_of('Apply','Quick Apply') visible"],
  "impl": { "macro": "apply_click_flow", "args": { "index_offset": "@i" } }
}
```

### 5.3 小红书：展开评论到页底并读取

```json
{
  "name": "xhs.expand_and_read_comments",
  "version": "1.0.0",
  "outputs": { "comments": {} },
  "impl": {
    "steps": [
      { "do":"instr.click", "target":{"role":"button","text":"展开评论"} },
      { "do":"instr.scroll","dir":"down","amount":800,"target":{"css":"div.comment-pane"} },
      { "do":"instr.wait","ms":400 },
      { "do":"instr.read","target":{"css":"div.comment-pane"}, "fields":["texts"], "save":"comments" }
    ]
  }
}
```

---

# 6) Workflow 像搭积木一样引用 Task

```json
{
  "start": "loop",
  "states": {
    "loop": {
      "actions": [
        { "do":"task.run", "name":"indeed.apply_current", "args":{"i":"@i"}, "save":"r1" },
        { "do":"increment_variable", "name":"i" }
      ],
      "transitions": [
        { "if": "@i < 10", "go_to": "loop" },
        { "else_go_to": "done" }
      ]
    }
  }
}
```

---

# 7) Planner/MCTS 如何用 Task

* 在 `llm.plan` 前加 `mem.recall(tasks)`：召回**历史成功的 Task 名称+参数模板**（RAG on Catalog + Plans History）。
* 让 Planner 首选输出 `{"do":"task.run","name":"xxx","args":...}`，**只有缺少 Task**时才降级到 `instr.*`。
* 评估函数（simulate）对 **Task** 给予先验加分（AgentQ），因为它们已在晋升环节验证过。

---

# 8) 验收与指标

* **Task 级**：成功率、平均步数、p95 时延、调用成本（LLM token）、失败 Top 原因。
* **Catalog 级**：安装数、引用数、自动晋升/回滚次数。
* **Workflow 级**：使用 Task 后行数下降 ≥ 30%，成功率不低于原始微步骤实现。

---

# 9) 落地步骤（Sprint K，1–1.5 周）

1. 建 `TASK_REGISTRY`（服务端表/API + 客户端缓存）。
2. 新增 `task.run / task.compose` 动作与日志。
3. 先把 **3 个高频 Task** 实现并上 Catalog（上面三例）：

   * `wechat.send_message`、`indeed.apply_current`、`xhs.expand_and_read_comments`。
4. 控制台加「Task 列表页 & 版本/状态 & 指标」。
5. 晋升规则与一键回滚。
6. Planner 接入：Recall Task + 优先产出 `task.run`。
7. 文档：Task 规范、示例、如何从 Macro 升级成 Task。

---

这样做完，你的 Workflow JSON 会**短很多**、**更稳**，而且“跑多次验证过的 Task”能直接复用，真正做到“搭积木”式自动化。

没问题！下面给你一份**可直接执行的“Task 积木化”落地步骤（Sprint K）**。它把“宏（macro）→Task→Workflow”的全链路一次打通，严格走 API（**客户端不直连 Postgres**），并与现有 `instr.* / macro.run / plan.* / mem.recall` 完全兼容。

---

# 0. 目标与范围（不跑偏）

* 用 **Task** 封装常用动作链：有输入/输出、前后置条件、重试/幂等、指标与版本管理。
* **Workflow嵌Task**：像搭积木组合；Planner/MCTS/AgentQ 优先使用 Task。
* **市场化**：Task 可打包发布（`.taskpack.tgz`），可安装、灰度、回滚。
* 客户端只调 **API**，不直连数据库；OCR/Anchor 在客户端本地执行。

---

# 1. 数据库与存储（迁移 SQL）

> 放到后端服务 Migrate 中执行；对象存储沿用你插件/宏的桶（S3/本地）。

```sql
-- 任务定义（逻辑主表）
CREATE TABLE tasks (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL,                 -- eg. wechat.send_message
  latest_version TEXT,                -- 便捷指针
  UNIQUE(name)
);

-- 任务版本（真正的包）
CREATE TABLE task_versions (
  id BIGSERIAL PRIMARY KEY,
  task_id BIGINT REFERENCES tasks(id) ON DELETE CASCADE,
  version TEXT NOT NULL,              -- 语义化版本
  status TEXT NOT NULL,               -- staging | stable | locked | deprecated
  manifest JSONB NOT NULL,            -- 校验通过后的 Task schema（含 impl/macro/steps）
  pack_url TEXT NOT NULL,             -- .taskpack.tgz 存储地址
  signature TEXT NOT NULL,            -- 包签名
  created_by BIGINT,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(task_id, version)
);

-- 安装/授权（用户/设备维度）
CREATE TABLE task_installations (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  device_id TEXT NOT NULL,
  task_id BIGINT NOT NULL,
  version TEXT NOT NULL,
  enabled BOOLEAN DEFAULT TRUE,
  installed_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id, device_id, task_id, version)
);

-- 运行与指标
CREATE TABLE task_runs (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT,
  device_id TEXT,
  task_id BIGINT,
  version TEXT,
  workflow_run_id BIGINT,
  started_at TIMESTAMPTZ DEFAULT now(),
  ended_at TIMESTAMPTZ,
  ok BOOLEAN,
  steps INT,
  reward DOUBLE PRECISION,
  error TEXT,
  meta JSONB
);

CREATE TABLE task_stats_daily (
  day DATE,
  task_name TEXT,
  version TEXT,
  runs INT,
  success INT,
  avg_steps DOUBLE PRECISION,
  p95_latency_ms INT,
  PRIMARY KEY(day, task_name, version)
);
```

---

# 2. 包结构与签名（`.taskpack.tgz`）

```
/taskpack
  ├─ manifest.json   # 即 Task schema（name/version/inputs/impl/...）
  ├─ impl.yaml       # 纯动作定义（macro 或 instr.* steps）
  ├─ anchors/        # 微信等桌面锚点模板（png/json）
  ├─ ocr/            # OCR 词典/字典（可选）
  └─ SIGNATURE
```

* **签名**：沿用你插件市场的签名机制。后端发布时校验签名+schema，入库 `task_versions`。

---

# 3. 后端 API（仅关键）

* `POST /tasks/publish`：上传包 → 校验签名 & schema → 写 `tasks / task_versions`（默认 `staging`）。
* `POST /tasks/promote`：将某版本设为 `stable`，并更新 `tasks.latest_version`。
* `POST /tasks/rollback`：把默认版本回滚到上一 `stable`。
* `GET  /tasks/list?host=&app=`：按站点/应用列出可用 Task（含状态/版本）。
* `POST /tasks/install`：为用户+设备安装某 Task 版本（计费/权限校验）。
* `POST /task/run`：\*\*（服务端转发/授权）\*\*接收客户端运行请求，返回规范响应/事件流水入口。
* `GET  /tasks/stats`：给控制台汇总指标。

> 说明：客户端仍按本地执行 Task，`/task/run` 可作为“记录开/关账”的入口（也可只打事件 `/events`）。**核心原则：客户端不直连 DB**。

---

# 4. 客户端：注册表与两个动作

## 4.1 注册表（本地缓存 + 拉取安装列表）

* `TASK_REGISTRY`：内存字典（name→版本→定义），启动时从 `/tasks/list` 拉取并按设备安装集同步。
* 若任务依赖 `anchors/` 资源，首次使用时从 `pack_url` 拉到本地缓存。

## 4.2 `task.run`（最小实现逻辑）

1. **加载定义**（name+version 或默认 latest stable）。
2. **参数绑定**：把 `args` 与 `ctx.vars` 合并，校验 `inputs` 类型。
3. **前置校验**：`preconditions`（如 `app:WeChat.front`、`host:indeed.com`、`anchor:chat_input_ready`）。
4. **执行**：

   * 若是宏：`macro.run(name=impl.macro, args=impl.args)`；
   * 若是步骤：逐条 `instr.*`（由编译器落到 ext/coords/ocr）。
5. **后置校验**：`postconditions`（DOM/OCR/页面变化信号）。
6. **策略**：`retries`、`retry_backoff_ms`、`idempotency_key`（结合 `task_runs` 去重）。
7. **记录**：写 `task_runs` 事件（经 API），包含 steps、时延、ok/error。
8. **返回**：`{ ok, outputs }`（outputs 写回 `ctx.vars` 指定命名）。

## 4.3 `task.compose`（可选，本期可延后）

* 顺序/并发（并发需注意 HP 抢占与资源锁），统一超时。

---

# 5. 条件/校验表达式（可复用已有 evaluator）

* `preconditions` / `postconditions` 支持简单谓词：

  * `app:WeChat.front`（前台焦点窗口）
  * `host:indeed.com`（当前浏览器 host）
  * `ocr:chat_view_contains(@text)`（OCR 文本包含）
  * `dom:text_any_of('Apply','Quick Apply') visible`
* 实现上用**适配器**转为已有 `ext.get_pagestate / anchor.find / ocr.recognize` 即可。

---

# 6. Planner / MCTS 集成

* **RAG 召回**：新增 `/tasks/recall?host=&goal=` 返回历史成功 Task（基于 `plans_history + task_runs` 的向量/规则检索），Sprint H 的 `mem.recall` 直接复用。
* **Planner 提示**：把可用 Task 列表作为可选动作，LLM 优先产出：

  ```json
  { "do":"task.run", "name":"indeed.apply_current", "args":{ "i":"@i" } }
  ```
* **MCTS**：把“调用 Task”视作一个原子行动，rollout 奖励加先验（AgentQ 有该 Task 的 Q 值）。

---

# 7. 宏 → Task 的快速迁移

CLI：`wf task scaffold --from-macro apply_click_flow.yaml --name indeed.apply_current --version 1.0.0`

* 自动生成 `manifest.json + impl.yaml`（impl 直接引用宏）；
* 支持补齐 `pre/postconditions` 与 `inputs`；
* 一键 `publish → promote → install` 跑通链路。

---

# 8. 三个“首发 Task”——可直接发布

## 8.1 wechat.send\_message（桌面/坐标）

```json
{
  "name": "wechat.send_message",
  "version": "1.0.0",
  "title": "向当前会话发送文本",
  "inputs": { "user_anchor": {"type":"string"}, "text": {"type":"string"} },
  "preconditions": ["app:WeChat.front", "anchor:chat_input_ready"],
  "postconditions": ["ocr:chat_view_contains(@text)"],
  "policy": { "retries": 1, "idempotency_key": "wx:send:@text:@user_anchor", "max_runtime_ms": 8000 },
  "impl": {
    "steps": [
      { "do":"instr.click",     "target":{"bbox_var":"@user_anchor"} },
      { "do":"instr.type_text", "target":{"bbox_var":"@chat_input_bbox"}, "text":"@text" },
      { "do":"instr.key",       "key":"Enter" },
      { "do":"instr.wait",      "ms": 300 }
    ]
  }
}
```

## 8.2 indeed.apply\_current（Web/宏）

```json
{
  "name": "indeed.apply_current",
  "version": "1.0.0",
  "inputs": { "i": {"type":"integer","default":0} },
  "preconditions": ["host:indeed.com", "ps:left_list_ready"],
  "postconditions": ["dom:text_any_of('Apply','Quick Apply') visible"],
  "policy": { "retries": 1, "max_runtime_ms": 12000 },
  "impl": { "macro": "apply_click_flow", "args": { "index_offset": "@i" } }
}
```

## 8.3 xhs.expand\_and\_read\_comments（Web/步骤）

```json
{
  "name": "xhs.expand_and_read_comments",
  "version": "1.0.0",
  "outputs": { "comments": {} },
  "preconditions": ["host:xiaohongshu.com"],
  "impl": {
    "steps": [
      { "do":"instr.click", "target":{"role":"button","text":"展开评论"} },
      { "do":"instr.scroll","dir":"down","amount":800,"target":{"css":"div.comment-pane"} },
      { "do":"instr.wait","ms":400 },
      { "do":"instr.read", "target":{"css":"div.comment-pane"}, "fields":["texts"], "save":"comments" }
    ]
  }
}
```

---

# 9. Workflow 像搭积木一样使用

```json
{
  "start": "loop_apply",
  "vars": { "i": 0 },
  "states": {
    "loop_apply": {
      "actions": [
        { "do":"task.run", "name":"indeed.apply_current", "args":{"i":"@i"}, "save":"r1" },
        { "do":"increment_variable", "name":"i" }
      ],
      "transitions": [
        { "if": "@i < 10", "go_to": "loop_apply" },
        { "else_go_to": "done" }
      ]
    }
  }
}
```

---

# 10. 可观测与计费（事件与仪表）

* 新增事件：`task.run.start/end`（name/version/ok/duration/steps/error），与 `plan.* / macro.run` 并列；
* 仪表盘：Task 列表（成功率、安装量、Top 失败原因、p95 时延、LLM token/成本）；
* 计费：按“Task 调用次数/时长/调用 LLM 次数”计量；使用现有用户/设备/套餐校验。

---

# 11. 安全与权限

* **客户端不直连数据库**（仅 API）。
* Task 包签名校验 + 白名单动作（内部仍走 `allowed_actions`/来源校验）。
* 桌面任务强制 `focus_app(WeChat)` + 限定窗口内点击。
* 上传/敏感动作需显式 Capability（平台层开关）。

---

# 12. 测试与验收（必须做）

**单元**

* schema 校验、参数绑定、前后置条件解析、重试/幂等。
  **集成**
* 端到端：`publish→install→task.run→stats` 全链路；宏迁移工具。
  **E2E 实机**
* 微信/Indeed/小红书各 ≥20 次回合：

  * Task 成功率 ≥ 对应手写动作基线；
  * Workflow JSON 行数 ↓ ≥30%；
  * 指标入库正确，控制台可见。
    **通过标准**
* 回滚 1 分钟内生效；关闭 Feature Flag 不影响旧 Workflow 运行。

---

# 13. 推出与回滚（Feature Flags）

* `features.tasks.enabled`（全局）
* `features.tasks.use_in_planner`（Planner 优先用 `task.run`）
* 出现异常：关闭第二个 flag → Planner 降级为 macro/instr；必要时关闭第一个 flag，原有流程不受影响。

---

# 14. 今日待办（你可以马上分工）

1. 执行上方 **SQL 迁移**；创建 S3/bucket 前缀 `taskpacks/`。
2. 落 `POST /tasks/publish|promote|rollback|install|list|stats`（签名与 schema 校验）。
3. 客户端实现 `TASK_REGISTRY` + `task.run`；接入事件。
4. 将三款 **首发 Task** 打包并 `publish → promote → install`。
5. 在 Indeed/XHS/微信工作流中替换一处为 `task.run` 验证可用。
6. 控制台新增 Task 卡片与统计。
7. Planner 提示/回退策略切换到“优先 Task”。
8. 写 Runbook：如何从 Macro 产出 Task、如何晋升/回滚。

---

太好了！我把前面承诺的**最小可跑模板**直接给你，拷进仓库就能跑第一版 Task 积木化：

---

# 1) `POST /tasks/publish` 示例（含包结构与 manifest）

## 1.1 `manifest.json`（放进 `.taskpack.tgz`）

```json
{
  "name": "wechat.send_message",
  "version": "1.0.0",
  "title": "向当前会话发送文本",
  "description": "点击会话 → 聚焦输入框 → 发送文本 → 轻等待",
  "tags": ["wechat","desktop","messaging"],
  "inputs": { "user_anchor": {"type":"string"}, "text": {"type":"string"}, "timeout_ms": {"type":"integer","default":8000} },
  "outputs": { "ok": {}, "meta": {} },
  "preconditions": ["app:WeChat.front", "anchor:chat_input_ready"],
  "postconditions": ["ocr:chat_view_contains(@text)"],
  "policy": { "retries": 1, "retry_backoff_ms": 400, "idempotency_key": "wx:send:@text:@user_anchor", "max_runtime_ms": 8000 },
  "impl": {
    "steps": [
      { "do":"instr.click",     "target":{"bbox_var":"@user_anchor"} },
      { "do":"instr.type_text", "target":{"bbox_var":"@chat_input_bbox"}, "text":"@text" },
      { "do":"instr.key",       "key":"Enter" },
      { "do":"instr.wait",      "ms": 300 }
    ]
  }
}
```

## 1.2 打包（最小脚本）

```bash
mkdir -p taskpack && \
cp manifest.json taskpack/ && \
echo "anchors and extra files optional" > taskpack/README && \
tar -czf wechat.send_message-1.0.0.taskpack.tgz -C taskpack .
```

## 1.3 发布（curl）

```bash
curl -X POST https://your-api/tasks/publish \
  -H "Authorization: Bearer <token>" \
  -F "file=@./wechat.send_message-1.0.0.taskpack.tgz"
```

返回（示例）：

```json
{
  "task_id": 12,
  "name": "wechat.send_message",
  "version": "1.0.0",
  "status": "staging",
  "pack_url": "s3://taskpacks/wechat.send_message/1.0.0.tgz",
  "signature_ok": true
}
```

---

# 2) 服务端最小 Handler（Node/Express）

```ts
// server/routes/tasks.publish.ts
import express from "express";
import { verifySignature, parseTaskpack, validateManifest } from "../services/taskpack";
import { pg } from "../services/pg";

export const tasksRouter = express.Router();

tasksRouter.post("/tasks/publish", async (req, res) => {
  try {
    const file = (req as any).file || (req as any).files?.file;
    if (!file) return res.status(400).json({ error: "file missing" });

    const { manifest, signature } = await parseTaskpack(file.path); // 解包读取 manifest.json / SIGNATURE
    const ok = await verifySignature(file.path, signature);
    if (!ok) return res.status(400).json({ error: "bad signature" });

    const v = validateManifest(manifest); // 基于 JSON Schema 校验
    if (!v.ok) return res.status(400).json({ error: "schema invalid", details: v.errors });

    // upsert tasks / task_versions
    const t = await pg.oneOrNone("SELECT id FROM tasks WHERE name=$1", [manifest.name]);
    const taskId = t?.id ?? (await pg.one("INSERT INTO tasks(name, latest_version) VALUES($1,$2) RETURNING id",
      [manifest.name, manifest.version])).id;

    await pg.none(
      `INSERT INTO task_versions(task_id, version, status, manifest, pack_url, signature, created_by)
       VALUES($1,$2,'staging',$3,$4,$5,$6)
       ON CONFLICT(task_id,version) DO UPDATE SET manifest=$3, pack_url=$4, signature=$5`,
      [taskId, manifest.version, manifest, `s3://taskpacks/${manifest.name}/${manifest.version}.tgz`, signature, req.user?.id || null]
    );

    res.json({ task_id: taskId, name: manifest.name, version: manifest.version, status: "staging" });
  } catch (e:any) {
    res.status(500).json({ error: e.message });
  }
});
```

> 另外再加 `/tasks/promote`, `/tasks/rollback`, `/tasks/install`, `/tasks/list` 按我们前面约定落下即可。

---

# 3) 客户端 `task.run`（Python，含重试/幂等/前后置条件）

```python
# runtime/actions/task.run.py
import time, hashlib, json
from runtime.engine.registry import register_action
from runtime.engine.errors import ValidationError

def _idem_key(name, args):
    raw = f"{name}:{json.dumps(args, sort_keys=True)}"
    return "idem:" + hashlib.sha1(raw.encode()).hexdigest()

def _check_pre(ctx, preds):
    for p in preds or []:
        if p.startswith("app:"):
            if not ctx.win.is_front(p.split(":",1)[1]): return False, p
        elif p.startswith("host:"):
            ps = ctx.vars.get("ps") or {}
            if p.split(":",1)[1] not in (ps.get("host") or ps.get("url","")): return False, p
        elif p.startswith("anchor:"):
            if not ctx.anchor.ready(p.split(":",1)[1]): return False, p
        elif p.startswith("ocr:"):
            # 简化示例，实际用 ctx.ocr.contains(...)
            pass
    return True, None

def _check_post(ctx, posts, args):
    for p in posts or []:
        if p.startswith("ocr:chat_view_contains("):
            txt = args.get("text") or ""
            ok = ctx.ocr.contains(region=ctx.vars.get("chat_view_bbox"), text=txt)
            if not ok: return False, p
        # DOM 可用时：ext.extract/visibility 判断
    return True, None

def _execute_impl(ctx, manifest, bound_args):
    impl = manifest["impl"]
    if "macro" in impl:
        return ctx.actions["macro.run"](ctx, name=impl["macro"], args=impl.get("args") or {}, save=None)
    else:
        ok = True; steps = 0
        for step in impl["steps"]:
            # 变量替换（@xxx）
            resolved = ctx.helpers.bind_params(step, {**ctx.vars, **bound_args})
            r = ctx.actions[resolved["do"]](ctx, **{k:v for k,v in resolved.items() if k!="do"})
            ok = ok and bool(r.get("ok", True)); steps += 1
            if not ok: break
        return {"ok": ok, "steps": steps}

@register_action("task.run")
def task_run(ctx, name:str, args:dict=None, version:str=None, save:str=None, **_):
    args = args or {}
    # 1) 拉取定义（本地缓存优先）
    td = ctx.tasks.get(name, version)  # 从 TASK_REGISTRY
    if not td: raise ValidationError(f"task not installed: {name}@{version or 'latest'}")
    manifest = td["manifest"]

    # 2) 幂等：若提供 idempotency_key，查重
    idem = manifest.get("policy", {}).get("idempotency_key")
    if idem:
        ikey = _idem_key(name, ctx.helpers.bind_params({"k": idem}, {**ctx.vars, **args})["k"])
        if ctx.cache.exists(ikey):
            res = ctx.cache.get(ikey); 
            if save: ctx.vars[save] = res
            return res

    # 3) 前置
    ok, pred = _check_pre(ctx, manifest.get("preconditions"))
    if not ok: raise ValidationError(f"precondition failed: {pred}")

    # 4) 重试策略
    retries = int(manifest.get("policy", {}).get("retries", 0))
    backoff = int(manifest.get("policy", {}).get("retry_backoff_ms", 400))
    attempt, res = 0, None
    while attempt <= retries:
        start = time.time()
        res = _execute_impl(ctx, manifest, args)
        duration = int((time.time() - start)*1000)
        ctx.events.log("task.run.end", {"name": name, "version": manifest["version"], "ok": res.get("ok"), "duration_ms": duration})
        if res.get("ok"): break
        time.sleep(backoff/1000.0); attempt += 1

    # 5) 后置
    ok2, post = _check_post(ctx, manifest.get("postconditions"), args)
    res["ok"] = res.get("ok") and ok2
    if not ok2: res["error"] = f"postcondition failed: {post}"

    # 6) 记录（通过 API，不直连 DB）
    ctx.http.post("/task/run", json={
        "name": name, "version": manifest["version"], "ok": res.get("ok"),
        "steps": res.get("steps"), "error": res.get("error"), "meta": {"args": args}
    }, timeout=2000)

    if idem and res.get("ok"):
        ctx.cache.set(ikey, res, ttl=3600)

    if save: ctx.vars[save] = res
    return res
```

---

# 4) 工作流里调用（示例）

```json
{
  "start": "loop",
  "vars": {"i": 0},
  "states": {
    "loop": {
      "actions": [
        { "do":"task.run", "name":"indeed.apply_current", "args":{"i":"@i"}, "save":"r1" },
        { "do":"increment_variable", "name":"i" }
      ],
      "transitions": [
        { "if": "@i < 10", "go_to": "loop" },
        { "else_go_to": "done" }
      ]
    }
  }
}
```

---

# 5) 最小测试清单（今天可跑）

1. **发布**：用上面的 `manifest.json` 打 `.taskpack`，`/tasks/publish` 返回 `staging`。
2. **晋升**：`/tasks/promote` → `stable`；设备端拉取安装列表。
3. **运行**：`task.run wechat.send_message` 对着测试窗口跑一次，检查事件与 `postconditions`（OCR 包含发送文本）。
4. **幂等**：同参数重复调用，命中缓存不重复发。
5. **失败回退**：人为让 `anchor:chat_input_ready` 失败，验证 `precondition` 抛错。
6. **指标**：控制台能看到 `task_runs`/日统计。

---
base64 < s2.png | tr -d '\n' > s2.b64.txt

curl https://api.openai.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer \$OPENAI_API_KEY" \
  -d @- <<EOF
{
  "model": "gpt-4o-mini",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "Describe this image." },
        {
          "type": "image_url",
          "image_url": { "url": "data:image/png;base64,$(cat s2.b64.txt)" }
        }
      ]
    }
  ]
}
EOF
