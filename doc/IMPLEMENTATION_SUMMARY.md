# Summary View + 落地清单（可直接派工）

本文按主题列出当前状态（Implemented｜Partial｜Missing）＋文件定位＋差距说明＋落地任务（函数/消息/参数级别，无代码）＋完成定义（DoD）。

---

## Entities & IDs

- 状态: Partial → MVP (headers on signals)
- 已有/文件:
  - `getcontent/extension/sw/bootstrap.js`: 扩展存储 `device_id/sid/account_id`；LOGIN 到 8787（API_BASE 探测、签名校验）。
  - `getcontent/backend/orchestrator.js`: 生成 `run_id`、创建 per-run steps，查询 `/runs/:runId`。
- 差距:
  - 上下行消息未统一携带 `{user_id, device_id, tab_id, run_id, step_id}`。
  - `step_id/exec_id` 未全链路约束；幂等未落地。
- 落地任务:
  - 统一消息头: 定义 `MsgHeader={user_id, device_id, tab_id, run_id, step_id, ts}`；扩展 SW/Orchestrator/Engine 所有事件/命令统一携带。
  - 步序与幂等: Engine 侧 `next_step_id()` + 生成 `exec_id(UUID)`；Orchestrator `seen_exec(exec_id)->bool` 幂等返回；Extension `onAction(exec_id)` 缓存并复用结果。
- DoD:
  - 任意抓包一条事件/命令，均含完整 `MsgHeader`。
  - 重放同一 `exec_id` 3 次，扩展/Orchestrator 返回一致结果且不重复入队。

- 本次交付（MVP）:
  - 扩展 SW: `PAGE_STABLE` 及 webNavigation 信号附带 `{ device_id, tab_id, ts }`。
  - Orchestrator: `/page_stable` 接受并记录上述 `header`；保持稳定窗口逻辑。
  - Engine: `autostep` 生成 `exec_id=UUIDv4` 并写入等待日志（`wait_ext_page_stable`）。
  - 后续：将 `exec_id` 贯穿所有 `autostep_*` 日志与 WS 通道的 action/action_result。

---

## Extension ↔ Orchestrator Channel

- 状态: Partial（WS MVP added）；HTTP 已 Implemented
- 已有/文件:
  - Orchestrator HTTP: `/runs/start`、`/runs/:runId`、`/artifacts/save_text`、`/commands/next`、`/commands/ack`、`/health`（`getcontent/backend/orchestrator.js`）。
  - 扩展目前使用 `runtime.sendMessage` 与 `fetch`（`sw/bootstrap.js`、`cs/actions.js`）。
- 差距:
  - 无 WS 注册/心跳/按 tab 的推送队列；扩展端无 WS 客户端。
- 落地任务:
  - WS 消息协议:
    - [已完成] `register(device_id, tab_id, ua) -> {ok}`
    - [已完成] `heartbeat(ts) -> {ok}`（15s）
    - [已完成] 上行 `page_event{header, url, route_change, ready}`（MVP）
    - [待办] 下行 `action{header, exec_id, action:"ext.*", args}` / 上行 `action_result{...}` / 上行 `extract_result{...}`
  - 路由与队列:
    - [已完成] `ConnRegistry`: `(device_id, tab_id) -> ws`
    - [待办] `CommandQueue`: 分桶 `bucket=(user_id?, device_id, tab_id)`；推送与回传。
  - HTTP 兼容层（可选）: 保留现有 HTTP 作为降级。
- DoD:
  - [已达成] 扩展成功通过 WS `register/heartbeat`；Orchestrator 接收 `page_event`。
  - [下一步] 按 tab 精确下发 `action` 并收到 `action_result`。

---

## Page Stability Signals（事件驱动等待）

- 状态: Implemented (MVP)
- 已有/文件:
  - Orchestrator: `GET/POST /page_stable`（已加到 `getcontent/backend/orchestrator.js`）。
  - Engine: `core/workflow.py` 等待 `ext_page_stable`（成功时写 success 日志）。
  - Extension: `sw/bootstrap.js` 用 `webNavigation.onCompleted` POST `/page_stable`。
- 补充说明（MVP 完成）:
  - 已覆盖 SPA 路由（SW: `onHistoryStateUpdated`；CS: `popstate/hashchange` + `MutationObserver` 静默检测）。
  - Engine 等待已严格：`wait_for` 超时抛错置失败；并新增别名 `ext.wait_quiet`。
