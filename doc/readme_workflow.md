# 工作流编写说明文档（作者版 · v1.0）

> 适用于 yolo+llm 自动化平台的**工作流（Workflow）**作者与工程师。本文教你从零到一编写、调试、发布一个可复用、可观测、可回滚的工作流，覆盖 Web（DOM/CDP）与桌面（坐标/OCR/锚点）两大场景，并与 **Task（任务积木）**、**Macro（技能/宏）**、**`instr.*` 语义指令集** 完整对接。

---

## 0. 基本心智模型

* **Workflow = 状态机**
  由若干 `states` 组成，每个状态包含一组 `actions`（动作），执行完后通过 `transitions` 跳转到下一个状态。
* **Action = 原子步骤**
  对 LLM/作者暴露的动作首选 **`instr.*` 语义指令**（如 `instr.click` / `instr.scroll`）。编译器会把它们自动落到 Web 的 `ext.*` 或桌面的 `coords.* / anchor.*`。
* **Macro 与 Task**

  * **Macro**：可复用的动作片段（MicroPlan），无强 I/O 约束。
  * **Task**：带输入/输出、重试/幂等/指标与前后置条件的“积木”。在工作流中优先使用 `task.run` 组合任务，复杂场景才降级到 `instr.*` 明细动作。
* **PageState（可选）**
  在 Web 场景可通过扩展获取页面结构指纹与关键区域 bbox，便于定位与回退。
* **优先级与异步**
  将“必须优先响应”的子流程（如微信回消息）放入高优先级队列（HP），巡检/采集类放入低优先级队列（LP）。

---

## 1. 工作流 JSON 结构

### 1.1 最小骨架

```json
{
  "version": "1.3",
  "start": "state_name",
  "vars": { },
  "features": {
    "macros": { "enabled": true },
    "planner": { "enabled": false },
    "tasks": { "enabled": true }
  },
  "states": {
    "state_name": {
      "actions": [ /* 一组动作（顺序执行） */ ],
      "transitions": [
        { "if": "<表达式>", "go_to": "next_state" },
        { "else_go_to": "fallback_or_end" }
      ]
    }
  }
}
```

### 1.2 常用顶层字段

* `version`：工作流版本号（字符串/数字）。
* `start`：起始状态名。
* `vars`：全局变量（循环计数、常量、配置等）。
* `features`：可选功能开关（是否启用任务、宏、规划器等）。
* `states`：状态集合（至少一个），每个状态包含：

  * `actions`：动作数组（按顺序执行）。
  * `transitions`：条件跳转；支持 `if`/`else_go_to`。也兼容老的 `on_success`。

> 建议：**尽量把业务逻辑封装为 Task**，工作流只做编排与循环/条件，能显著缩短 JSON 并提高稳定性。

---

## 2. 动作（Actions）写法

### 2.1 首选语义指令 `instr.*`（推荐 12–14 个）

**统一目标（target）格式：**

```json
{ "element_id":"...", "css":"...", "xpath":"...", "role":"button", "text":"Apply", "bbox_var":"@some_bbox" }
```

**解析顺序**：`element_id → css → xpath → role+text → bbox_var`（Web 失败后回退到坐标；桌面直接用 `bbox_var`）。

**常用 `instr.*` 列表与参数：**

* `instr.click` → `{ "target": { ... } }`
* `instr.type_text` → `{ "target":{...}, "text":"...", "clear":false }`
* `instr.select_option` → `{ "target":{...}, "value":"US" }`
* `instr.scroll` → `{ "dir":"down", "amount":600, "target":{...} }`
* `instr.navigate` → `{ "url":"https://..." }`
* `instr.history` → `{ "op":"back" }`
* `instr.hover` → `{ "target":{...} }`
* `instr.key` → `{ "key":"Enter", "target":{...} }`
* `instr.upload` → `{ "target":{...}, "file":"/path/to/file" }`（Web 用 CDP）
* `instr.read` → `{ "target":{...}, "fields":["text","html","lines"], "save":"var_name" }`
* `instr.wait` → `{ "ms": 400 }`（或内部映射 `wait_quiet`）
* 结束类：`instr.task_complete` / `instr.answer_user`

> **保存输出**：动作通常支持可选 `save` 字段，将结果写入 `vars`，例如 `{ "do":"instr.read", ..., "save":"job_desc" }`。

### 2.2 直接调用 Task（强烈推荐）

```json
{ "do":"task.run", "name":"indeed.apply_current", "args": { "i":"@i" }, "save":"r" }
```

