# 系统说明文档（v1.0）

**项目代号：yolo+llm 自动化平台**
**定位：** 用统一的“指令集（Action Space）+ 规划器（Planner/AgentQ+MCTS）+ 执行后端（Web DOM/CDP 与 桌面坐标/OCR）+ 记忆学习（RAG/Reflexion/DPO）”，驱动 Web 与桌面应用的端到端自动化。
**目标：** 低代码可编排、可扩展、可观测、可回滚、可计费；支持**宏（Macro）→任务（Task）→工作流（Workflow）**“搭积木”。

---

## 1. 体系全览

### 1.1 分层架构

* **LLM 层（大脑）**

  * Planner：AgentQ 候选 + MCTS 搜索与模拟（simulate/rollout），自我反思（Reflexion）。
  * Memory：RAG 轨迹检索（Plans History/Skills/Tasks），在线反思，离线 DPO/RLAIF 迭代。
* **语义指令层（语言）**

  * `instr.*` 统一动作空间（12–14 个动词）：click/type/scroll/…
  * LLM 仅输出 `instr.*`（或 `task.run`），不直接接触底层复杂度。
* **编译层（翻译）**

  * 目标解析（`element_id|css|xpath|role+text|bbox_var`）→ DOM/CDP 或 坐标 bbox。
  * 回退策略：DOM 失败时退到坐标链路（pyautogui）。
* **执行层（手）**

  * Web：`ext.*`（Chrome 扩展 + CDP），可靠触发页面事件。
  * 桌面：`coords.*`（pyautogui）、`anchor.*`（模板/文本锚点）、本地 OCR（Paddle/Tesseract）。
* **编排层**

  * Workflow JSON（状态机 + 条件/循环 + 优先级/异步队列）。
  * Task（可复用、带 I/O 与重试/SLO）与 Macro（动作片段）。
* **平台层**

  * 市场：Macro/Task 上架/安装/签名/灰度/回滚。
  * 计费与授权：登录→设备识别码→套餐权限；API Key 管理（可选明文可见）。
  * 观测与运维：事件日志、指标、AB 实验、回退开关。
  * 队列：SQS（生产）/LocalStack（本地），高优先级优先调度。

---

## 2. 关键能力与设计原则

* **统一动作空间**：LLM 只学 12–14 条 `instr.*` 指令，减少动作熵，提高泛化。
* **DOM→坐标回退**：优先 DOM/CDP 精确事件；失败时用坐标（抗动态 ID、适配桌面 App）。
* **任务积木**：高频微流程沉淀成 Task；Task 组合成 Workflow，降低重复劳动和出错率。
* **可学习闭环**：Plans History → 偏好对 → Prompt 调优 / LoRA+DPO；Teacher 打分（RLAIF）可选。
* **严格安全**：客户端不直连 DB；动作白名单；域名/窗口边界；可急停；API Key 管理受控。
* **异步优先级**：收消息（低优先）与回消息（高优先）拆分为两条工作流；SQS 多队列抢占。

---

## 3. Action Space v2（语义指令集）

### 3.1 对 LLM 暴露的 12–14 个指令

`instr.click` / `instr.type_text` / `instr.select_option` / `instr.scroll` /
`instr.navigate` / `instr.history` / `instr.hover` / `instr.key` / `instr.upload` /
`instr.read` / `instr.wait` / `instr.task_complete` / `instr.answer_user` / `instr.annotate(可选)`

**Target 统一格式：**

```json
{ "element_id":"...", "css":"...", "xpath":"...", "role":"button", "text":"Apply", "bbox_var":"@chat_input_bbox" }
```

**解析顺序：** element\_id → css → xpath → role+text → bbox\_var（坐标回退）。

### 3.2 执行原语（引擎内部 \~30 个）