- 落地任务:
  - 扩展 SW/CS 信号增强:
    - 监听 `onHistoryStateUpdated/popstate/hashchange` → `route_change=true`。
    - CS 侧使用 `MutationObserver` + `PerformanceObserver` 判断 `dom_idle/net_idle`。
    - 统一上报 `page_event{header, url, route_change, ready, signals{net_idle, dom_idle, dom_hash, title}}`。
  - Engine 严格等待:
    - `wait type="ext.wait_quiet"`（映射 `ext_page_stable`）超时→`step_failed`；进入 `R-POP`。
    - 点击后短等待 `verify.rules=["page_change","disappear:loading"]`。
- DoD（达成，PNA: net-idle 后续）:
  - SPA 场景路由切换后可在 1~1.5s 内收到 `ready=true`（基于 DOM 静默）。
  - 超时等待将 step 标记失败并终止当前状态（恢复策略后续接入）。

---

## DOM Extract & Actions（Content Scripts）

- 状态: Partial → MVP（标准化 `ext.*` 已落地子集）
- 已有/文件:
  - `getcontent/extension/cs/actions.js`: `DOM_WAIT_FOR`、`DOM_TYPE`、`DOM_CLICK`、`DOM_OPEN_NTH`、`DOM_SCRAPE_COMMENTS`、`SAVE_TEXT`、`SIM_CLICK` 等。
- 差距:
  - 缺统一 `ext.*` API 命名与入参/出参；缺标准化抽取结构。
  - 页面内截图 `ext.screenshot` 缺失（当前由 Engine 桌面截图）。
- 落地任务:
  - 标准动作族（`ext.*`）:
    - [已完成] `ext.wait_quiet(timeout_ms)`（DOM 静默）
    - [已完成] `ext.extract(want, limit=400)`（MVP：basic DOM snapshot + meta）
    - [已完成] `ext.click_selector(sel)`、`ext.type_text(sel,text,replace)`、`ext.key(key)`、`ext.scroll(dir,amount)`
    - [待办] `ext.get_coords(sel)`、`ext.screenshot(mode)`（截图后补）
  - 抽取结构（MVP）：
    - `dom={vw, vh, dpr, items:[{id, sel, role, text, href?, bbox, region, visible, z}], meta:{url,title}}`
    - `want` 场景：`"topbar+search_box"|"post_cards"|"comments_with_reply_btn"|"default"`
    - `comments` 结构：`comments[{id,user,text,time,replyBtnSel,bbox?}]`
  - 截图（后补）: `ext.screenshot("viewport")`。
- DoD（部分达成）:
  - Engine 可使用 `wait_for: {type: "ext.wait_quiet"}` 进行严格等待。
  - `ext.extract` 提供基础 DOM 结构；后续按站点 adapter 丰富化。

---

## Engine (Python)

- 状态: Implemented/Partial 混合
- 已有/文件:
  - `core/workflow.py`: Runner、YOLO+LLM、unified picker、LLM router（cost guard）、部分 Outcome 验证、`ext_page_stable` 等待。
- 差距:
  - Outcome Verifier 未按严格 JSON 契约；R-POP 未按标准化输出；`executor="dom|dom+coords|vision"` 未统一对外。
  - `wait_ext` 超时未置失败。
- 落地任务:
  - 统一执行器语义：
    - `ext.wait_quiet / ext.extract / ext.click_selector / ext.type_text / ext.key / ext.scroll / ext.screenshot`
    - `pick+click(executor="dom"|"dom+coords"|"vision", hint, strategy="adapter_first_then_llm")`
  - Outcome Verifier：
    - 入参：`{task, phase, state, goal, action_summary, expect_page, history_summary} + image`
    - 出参：`{ok, state:"home|search_results|post_detail|other", reason:"<=32", confidence}`
  - R-POP：
    - 入参：`{task, expect_page, last_action, error, history, page_brief, image}`
    - 出参：`{decision, steps:[{action,target,why}], success_signature[], notes}`
    - 执行：`patch_queue` 插队、`step_overrides` 回退覆盖、`reset_to_start`
  - 严格失败：`ext.wait_quiet` 超时→`step_failed`；点击后 `verify.rules` 短等待。
- DoD:
  - 导航/提交步统一通过 Verifier 校验；失败自动触发 R-POP 并可修复继续。
  - `executor` 三通道可用（DOM 优先，视觉兜底）。

---

## Orchestrator (8788)

- 状态: Implemented/Partial 混合
- 已有/文件:
  - `/runs/start`、`/runs/:runId`、`/artifacts/save_text`、`/commands/next`、`/commands/ack`、`/health`；`/page_stable`（非 run-scoped）。
- 差距:
  - 无 WS 服务/注册/心跳；无 per-tab bucket 队列；`/page_stable` 未带 run/step。