* Task 会自动处理重试/幂等、前后置条件、指标与错误。
* 适合**稳定可复用**的子流程：如“微信发消息”“Indeed 点击第 i 个职位并点 Apply”“小红书展开评论到底”。

### 2.3 使用 Macro（动作片段）

```json
{ "do":"macro.run", "name":"apply_click_flow", "args":{"index_offset":"@i"} }
```

* Macro 适合**较短**的、对站点强相关的动作片段。
* 与 Task 的差异：Macro 不定义 I/O 与重试策略，通常被 Task 或 Workflow 包裹。

### 2.4 变量与数据动作（局部逻辑）

* `set_variable` / `increment_variable`
* `get_list_length` / `get_list_item`
* `query_data`（JSONPath/字段提取）
* `sleep_ms`（短等待；更推荐 `instr.wait` 或 `wait_for: ext.wait_quiet`）

---

## 3. 条件与循环（Transitions）

### 3.1 条件表达式

* 支持比较与逻辑运算：`@i < 10`、`@job_index < @total_jobs`、`@r['ok']==true`
* 变量引用用 `@var_name`；对象属性用 `@obj['key']` 或 `@obj.key`（实现以引擎为准）。

### 3.2 循环示例（遍历 10 个职位）

```json
{
  "start":"loop",
  "vars":{"i":0},
  "states":{
    "loop":{
      "actions":[
        { "do":"task.run", "name":"indeed.apply_current", "args":{"i":"@i"}, "save":"r" },
        { "do":"increment_variable", "name":"i" }
      ],
      "transitions":[
        { "if":"@i < 10", "go_to":"loop" },
        { "else_go_to":"done" }
      ]
    }
  }
}
```

### 3.3 无限滚动直到“底部锚点”出现（小红书评论）

```json
{
  "start":"scroll_loop",
  "states":{
    "scroll_loop":{
      "actions":[
        { "do":"instr.scroll","dir":"down","amount":800,"target":{"css":"div.comment-pane"} },
        { "do":"anchor.find","template":"xhs_end_marker","region":"@comment_pane_bbox","save":"end_bbox" }
      ],
      "transitions":[
        { "if":"@end_bbox != null", "go_to":"extract" },
        { "else_go_to":"scroll_loop" }
      ]
    },
    "extract":{
      "actions":[ { "do":"instr.read","target":{"css":"div.comment-pane"}, "fields":["texts"], "save":"comments" } ]
    }
  }
}
```

---

## 4. Web 与桌面的差异写法

### 4.1 Web（优先 DOM/CDP）

* 目标写法优先使用：`role+text` 或 **稳定 CSS**，避免动态 ID。
* 默认 `instr.*` → `ext.*`，失败再回退 `coords.*`。
* 关键动作：`instr.select_option`、`instr.upload`（CDP `DOM.setFileInputFiles`）、`instr.hover`。
* 稳定等待：`instr.wait`（内部使用 `ext.wait_quiet`）比固定 `sleep_ms` 更可靠。

### 4.2 桌面（微信等，无 DOM）

* `target` 使用 `bbox_var`（由 `anchor.find`/模板识别或窗口布局预置）。
* 常用套路：`focus_app(WeChat)` → `window_bounds`→ 对**窗口内相对坐标**执行 `click_coordinates/wheel_coordinates/type_text/key_combo`。
* 识别：`anchor.find`（红点、联系人、输入框）、`ocr.recognize`（读取聊天区文本）。

---

## 5. 三个“从零到一”的示例工作流

### 5.1 Indeed：搜索 AI → 逐条点击 → 点 Apply（简版）

```json
{
  "version":"1.3",
  "start":"loop",
  "vars":{"i":0},
  "states":{
    "loop":{
      "actions":[
        { "do":"instr.scroll","target":{"css":"div.left-pane"},"dir":"down","amount":600 },
        { "do":"instr.click","target":{"css":"div.left-pane .job-card:nth-child(@i+1)"} },
        { "do":"instr.wait","ms":500 },
        { "do":"instr.click","target":{"role":"button","text":"Apply"} },
        { "do":"increment_variable","name":"i" }
      ],
      "transitions":[
        { "if":"@i < 10","go_to":"loop" },
        { "else_go_to":"done" }
      ]
    }
  }
}
```

> 生产建议：把“点第 i 个并 Apply”固化为 **Task `indeed.apply_current`**，工作流更短 & 指标可见。

### 5.2 小红书：展开评论到底并提取