* Web DOM/CDP：`ext.open_url/history/wait_quiet/click_selector/type_text/scroll/key/select_option/hover/upload_file/extract/get_pagestate`
* 坐标/桌面：`click_coordinates/wheel_coordinates/mouse_move_coordinates/type_text/key_combo/screenshot/focus_app/window_bounds`
* OCR/锚点：`ocr.recognize/anchor.find/anchor.wait`
* 数据/控制：`set_variable/increment_variable/get_list_length/get_list_item/query_data`
* 规划/记忆：`llm.plan/plan.simulate/plan.execute/mem.recall/plan.reflect/macro.run`
* 队列/I-O：`queue.publish/queue.consume_once/http.post|get/storage.write_json(可选)`

**映射关系：** 编译器把 `instr.*` 落到 `ext.*` 或 `coords.*`，并保留安全检查与来源审计。

---

## 4. Workflow / Macro / Task

### 4.1 Workflow JSON（状态机）

* 字段：`version/start/vars/states`
* `state.actions`：动作数组（可混用 `instr.*`、`task.run`、老动作）。
* `state.transitions`：`[{ "if": "<表达式>", "go_to": "state" }, { "else_go_to": "state" }]`
* 支持循环与条件（不再局限 `on_success`）。
* 支持高优先级中断：HP 队列有任务时，当前状态结束后先执行 HP。

**循环示例（Indeed 左列逐条应聘）**

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

### 4.2 Macro（技能）

* 定义：MicroPlan 片段 + 参数化 + 约束（`must_stay_in_host/no_dom_click/max_steps`）。
* 发布/安装：`.wfpack.tgz` 包，签名校验；服务端管理版本与灰度。
* 运行：`macro.run(name,args)` → 展开为步骤执行；来源/白名单严格校验。
* 挖掘：PrefixSpan/FP-growth 从成功轨迹中发现高频子序列，自动生成候选宏。

### 4.3 Task（积木）

* 定义：带 `inputs/outputs`、`pre/postconditions`、`policy(retries/idempotency/max_runtime)`、`impl(macro|steps)`。
* 打包：`.taskpack.tgz`，签名；安装到设备。
* 运行：`task.run(name,args,version?)`；写入 `task_runs` 和指标；支持幂等与重试。
* 晋升：staging → stable → locked（自动/人工，根据成功率、时延、故障阈值）。
* Planner/MCTS 优先使用 Task；缺少 Task 时才回落到 `instr.*`。

**Task 示例：微信发消息**

```json
{
  "name":"wechat.send_message","version":"1.0.0",
  "inputs":{"user_anchor":{"type":"string"},"text":{"type":"string"}},
  "preconditions":["app:WeChat.front","anchor:chat_input_ready"],
  "postconditions":["ocr:chat_view_contains(@text)"],
  "policy":{"retries":1,"idempotency_key":"wx:send:@text:@user_anchor","max_runtime_ms":8000},
  "impl":{"steps":[
    {"do":"instr.click","target":{"bbox_var":"@user_anchor"}},
    {"do":"instr.type_text","target":{"bbox_var":"@chat_input_bbox"},"text":"@text"},
    {"do":"instr.key","key":"Enter"},
    {"do":"instr.wait","ms":300}
  ]}
}
```

---

## 5. 规划与学习（AgentQ + MCTS + RAG + Reflexion + DPO/RLAIF）

### 5.1 在线规划

* **候选生成（AgentQ）**：从 Macro/Task/历史成功片段召回，结合 `instr.*` 生成若干候选计划。
* **MCTS**：在虚拟 PageState 上模拟（click/scroll/等待可达性与代价），选最优路径；失败回退策略。
* **Reflexion**：每次失败或低奖励，写入短评（错误模式/修复建议），参与下次候选排序。

### 5.2 离线学习

