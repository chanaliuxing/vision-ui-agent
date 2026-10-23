下面是把我们整套系统（阶段 1–13）里**工作流 JSON**可控制的一切参数，汇总成一份**实用规范文档**。它兼容你给的旧 Schema，并加入我们后来实现的「变量/循环/条件转场、OCR/LLM/MQ/聊天适配器、人类化/容错」等扩展。你可以把它当作**v1.1 草案**：老工作流可直接跑；新字段是向后兼容的增量。

---

# 工作流 JSON 规范 v1.1（实用版）

## 0. 术语约定

* **变量引用**：`@var`（或 `@obj['key']` / `@obj.key`），运行时从内存取值。
* **字符串插值**：`"device.${device_id}.wechat.hp.fifo"`（`${…}` 来自工作流变量/系统上下文）。
* **保存结果**：大多数动作支持 `"save": "<var>"` 或 `"save_as": "<var>"`，写入工作流内存（全局作用域）。
* **返回值规范**：动作成功返回 `{ ok:true, ... }`；失败 `{ ok:false, error:"..." }`。

---

## 1. 顶层结构

```json
{
  "version": "1.1",                         // 可选
  "name": "可选：工作流名称",
  "description": "可选：说明",
  "start": "state_id",                      // 必填：起始状态
  "vars": {                                 // 可选：初始变量（全局）
    "app": "wechat_desktop",
    "device_id": "${runtime.device_id}"
  },
  "meta": {                                 // 可选：调度/并发元信息
    "priority": "HIGH",                     // HIGH | LOW（HP/LP）
    "resource_lock": "CHAT_UI_${app}"       // 同资源互斥
  },
  "states": { "…": { /* 见下 */ } }         // 必填：状态图
}
```

* `meta.priority`：调度优先级（HP/LP）。
* `meta.resource_lock`：同一资源（如聊天窗口）互斥，避免并发冲突。

---

## 2. 状态（State）

```json
"state_id": {
  "description": "可选",
  "vars": { "local_overrides": true },     // 可选：进入该状态时覆盖/新增变量
  "actions": [ /* 顺序执行 */ ],
  "transitions": [                         // v1.1 新增：条件转场（首命中即跳转）
    { "if": "@x < 10", "go_to": "next" },
    { "else_go_to": "fallback" }
  ],
  "on_success": "next_legacy",             // 兼容旧字段：若无 transitions，用它
  "on_error": "recover_or_end",            // 可选：动作失败的兜底跳转
  "state_timeout_ms": 15000                // 可选：该状态最长停留时间
}
```

**执行顺序**

1. 依次跑 `actions`；
2. 若全部成功：按 `transitions` 逐条判断，第一个命中跳转；如果未定义 `transitions`，退回 `on_success`；
3. 任一动作失败：若设 `on_error` 则跳；否则引擎记录失败并停止（可由上层恢复策略接管）。

---

## 3. 表达式与插值

### 3.1 条件表达式（`"if": "<expr>"`）

* 支持：`== != < <= > >= && || !`、括号、数字/布尔/字符串/`null`。
* 变量：`@var`、`@obj.key`、`@arr[0]`。
* 例：`"@job_index < @total_jobs && @current_job != null"`

### 3.2 字符串插值（运行前展开）

* 语法 `${...}`，从 `vars` 与系统上下文取值：`"device.${device_id}.${app}.hp.fifo"`。
* 与 `@` 不同：`@` 在**条件/参数**里按值使用；`${}` 在**字符串**内先替换为文本。

---

## 4. 标准动作库（Actions）

> 下方列出**动作名、参数、保存值、注意事项**。未列出的旧动作保持原行为（见你提供的 Schema）。

### 4.1 基础控制

1. `sleep_ms` / `wait_ms`（等价）

```json
{ "do":"sleep_ms", "value": 800 }
```

2. `wait_for`（等待某条件）

```json
{ "do":"wait_for", "until": {
  "type": "ext.wait_quiet",               // or: yolo_appear | spinner_disappear | sleep_ms
  "value": "selector_or_label",           // 取决于 type
  "rules": ["page_change"],               // 可选，事件规则
  "timeout_ms": 12000, "poll_ms": 300
}}
```

3. `branch`（可选语法糖：在 actions 内直接跳转）

```json
{ "do":"branch", "if":"@has_unread==true", "then":"open", "else":"sleep" }
```

---

### 4.2 视觉/键鼠（Vision + UI）

* `screenshot`

```json
{ "do":"screenshot", "save_as":"shot_{n}.png" }
```

* `detect`（YOLO/检测）

```json
{ "do":"detect", "return_image": false, "save_json":"yolo_{n}.json", "save_overlay":"ov_{n}.png" }
```

* `locate`（目标/候选集合定位）