```json
{
  "start":"open_comments",
  "states":{
    "open_comments":{
      "actions":[
        { "do":"instr.click","target":{"role":"button","text":"展开评论"} },
        { "do":"instr.wait","ms":400 }
      ],
      "on_success":"scroll_loop"
    },
    "scroll_loop":{
      "actions":[
        { "do":"instr.scroll","dir":"down","amount":800,"target":{"css":"div.comment-pane"} },
        { "do":"anchor.find","template":"xhs_end_marker","region":"@comment_pane_bbox","save":"end" }
      ],
      "transitions":[
        { "if":"@end != null","go_to":"extract" },
        { "else_go_to":"scroll_loop" }
      ]
    },
    "extract":{
      "actions":[
        { "do":"instr.read","target":{"css":"div.comment-pane"},"fields":["texts"],"save":"comments" },
        { "do":"instr.task_complete","message":"评论已提取" }
      ]
    }
  }
}
```

### 5.3 微信（桌面）：每 5 秒巡检新消息（LP）+ 高优先级回复（HP）

**LP 工作流（巡检）**

```json
{
  "start":"poll",
  "states":{
    "poll":{
      "actions":[
        { "do":"anchor.wait","template":"wx_red_dot","timeout_ms":10, "save":"dot" },
        { "do":"instr.click","target":{"bbox_var":"@dot"} },
        { "do":"instr.read","target":{"bbox_var":"@chat_view_bbox"},"fields":["lines"],"save":"new_msgs" },
        { "do":"queue.publish","topic":"hp-reply","json":{"user":"@current_user","msgs":"@new_msgs"} },
        { "do":"sleep_ms","value":5000 }
      ],
      "on_success":"poll"
    }
  }
}
```

**HP 工作流（回复）**

```json
{
  "start":"consume",
  "states":{
    "consume":{
      "actions":[
        { "do":"queue.consume_once","topic":"hp-reply","save":"job" },
        { "do":"task.run","name":"wechat.send_message","args":{"user_anchor":"@job.user_anchor","text":"@job.reply"} }
      ],
      "on_success":"consume"
    }
  }
}
```

---

## 6. 可靠性与安全：必须掌握的 12 条

1. **优先 Task，其次 Macro，最后才写原始 `instr.*`**。
2. **目标解析顺序固定**：`element_id → css → xpath → role+text → bbox_var`；写法明确，日志可审计。
3. **等待优先 `wait_quiet`**，减少硬等待；页面切换或大渲染后都应等待。
4. **循环要有停止条件**（计数或锚点/哨兵）；无限滚动必须设上限与异常回退。
5. **坐标动作限定窗口内**：先 `focus_app` + `window_bounds`。
6. **人类化**：坐标点击加入微抖动与最小停顿，降低风控风险。
7. **输入模式选择**：中文/长文本优先 `paste`；若页面依赖 `keyup` 事件，改用逐键 `type`。
8. **文件上传走 CDP**，对话式上传需引导用户授权。
9. **幂等**：对“发送类”动作加入 `idempotency_key`（在 Task 层实现更简单）。
10. **错误回退**：为关键操作提供后备路径（例如滚动一次重试再次点击）。
11. **变量命名规范**：计数器 `i/job_index`，中间产物 `ps/end/dot`，持久对象以 `@` 引用。
12. **越域/越窗拦截**：设置 `must_stay_in_host`（Macro/Task 约束）与窗口限定。

---

## 7. 选择器与目标定位实战建议

* **Web**：首选 `role+text`（语义稳健），其次稳定 CSS；避免动态类名与深度层级。
* **文本按钮**：`{"role":"button","text":"Apply"}`；多语言场景用 `text_any_of`（在 Task/Macro 里参数化）。
* **列表第 i 个**：`css: ".list .item:nth-child(@i+1)"`。
* **桌面**：用 `anchor.find` 标记“联系人”、“输入框”、“聊天区”基准点，保存为 `@xxx_bbox`，后续统一引用。

---

## 8. 保存数据与在流程中使用

* 多数动作支持 `save`（保存结果到 `vars`），例如：

  * `instr.read` ⇒ 文本/数组
  * `anchor.find` ⇒ `bbox`
  * `ext.get_pagestate` ⇒ 结构化 PageState（`@ps`）
* 在表达式与后续动作中用 `@var` 或 `@obj['key']` 引用。

---

## 9. 规划器（可选）：让系统“自己补动作”