* **数据**：从 `plans_history/plan_candidates/plan_reflections` 构造“偏好对”（preferred>rejected）。
* **Prompt 调优**：快速路线，自动选择最优提示模板。
* **DPO+LoRA（策略微调）**：用偏好对训练轻量 Planner 头；输出受严格 Schema 校验。
* **RLAIF（Teacher）**：缺人类偏好时，用更强 LLM 打分生成偏好；仅在“难站点/高失败指纹”上启用。
* **灰度与回退**：`planner_versions + ab_assignments` 按 host/策略上线；异常阈值自动回滚。

---

## 6. 异步与优先级（SQS / LocalStack）

* **队列设计**：

  * `hp-reply`（高优先）：如“收到 LLM 回复 → 立即发给微信联系人”。
  * `lp-ingest`（低优先）：如“每 5 秒查新消息 → 上报给后端/LLM”。
* **本地开发**：LocalStack 模拟 SQS；生产用 AWS SQS。
* **调度**：引擎在状态边界检查 HP 队列，存在时**优先抢占**；保证“先回复，再巡检”。
* **幂等**：消息附带 `idempotency_key`；消费者端去重。
* **错误**：重试/死信队列（DLQ），可视化告警。

---

## 7. 浏览器扩展与桌面后端

### 7.1 Chrome 扩展（Web 执行）

* 能力：`ext.resolve/ click/ type_text/ select_option/ hover/ key/ open_url/ history/ scroll/ upload_file/ extract/ wait_quiet/ get_pagestate`。
* 上传文件：CDP `DOM.setFileInputFiles`（需授权）。
* 解析：`element_id/css/xpath/role+text` → DOM 节点 + 屏幕 bbox + 稳定 selector；失败回退坐标。
* 安全：只允许白名单事件；跨域拦截；DOM 事件派发合规。

### 7.2 桌面执行（WeChat/非 DOM）

* 原语：`click_coordinates/mouse_move/wheel/type_text/key_combo/screenshot/focus_app/window_bounds`。
* 锚点：`anchor.find/anchor.wait`（模板图或文字）；多 DPI/暗黑模式资源。
* OCR：本地运行（无需云费用），中文友好。
* 安全：限定窗口矩形内动作；全局热键急停；权限（macOS 辅助功能/Win 管理员）。

---

## 8. 安全、权限与合规

* **边界与来源校验**：

  * DOM：动作仅在 `must_stay_in_host`；参数来源必须是 `@ps` 或前序 `save`。
  * 桌面：限定到目标进程窗口内；坐标加微抖动和人类化最小停顿。
* **API 与数据**：

  * 客户端**只调用 API**（HTTPS），**不直连 Postgres**。
  * 审计日志：动作、来源（selector/bbox）、耗时、结果、错误。
* **API Key 管理**：

  * 支持明文存储（便于后台可见）或加密存储（推荐）；可按用户/工作流设置 Key；
  * Key 使用范围/配额/吊销；调用时统一走平台代理。
* **签名与上架**：Macro/Task 包签名校验；安装/升级/回滚全链路可追溯。
* **急停与防滥用**：全局热键；速率限制；域名单与黑名单；敏感指令需 Capability 开关。

---

## 9. 计费与授权

* 登录 → 设备识别码（机器码） → 套餐授权（设备数/并发/可用工作流/可用 Task）。
* 支持“付费下载任务/工作流”，可暂停/停止/继续。
* 统一计量：动作次数、Task 执行、LLM token 消耗、运行时长；账单导出。

---

## 10. 数据模型（核心表）

> 客户端不直连，以下通过 API 服务访问。