```json
{ "do":"locate", "targets":["评论按钮","搜索框"], "candidates":["发布","输入"], "verify": { "type":"yolo_appear","timeout_ms":8000 } }
```

* `click`（基于最近一次 `locate/autostep` 目标）

```json
{ "do":"click" }
```

* `type_text`

```json
{ "do":"type_text", "text":"非常好", "mode":"auto" }   // auto|type|paste
```

* `scroll`

```json
{ "do":"scroll", "clicks": -200 }                      // 鼠标滚轮：负数=向下，正数=向上
```

* `go_back`

```json
{ "do":"go_back" }
```

* `autostep`（智能一步：描述目标 → 视觉/DOM 执行）

```json
{
  "do":"autostep",
  "goal":"点击左上角第一个搜索结果卡片",
  "picker":"vision",                                   // 也可留空（默认）
  "executor":"vision",                                 // vision | dom | dom+coords
  "k":12, "hints":["选择最上排最左边的内容卡片"],
  "verify": { "timeout_ms": 10000, "poll_ms": 600, "rules":["page_change"] },
  "fallback": { "action":"scroll", "clicks": -200 },
  "save": { "shot":"step_{n}.png","yolo":"yolo_{n}.json","picker":"picker_{n}.json" }
}
```

* `click_coordinates`（用变量里的 bbox 点击；桥接 DOM→pyautogui）

```json
{ "do":"click_coordinates", "bbox":"@current_job_bbox" }  // bbox = [x,y,w,h] 或 {x,y,w,h}
```

---

### 4.3 浏览器扩展（DOM 执行，`ext.*`）

* `open_url`（本地应用唤起 + 地址）

```json
{ "do":"open_url", "url":"https://www.xiaohongshu.com/explore", "app":"Google Chrome" }
```

* `ext.open_url`（让浏览器扩展在当前页打开/激活）

```json
{ "do":"ext.open_url", "url":"https://ca.indeed.com/", "active": true }
```

* `ext.click_selector`

```json
{ "do":"ext.click_selector", "sel":"#jobDescriptionText" }
```

* `ext.type_text`

```json
{ "do":"ext.type_text", "sel":"input[name=q]", "text":"温哥华 卖车", "replace": true }
```

* `ext.key`

```json
{ "do":"ext.key", "key":"Enter" }
```

* `ext.scroll`

```json
{ "do":"ext.scroll", "dir":"down", "amount": 1200 }
```

* `ext.extract`（提取 DOM 内容，**旧例中已有**）

```json
{ "do":"ext.extract", "args": { "selector": "#jobDescriptionText" }, "save":"job_html" }
```

---

### 4.4 变量/数据（让 JSON 拥有脚本力）

* `set_variable`

```json
{ "do":"set_variable", "name":"job_index", "value": 0 }
```

* `increment_variable`

```json
{ "do":"increment_variable", "name":"job_index" }
```

* `get_list_length`

```json
{ "do":"get_list_length", "from":"@job_links", "save":"total_jobs" }
```

* `get_list_item`

```json
{ "do":"get_list_item", "from":"@job_links", "index":"@job_index", "save":"current_job_link" }
```

* `query_data`（从对象中取字段/路径）

```json
{ "do":"query_data", "from":"@current_job_link", "query":"bbox", "save":"current_job_bbox" }
```

> 说明：`query` 支持 `.a.b[0]`、`["键名含空格"]` 等常见 JSON 路径子集。

---

### 4.5 消息队列（SQS / LocalStack 统一封装，`mq.*`）

* `mq.consume`（拉取一条消息）

```json
{ "do":"mq.consume", "topic":"device.${device_id}.${app}.hp.fifo", "save":"msg", "visibility_timeout_ms": 15000 }
```

* `mq.ack`（确认处理完成）

```json
{ "do":"mq.ack", "topic":"device.${device_id}.${app}.hp.fifo", "from_var":"msg" }
```

* `mq.publish`（可选，用于触发下游）

```json
{ "do":"mq.publish", "topic":"events.workflow", "payload":"@some_object" }
```

---

### 4.6 OCR（本地）

* `ocr.run`

```json
{
  "do":"ocr.run",
  "roi":"@bubbles_roi",                    // 可传 [x,y,w,h] 或图像切片
  "lang":"chi_sim+eng",
  "psm": 6,                                // 版面模式
  "cache": true,                           // 相同图像缓存
  "save":"ocr_text"
}
```

---

### 4.7 聊天适配器（桌面/Android 统一接口，`chat.*`）

* `chat.find_unread` → `{"has_unread": true, "count": 1}`

```json
{ "do":"chat.find_unread", "save":"ur" }
```

* `chat.open_latest_unread`

```json
{ "do":"chat.open_latest_unread" }
```

* `chat.capture_visible`