* 开启方式：`"features": { "planner": { "enabled": true, "strategy": "agentq+mcts" } }`
* 提示：规划器会优先检索 **Task Catalog** 与 **Macro**；能用就用，减少 LLM“即兴发挥”。
* 调优：通过 A/B 灰度与 DPO/RLAIF 离线训练不断提升策略；异常时一键回滚旧版。

---

## 10. 调试与观测

* **本地模拟（simulate）**：在“虚拟 PageState”上跑一遍计划（不真实点击），验证流程可达性。
* **截图与日志**：为关键步骤加 `screenshot` 或在 Task/Macro 中配置保存；查看 `run_events` 时间线。
* **指标面板**：成功率、平均步数、p95 延时、Top 失败原因、LLM Token/成本。
* **异常排查**：看“目标解析链”（selector→bbox 或 bbox\_var）、等待是否足够、是否越域/越窗被拦。

> CLI 常用：
>
> * `wf lint myflow.json`（Schema/风格检查）
> * `wf simulate myflow.json --vars i=0`
> * `wf run myflow.json --device <id>`
> * `wf logs <run_id> --tail`

---

## 11. 版本化、打包与发布

* **工作流**：直接 JSON 文件，可在控制台/CLI 上传与版本化。
* **Macro**：`.wfpack.tgz`（含 YAML、资源、签名）。
* **Task**：`.taskpack.tgz`（`manifest.json + impl.yaml + anchors/`），发布到服务端，经签名与 Schema 校验后进入 **staging**；通过指标晋升 **stable**，随时可回滚。
* **依赖管理**：工作流仅引用 `task.run(name@version)` 或宏名；版本冲突由安装器解决。

---

## 12. 性能与成本优化

* **先 Task 后 LLM**：Task 内尽量不用 LLM；只有在必要时才调用（例如抽取与判别）。
* **合并读写**：一次 `instr.read` 获取完整区域文本，减少多次 DOM/截图/OCR。
* **等待合理化**：优先 `wait_quiet`，慎用长 `sleep_ms`。
* **批处理**：对列表操作优先批量（如获取一屏所有职位的 bbox 再逐个点击）。
* **缓存**：复用 `@ps`、锚点 bbox、历史成功选择器；对重复消息启用幂等缓存。

---

## 13. 安全与合规清单（作者必读）

* 仅在授权 **host** 或 **窗口** 内操作；跨站/跨窗动作会被拒绝。
* 上传文件需用户授权（CDP）并记录审计日志。
* 客户端**只走 API**；不得在工作流中写入任何直连 DB 的动作。
* 避免在工作流中硬编码敏感密钥，统一使用平台的 API Key 引用。
* 为桌面动作设置全局急停键（文档说明给用户）。

---

## 14. 迁移：从老 Schema 到新写法

* 老动作如 `ext.click_selector / type_text / scroll / wait_for` 可继续用，但**优先换成 `instr.*`**，由编译器决定 DOM/坐标。
* 老的 `on_success` 逻辑建议迁移为 `transitions`，让循环/条件更清晰。
* 复杂片段先提炼成 **Macro**，再升级成 **Task**；工作流尽量只编排 Task。

---

## 15. 模板与配方（快速复制）

### 15.1 最小工作流模板

```json
{
  "version":"1.3",
  "start":"main",
  "vars":{},
  "states":{
    "main":{
      "actions":[
        { "do":"instr.navigate", "url":"https://example.com" },
        { "do":"instr.wait","ms":800 },
        { "do":"instr.click","target":{"role":"button","text":"Sign in"} }
      ]
    }
  }
}
```

### 15.2 典型配方

* **列表遍历**：计数器 `i` + `nth-child(@i+1)` + 循环。
* **无限滚动**：`instr.scroll` + `anchor.find(底部锚点)` → 见 §3.3。
* **文件上传**：`instr.upload`；若页面弹出原生对话框，改用“引导用户手动选择 + 继续执行”的两段式。
* **桌面输入**：先 `anchor.find` 输入框 → `instr.type_text`（`paste` 模式发送中文）。
* **异步回复**：LP 工作流巡检 → 发布到 HP → HP `task.run(wechat.send_message)`。

---

## 16. 检查清单（发布前 1 分钟自检）

* [ ] 目标定位稳：`role+text` 或稳定 CSS，桌面用锚点。
* [ ] 等待充分：关键页面切换后有 `instr.wait`/`wait_quiet`。
* [ ] 循环有上限：计数或哨兵；失败有回退。
* [ ] 使用 Task：能 Task 的都 Task；宏只作小片段。
* [ ] 保存与复用：重要信息用 `save`，后续引用 `@var`。
* [ ] 安全边界：限定 host/window，上传需授权，急停键可用。
* [ ] 指标与日志：打开截图/事件；上线前跑 `simulate` + 3 次真实冒烟。
* [ ] 计费/授权：用户/设备权限正确，API Key 来源合规。