* **任务与版本**：`tasks(name, latest_version)`；`task_versions(task_id, version, status, manifest, pack_url, signature, ...)`
* **安装与运行**：`task_installations(user_id,device_id,task_id,version,enabled)`；`task_runs(..., ok, steps, reward, error, meta)`；`task_stats_daily`
* **技能（宏）**：`skills(name, version, host, params, constraints, microplan, status, signature)`；`skill_stats_daily`
* **规划器**：`planner_versions(type: prompt|lora, file_url, base_provider)`；`ab_assignments(host,strategy,planner_version_id,traffic_pct)`
* **历史与反思**：`plans_history` / `plan_candidates` / `plan_reflections`
* **Teacher 评分**：`teacher_judgments(context, candidates, scores, rationale)`
* **设备与权限**：`devices(user_id, device_id, status, quota)`；`entitlements(user_id, plan, features)`
* **API Key**：`api_keys(user_id, name, value(可明文或加密), scopes, created_at, revoked_at)`

---

## 11. API（选摘）

* **任务流转**

  * `POST /tasks/publish`（上传 `.taskpack.tgz`，签名+Schema 校验）
  * `POST /tasks/promote` / `POST /tasks/rollback`
  * `GET /tasks/list?host=&app=` / `POST /tasks/install`
  * `POST /task/run`（记录/授权入口；或仅 `/events` 上报运行结果）

* **技能（宏）**

  * `POST /skills/publish` / `GET /skills/list` / `POST /skills/install`

* **规划器**

  * `POST /deploy/planner`（发布 prompt/lora）
  * `POST /deploy/ab`（灰度配置）
  * `POST /teacher/score`（RLAIF 打分）

* **密钥**

  * `POST /apikeys/create` / `GET /apikeys/list` / `POST /apikeys/revoke`（支持明文可见选项）

---

## 12. 典型流程

### 12.1 Indeed 应聘（DOM→坐标）

1. 打开列表页 → `instr.scroll` 左栏 → `instr.click` 第 i 个 → `instr.wait` → `instr.click` Apply。
2. 使用 Task：`indeed.apply_current(i)` 循环 10 次；失败则 fallback：`wheel_coordinates` & `click_coordinates`。

### 12.2 小红书评论采集（循环/无限下拉）

1. 搜索页逐卡片进入 → 评论区展开（重复点击“展开”）→ 无限下拉直到锚点出现 → `instr.read` 提取 → 发 LLM 识别优质评论 ID → 保存。

### 12.3 微信自动回复（桌面/高优先）

* 低优先工作流：每 5 秒巡检红点（`anchor.wait` 非阻塞）→ 读取新消息上报队列。
* 高优先工作流：消费 LLM 回复 → `wechat.send_message` 发送（Task），完成后回到巡检。

---

## 13. 部署与开发环境

* **服务端**：Node/Express（或你现有框架）+ Postgres + 对象存储（S3/MinIO）+ 队列（SQS）。
* **客户端**：Python 运行器（pyautogui/OCR/anchor）+ Chrome 扩展。
* **本地开发**：Docker Compose（API/PG/LocalStack/MinIO），扩展热重载，OCR 本地模型缓存。
* **配置**：Feature Flags（`features.tasks.enabled`、`features.tasks.use_in_planner` 等）。
* **监控**：Grafana/Prometheus（或你已有），触发回退的阈值规则（失败率、延迟、LLM 成本）。

---

## 14. 测试策略与验收

* **单元**：Schema 校验、参数绑定、目标解析、白名单/来源校验、回退路径。
* **集成**：`publish→install→run→stats` 链路；宏→Task 迁移工具；Planner AB 路由。
* **E2E**：Indeed/小红书/微信各 ≥20 回合；

  * 成功率 ≥ 基线；
  * 平均步数持平或下降；
  * Token/时间成本可控；
  * 无越权与安全回归。
* **回退**：Planner/Task/Skill 任一版本异常，5–15 分钟窗口内自动回滚；人工一键回滚。

---

## 15. 安全与风险应对

* **越域/越窗拦截**：所有动作强制域名/窗口边界；上传/敏感操作需显式授权。
* **人类化策略**：鼠标抖动+最小停顿，降低被风控识别的概率。
* **失败自愈**：Reflexion 快速纠错，RAG 召回成功策略；HP 抢占保证“先回消息”。
* **成本控制**：Teacher 打分限流；DPO 离线夜间训练；Planner 灰度与阈值回退。