- 落地任务:
  - WS 服务：
    - `/ws`: `register/heartbeat/action` 下发/`action_result`/`page_event`/`extract_result`。
    - `ConnRegistry/CommandQueue`（按 `(user_id, device_id, tab_id)` 分桶）。
  - Run 绑定与队列：
    - `startRun` 绑定 `run_id→tab_id`；`awaitActionResult(exec_id, timeout_ms)`。
  - `page_stable` run-scope：
    - 改为 WS `page_event`（带 `{run_id, step_id}`）；Orchestrator 标记并唤醒对应等待。
- DoD:
  - 扩展通过 WS 与 Orchestrator 通讯；`page_event` 仅影响对应 run/step。

---

## Multi-User Binding & Isolation

- 状态: Missing/Partial
- 已有/文件:
  - 扩展 LOGIN/JWT（`bootstrap.js`）；签名验证存在（`verifyEnvelope`）。
- 差距:
  - 消息未统一携带完整 IDs；无 per-tab 队列与硬隔离。
- 落地任务:
  - 统一消息头（见 Entities & IDs）。
  - Orchestrator 分桶路由；端点校验 `MsgHeader` 与连接上下文一致。
- DoD:
  - 多用户/多标签并发（≥50 并发 run）不串台。

---

## Site Adapter

- 状态: Missing
- 落地任务:
  - 新增 `adapters/xhs.yaml`：
    - `stability_profile.ready`；`page_signatures{home,search_results,post_detail}`
    - `selectors{search_input, post_cards, comment_item, comment_user, comment_text, comment_reply_btn}`
    - `behaviors.reply_flow{open.click, type.sel, send.sel}`
  - Engine 在 `ext.extract(want)` 时优先使用 adapter；缺省走通用规则。
- DoD:
  - 有/无 adapter 两种路径可跑；有 adapter 时点击/抽取更稳定。

---

## Reliability & Observability

- 状态: Partial
- 已有/文件:
  - Engine: `out/logs/steps_log.jsonl`、LLM req/resp（已加 state 命名）。
  - Orchestrator: DB 持久 run/steps、`/artifacts/save_text`。
- 差距:
  - 无统一事件时间线；无 `exec_id` 幂等；无重试/DLQ。
- 落地任务:
  - 统一事件：
    - `step_begin/step_end`、`page_event`、`action_dispatch/action_result`、`verify_outcome_ok/fail`、`recovery_plan/used`、`step_gate_failed/wrong_page_guard/ocr_fallback_used`
    - 事件结构：`MsgHeader + type + payload`；写入 DB(`events`) 与文件（按 run 目录）。
  - 重试与 DLQ：
    - Orchestrator：`ack_timeout_ms`，重试 N 次，入 `dlq_commands`。
    - Engine：LLM 路由与指数退避；超限降级规则/adapter。
  - 指标与 SLO：
    - Prometheus 指标；目标：`wait_quiet P95 < 1.5s`；`LLM ≤ 8s`；成功率 `>95%`。
- DoD:
  - 单个 run 可回放全程；故障场景幂等/不丢命令。

---

## Security

- 状态: Partial/Implemented 混合
- 已有/文件:
  - 扩展 manifest 最小 Host 权限；计划 envelope 验签（扩展 SW）。
  - Engine 危险词 OCR 预检。
- 差距:
  - 人工制品 PII 脱敏缺失；计划签名未贯穿 orchestrator→extension。
- 落地任务:
  - `/artifacts/*` 入库前脱敏（邮箱/手机号等）。
  - 敏感动作签名链：8787 签→ orchestrator 验→ extension 二次验（发布/删除/支付需 `allow_dangerous=true`）。
- DoD:
  - 抽样 artifacts 无原始 PII；未签动作被拒绝。

- 本次交付（MVP）:
  - Orchestrator `/artifacts/save_text` 已加入基础 PII 脱敏（邮箱/手机号）。

---

## 测试矩阵（必须）

- 功能: 搜索→点帖→抓评→LLM 过滤→回复（DOM 执行）；导航失败触发 R-POP 并恢复。
- 并发: 5 用户 × 3 tab × 3 run 并发不串台。
- 降级: 禁用 LLM → adapter/规则通；禁用 adapter → 通用+视觉兜底。
- 反检测: 目标站检测 `isTrusted` 时切换 `executor="dom+coords"` 成功点击。
- 稳定性: SPA 跳转 100 次，`wait_quiet` P95 < 1.5s。

---

### 说明
本清单可直接拆解为任务单，分别派给 Extension / Orchestrator / Engine / Platform 团队并行实现，保持消息契约与数据结构一致，逐里程碑交付。