---

## 17. 常见错误与解法

* **点不中/误点**：选择器不稳 → 换 `role+text`；或启用 PageState/bbox 回退。
* **输入无效**：页面需 `keyup` → `type_text` 改逐键模式；或手动触发 `input/change`（DOM 路径自动做）。
* **滚动无效**：容器滚动与页面滚动混淆 → 指定 `target.css` 到具体容器；坐标滚动指定 `at_bbox`。
* **中文乱码**：键盘输入法干扰 → `paste` 模式。
* **OCR 识别差**：缩放/DPI 不一致 → 改为窗口内相对坐标截图，调高分辨率与字典。
* **无限循环**：缺哨兵或条件写错 → 给出最大轮次与终止条件双保险。

---

## 18. 参考附录（Schema 片段）

### 18.1 `action_instruction`（精简版）

```json
{
  "do": "instr.click",
  "target": { "css": "button.apply", "text": "Apply" },
  "save": "optional_result_var"
}
```

> 其他 `instr.*` 见“动作参考速查表”。多数动作支持顶层 `save`。

### 18.2 `task.run`

```json
{ "do":"task.run", "name":"wechat.send_message", "args":{"user_anchor":"@some_bbox","text":"你好"}, "save":"res" }
```

### 18.3 `macro.run`

```json
{ "do":"macro.run", "name":"apply_click_flow", "args":{"index_offset":"@i"} }
```

---

### 一句话总结

> **写工作流的黄金法则**：**能用 Task 就用 Task**；确有需要再落到 `instr.*`；目标定位尽量“语义化”，等待用 `wait_quiet`，循环要有哨兵；Web 用 DOM/CDP，桌面用坐标/锚点/OCR；所有写出来的内容都能被**观测、灰度、回滚**。这样你写的工作流既稳定又好维护。


# 工作流自愈与自动晋升补充文档（Addendum v1.0）

> 这份补充文档专门补齐你指出的空缺：**如何配置 `auto_promote_on_success`**、工作流自愈（AutoFixer）的**模式、阈值、风控边界**、**数据结构/接口/审计**、以及**端到端流程**。同时再次确认：**系统不会静默改你的稳定工作流**，除非你开启对应开关；默认“仅建议不改动”。

---

## 1) 核心概念回顾

* **AutoFixer（自愈）**：运行期在某个动作失败/不可达时，临时注入**补丁**（如增加 `wait_quiet`、小幅滚动再试、DOM→坐标回退）。

  * 作用域：默认**仅本次运行**（Hot Patch Session），不改变仓库中的工作流版本。
* **补丁草案（Patch Proposal）**：每次自愈会生成一份**JSON Patch**（RFC 6902）+ 证据（失败步骤、截图/日志、指纹）。
* **自动晋升（auto\_promote\_on\_success）**：当**同一补丁**在**连续/滑动窗口内**达到你设置的成功阈值，平台可自动把“原工作流 + 补丁”保存为**新版本**并标记为 `stable`（或先 `staging` 再灰度）。

---

## 2) 配置入口与优先级

有三层配置，**就近覆盖**（下方覆盖上方）：

1. **全局/租户默认**（后端 env 或租户配置）
2. **工作流级 metadata**（写在 workflow JSON 顶层）✅ *推荐*
3. **一次运行的临时覆盖**（Run Options，调试/紧急场景）

> 优先级：`运行覆盖` > `工作流级` > `租户默认`。

---

## 3) 工作流级配置（JSON 字段）

在你的 workflow JSON 顶层新增 `autofix` 区块（与 `version/start/vars/states` 同级）：

```json
{
  "version": "1.3",
  "start": "main",
  "autofix": {
    "mode": "suggest_only", 
    "promote": {
      "enabled": false,
      "strategy": "auto_promote_on_success",
      "threshold": {
        "successes": 20,
        "window": 50,
        "min_runs": 30,
        "max_error_rate": 0.05,
        "p95_latency_ms": 8000
      },
      "rollout": {
        "staging_percent": 20,
        "soak_minutes": 120
      },
      "cooldown_minutes": 30
    },
    "limits": {
      "max_patches_per_run": 2,
      "max_total_patches_per_day": 10
    },
    "allowed_patch_kinds": [
      "wait_quiet_insert",
      "scroll_then_retry",
      "selector_role_text",
      "dom_to_coords_fallback",
      "timeout_increase_small"
    ],
    "risk_gate": {
      "max_dom_change_ratio": 0.2,
      "disallow_host_widening": true,
      "disallow_upload_semantics_change": true
    }
  },
  "states": { /* ... */ }
}
```