```json
{ "do":"chat.capture_visible", "save":"cap" }   // 通常返回 { image, bubbles_roi, contact_name?... }
```

* `chat.focus_contact`

```json
{ "do":"chat.focus_contact", "name":"@msg['contact_name']" }
```

* `chat.send_text`

```json
{ "do":"chat.send_text", "text":"@msg['reply_text']" }
```

> 以上动作在后台启用人类化（鼠标曲线/打字纠错/前台校验），无需在 JSON 写额外参数。

---

### 4.8 LLM 提交（云端路由、计量、强结构化）

* `llm.submit`

```json
{
  "do":"llm.submit",
  "job":"chat_reply",
  "prompt_pack":"wechat.sales.reply.v1",
  "schema":"WeChatReplyV1",                 // JSON Schema key（强制结构化）
  "provider_hint":"AUTO",                   // AUTO | FORCE:<provider>
  "inputs": { "app":"wechat", "new_messages_text":"@ocr_text" },
  "timeout_ms": 25000,
  "save":"llm_out"                          // e.g. {contact_name, reply_text}
}
```

---

## 5. 可靠性与容错（可选参数）

> 引擎默认带重试/熔断；以下是 JSON 层可覆写的**轻量控制**。

* 任意动作均可接受（引擎扩展层面实现，JSON 可选传）：

```json
{
  "do": "…",
  "retry": { "attempts": 3, "base_ms": 300, "max_ms": 3000 },   // 指数退避
  "timeout_ms": 8000
}
```

* 状态级别：`"state_timeout_ms": 15000` 超时触发 `on_error`。
* 幂等：队列消息已在服务端做去重；`mq.consume` 输出对象含 `idempotency_key`（只读）。

---

## 6. 转场模式对比（旧 vs 新）

| 用法    | 旧字段                   | 新字段                                                                     |
| ----- | --------------------- | ----------------------------------------------------------------------- |
| 无条件前进 | `"on_success":"next"` | `{"transitions":[{"go_to":"next"}]}`                                    |
| 条件分支  | 不支持                   | `{"transitions":[{"if":"@i<@n","go_to":"loop"},{"else_go_to":"done"}]}` |
| 错误兜底  | 无                     | `"on_error":"recover"`, 或在引擎层重试后触发                                      |

> **向后兼容**：老工作流只写 `on_success` 仍然有效；引擎优先看 `transitions`。

---

## 7. 常见模式配方

### 7.1 列表循环（DOM 抓取 → 坐标点击）

```json
{
  "start":"init",
  "states":{
    "init": {
      "actions":[
        { "do":"ext.extract", "args":{"selector":".job-card"}, "save":"job_links" },
        { "do":"get_list_length", "from":"@job_links", "save":"total_jobs" },
        { "do":"set_variable", "name":"job_index", "value":0 }
      ],
      "on_success":"each"
    },
    "each": {
      "actions":[
        { "do":"get_list_item", "from":"@job_links", "index":"@job_index", "save":"current" },
        { "do":"query_data", "from":"@current", "query":"bbox", "save":"bbox" },
        { "do":"click_coordinates", "bbox":"@bbox" },
        { "do":"wait_for", "until":{"type":"ext.wait_quiet","timeout_ms":8000} },
        { "do":"increment_variable", "name":"job_index" }
      ],
      "transitions":[
        { "if":"@job_index < @total_jobs", "go_to":"each" },
        { "else_go_to":"done" }
      ]
    },
    "done": { "actions":[{ "do":"sleep_ms","value":300 }] }
  }
}
```

### 7.2 WeChat LP→HP 异步编排

* LP（轮询→OCR→LLM）见我们上一条消息示例；
* HP（收队列→发送）同上；
* 通过 `mq.consume/ack` 串起两个工作流，**HP 永远优先**（由调度器根据 `meta.priority` 与资源锁保证）。

---

## 8. 与旧 Schema 的字段对照（你提供的部分）

已支持 & 兼容：

* 顶层：`version/start/vars/states` ✅
* 状态：`actions`、`on_success` ✅（新增 `transitions/on_error/state_timeout_ms/vars/meta`）
* 旧动作：`open_url/sleep_ms/screenshot/wait_for/detect/locate/click/type_text/scroll/go_back/autostep/decide_with_gemini/ext.*` ✅
* 新动作：`click_coordinates`、**变量/数据**组（`set_variable/increment_variable/get_list_length/get_list_item/query_data`）、**MQ**（`mq.consume/ack/publish`）、**OCR**（`ocr.run`）、**聊天**（`chat.*`）、**LLM**（`llm.submit`）✅

---

## 9. 错误码与可观测（简述）

* 任意动作失败时记录事件：`{category:"action", name:"<do>", level:"error", data:{ error, args }}`。
* 关键视觉/OCR/LLM 事件都有 `run_events` 记录，便于在 Web 回放（阶段 12）里复盘。
* **暂停/恢复**由控制面板或 Assist 指令触发，不需要在 JSON 里配置。