---

## 16. 快速上手（Checklist）

1. **开发环境起服务**：Postgres/S3(Local)/SQS(LocalStack)/API。
2. **安装扩展与客户端**：开启桌面辅助权限（macOS/Win）。
3. **发布首个 Macro**：`apply_click_flow`；**发布首个 Task**：`indeed.apply_current`。
4. **写 Workflow**：循环 10 次 apply（示例见 §4.1）。
5. **上线 Planner（Prompt 版）**：10–20% 灰度；监控失败率/成本；异常回退。
6. **桌面微信**：安装锚点资源，跑 `wechat.send_message`；接入 HP/LP 队列。
7. **计费**：创建账号→设备识别码→安装可用 Task；验证授权生效。
8. **观测**：控制台查看 Task/Macro/Workflow 指标；拉取日志排查。

---

## 17. FAQ（摘选）

* **Q：微信/桌面没有 DOM 怎么办？**
  A：统一用 `instr.*`；编译器把 target 的 `bbox_var` 映射到 `coords.*`，配合 `anchor.*` 与本地 OCR 识别。

* **Q：页面元素 ID 老变？**
  A：`role+text/css` 优先解析；解析失败回退坐标；Planner 有“滚动→点击→等待静默”的稳定模板。

* **Q：如何“自动学习变好”？**
  A：运行数据→偏好对→Prompt/DPO；RAG 召回历史成功轨迹；Reflexion 抑制已知错误模式。

* **Q：API Key 能在后台看明文吗？**
  A：支持两种模式（明文可见/加密存储）；可按租户策略选择，敏感场景建议加密。

* **Q：客户端能连数据库吗？**
  A：不能。严格走 API，所有写入（运行/指标/安装）都通过后端。

---

## 18. 附：关键 Schema 片段

### 18.1 `instr.*`（动作）

```json
{
  "do":"instr.click",
  "target":{"css":"button.apply","text":"Apply"}
}
```

（详见：`instruction_target` 与 `action_instruction` 定义，包含 `type_text/scroll/...`）

### 18.2 Task（manifest.json）

```json
{
  "name":"wechat.send_message","version":"1.0.0",
  "inputs":{"user_anchor":{"type":"string"},"text":{"type":"string"}},
  "preconditions":["app:WeChat.front","anchor:chat_input_ready"],
  "postconditions":["ocr:chat_view_contains(@text)"],
  "policy":{"retries":1,"idempotency_key":"wx:send:@text:@user_anchor","max_runtime_ms":8000},
  "impl":{"steps":[ ... ]}
}
```

### 18.3 宏（YAML）

```yaml
name: apply_click_flow
version: 1.0.0
host: ca.indeed.com
constraints: { must_stay_in_host: indeed.com, no_dom_click: true, max_steps: 5 }
microplan:
  steps:
    - { do: wheel_coordinates, args: { at_bbox: "@ps.panes.left.rect", amount: -600 } }
    - { do: click_coordinates, args: { bbox: "@ps.lists[0].itemRects[@i]" } }
    - { do: wait_for, args: { until: { type: "ext.wait_quiet", timeout_ms: 6000 } } }
    - { do: ext.extract, args: { mode: "find_button_bbox", text_any_of: ["Apply","Quick Apply"] } }
    - { do: click_coordinates, args: { bbox: "@last_found_bbox" } }
```

---

\*\*至此，本说明文档覆盖：\*\*架构、动作空间、编译与执行、Macro/Task/Workflow、Planner/MCTS/记忆学习、异步优先级队列、安全与计费、API/数据模型、扩展与桌面后端、典型用例、部署测试与运维策略。
如果你希望，我可以把这份文档拆成「开发者手册」「运维手册」「工作流作者指南」三份更细的版本，并附上 ER 图与 Swagger。