### 字段说明

* `mode`：

  * `suggest_only`（默认）：仅生成草案，不自动应用。
  * `hot_patch_session`：允许在**当前运行**临时加补丁（会在事件日志中标注）。
  * `auto_promote_on_success`：等价于 `mode: hot_patch_session` + `promote.enabled: true`（见下）。
* `promote.enabled`：是否允许**把验证通过的补丁**自动固化为新版本。
* `promote.threshold`：自动晋升的判定阈值（成功次数、滑动窗口、允许的错误率与延迟上限）。
* `promote.rollout`：先以 `staging_percent` 灰度跑 `soak_minutes`，通过再切成 `stable`。
* `cooldown_minutes`：同一工作流两次自动晋升的冷却时间。
* `limits`：防止“补丁风暴”。
* `allowed_patch_kinds`：允许自动注入的补丁类型白名单。
* `risk_gate`：风控门（拒绝“跨域/扩大 host”、“改变上传语义”等高风险补丁）。

> **快捷方式**：你也可以直接写
>
> ```json
> "autofix": { "mode": "auto_promote_on_success" }
> ```
>
> 平台会使用租户默认阈值（见 §4）。

---

## 4) 租户默认与后端环境变量

后端支持以环境变量/租户配置设置默认值：

```
AUTOFIX_DEFAULT_MODE=suggest_only
AUTOFIX_PROMOTE_ENABLED=false
AUTOFIX_THRESHOLD_SUCCESSES=20
AUTOFIX_THRESHOLD_WINDOW=50
AUTOFIX_THRESHOLD_MIN_RUNS=30
AUTOFIX_THRESHOLD_MAX_ERROR_RATE=0.05
AUTOFIX_THRESHOLD_P95_MS=8000
AUTOFIX_ROLLOUT_STAGING_PERCENT=20
AUTOFIX_ROLLOUT_SOAK_MIN=120
AUTOFIX_MAX_PATCHES_PER_RUN=2
AUTOFIX_MAX_PATCHES_PER_DAY=10
AUTOFIX_ALLOWED_KINDS=wait_quiet_insert,scroll_then_retry,selector_role_text,dom_to_coords_fallback,timeout_increase_small
```

> 工作流级配置若存在，将覆写这些默认。

---

## 5) 运行级覆盖（可选）

在触发一次运行时可以附带临时参数（仅对本次 run 生效）：

```json
POST /workflow/run
{
  "workflow_id": 123,
  "vars": { ... },
  "run_options": {
    "autofix": {
      "mode": "hot_patch_session",
      "limits": { "max_patches_per_run": 1 }
    }
  }
}
```

---

## 6) 补丁对象与数据模型

### 6.1 JSON Patch（摘要）

```json
{
  "patch_id": "wf-789:sha1:ab12...",
  "workflow_id": 789,
  "base_version": "1.2.3",
  "kind": "wait_quiet_insert",
  "reason": "click timeout on Apply; page not settled",
  "json_patch": [
    { "op": "add", "path": "/states/loop/actions/2", "value": { "do":"instr.wait", "ms": 500 } }
  ],
  "evidence": {
    "run_id": 556677,
    "state": "loop",
    "action_index": 2,
    "screens": ["s3://.../before.png","s3://.../after.png"],
    "logs_ref": "..."
  },
  "risk_score": 0.12
}
```

### 6.2 表与 API（工作流维度）

* 表：

  * `workflows(id, name, latest_version, owner, ...)`
  * `workflow_versions(workflow_id, version, status, doc, created_by, ...)`
  * `workflow_patches(patch_id, workflow_id, base_version, json_patch, kind, risk_score, status, proposer, created_at)`
  * `workflow_patch_stats(patch_id, day, runs, success, p95_ms)`
* API：

  * `POST /workflows/patches/propose`（系统/人工）
  * `POST /workflows/patches/apply`（仅 hot session）
  * `GET  /workflows/patches/list?workflow_id=`
  * `POST /workflows/promote`（把 base+patch 合并生成新版本 → staging/stable）
  * `POST /workflows/rollback`

---
详情见 workflowupgrade.md