---

## 10. 最小可运行示例（WeChat 自动回复）

**LP：**

```json
{
  "start":"poll",
  "vars":{"app":"wechat_desktop"},
  "states":{
    "poll":{
      "actions":[ { "do":"chat.find_unread", "save":"ur" } ],
      "transitions":[
        { "if":"@ur['has_unread']==true", "go_to":"open" },
        { "else_go_to":"sleep" }
      ]
    },
    "sleep": { "actions":[ { "do":"sleep_ms","value":1500 } ], "on_success":"poll" },
    "open":{
      "actions":[
        { "do":"chat.open_latest_unread" },
        { "do":"chat.capture_visible", "save":"cap" },
        { "do":"ocr.run", "roi":"@cap['bubbles_roi']", "lang":"chi_sim+eng", "psm":6, "cache":true, "save":"text" },
        { "do":"llm.submit", "job":"chat_reply", "prompt_pack":"wechat.sales.reply.v1", "schema":"WeChatReplyV1",
          "provider_hint":"AUTO", "inputs": { "app":"wechat", "new_messages_text":"@text" } }
      ],
      "on_success":"poll"
    }
  }
}
```

**HP：**

```json
{
  "meta": { "priority":"HIGH", "resource_lock":"CHAT_UI_${app}" },
  "vars":{"app":"wechat_desktop"},
  "start":"wait",
  "states":{
    "wait":{
      "actions":[ { "do":"mq.consume", "topic":"device.${device_id}.${app}.hp.fifo", "save":"msg" } ],
      "transitions":[ { "if":"@msg != None && @msg != 'pending'", "go_to":"send" }, { "else_go_to":"wait" } ]
    },
    "send":{
      "actions":[
        { "do":"chat.focus_contact", "name":"@msg['contact_name']" },
        { "do":"chat.send_text", "text":"@msg['reply_text']" },
        { "do":"mq.ack", "topic":"device.${device_id}.${app}.hp.fifo", "from_var":"msg" }
      ],
      "on_success":"wait"
    }
  }
}
```

---

### 结语

这份文档覆盖了**能写进 JSON 的所有开关**：从**动作参数**、**变量/循环/条件转场**到**LLM/OCR/MQ/聊天**，再到**调度/容错/资源锁**。

---

# 附录 A（v1.1 增量说明）

本附录汇总本次升级新增/强化的关键能力，以便老工作流平滑迁移。

## A.1 顶层 `autofix`（自愈/自动晋升）

```json
{
  "name": "my_flow",
  "autofix": {
    "mode": "auto_promote_on_success",       // suggest_only | hot_patch_session | auto_promote_on_success
    "limits": { "max_patches_per_run": 2 },  // 本次运行热补次数上限
    "allowed_patch_kinds": ["wait_quiet_insert","scroll_then_retry"],
    "promote": { "enabled": true }
  }
}
```

- 建议记录：out/logs/patch_proposals.jsonl。
- 热补：在运行中小幅 `wait_quiet/scroll` 后重试一次（限次）。
- 自动晋升：run 成功后将“安全补丁”固化为 flows/<name>.autofix.json，并保存审计副本至 out/logs/patched_workflow_*.json。

## A.2 语义指令集 `instr.*`

> 优先暴露给 LLM/作者的少量稳定动词，由执行器编译成 DOM 原语或坐标。

常用：
- `instr.click` / `instr.type_text(clear?)` / `instr.select_option(value)` / `instr.scroll(dir,amount)`
- `instr.navigate(url)` / `instr.history(op)` / `instr.hover` / `instr.key(key|WaitQuiet)`
- `instr.upload(file)` / `instr.read(fields)` / `instr.wait(ms)` / `instr.task_complete(message)` / `instr.answer_user(text)`

目标（target）统一结构：

```json
{
  "element_id": "id-123",      // 可选
  "css": "#id .class",         // 可选
  "xpath": "//button[1]",     // 可选
  "role": "button",           // 可选
  "text": "Apply",            // 可选
  "bbox_var": "@anchor"        // 可选：坐标回退/桌面场景
}
```

## A.3 扩展 DOM 原语（`ext.*` 补齐）

- `ext.resolve(target)`：解析到 `{ selector?, bbox? }`
- `ext.hover(sel)`：`mouseover/mouseenter`
- `ext.select_option(sel,value)`：赋值并派发 `input/change`
- `ext.upload_file(sel,file)`：CDP `DOM.setFileInputFiles`（需调试权限）
- `ext.history(op)`：浏览器后退/前进

> 以上用于强化 `instr.*` 的 DOM 路径；失败时执行器会退回坐标链路（若提供 `bbox_var`）。
