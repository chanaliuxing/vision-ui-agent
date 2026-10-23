我给你一份“可直接落地”的**小模块（Workflow Authoring Module，WAM）**说明与样例代码，专门帮你把任务拆解成**可循环、可验证、符合 JSON Schema** 的工作流；同时讲清楚**自愈/自动更新**机制到底怎么生效、有哪些开关。

---

# 目标与范围

* 面向“具体任务”的本地小模块，**可选调用 LLM 做拆解**，但核心是**结构化建模**（循环/条件/变量/优先级）。
* 产出就是**合法的 Workflow JSON**（符合你提供的 schema，支持 `instr.* / task.run / macro.run / transitions`）。
* 自带**静态校验**（Schema + 语义规则）、**动态仿真**（simulate）、**防无限循环**（哨兵上限/超时）。
* 支持**两类典型循环**：

  * 列表遍历（Indeed 左列职位→右栏 Apply）
  * 时间轮询（微信 5 秒红点检查/第一个会话固定位置）

---

# 模块设计（WAM）

## 1) 组成

1. **Builder（构建器）**：Python 小库，提供链式 API/DSL（也支持纯 JSON）。
2. **Validator（校验器）**：集成 `jsonschema` + 语义规则（必有终止条件、变量引用存在、状态可达）。
3. **Simulator（仿真器）**：在虚拟 PageState 上“干跑”（不真实点击），验证 transitions 与循环收敛。
4. **Decomposer（可选 LLM 拆解）**：把“自然语言任务”->“Task+instr 计划”，但**生成后仍经 Builder 约束与校验**。
5. **AutoFixer（自愈/自动更新）**：运行期发现失败→插入“等待/回滚/滚动/改 selector”的**临时补丁**；同时生成**补丁草案**供人审/或自动晋升（按开关）。

> 你可以把 WAM 放在 `tools/wam/`，供本地脚本、CI、以及控制台编辑器后端共用。

---

## 2) Builder API（最小但够用）

### Python 伪代码（可直接按这个骨架落地）

```python
from typing import Dict, List, Any, Optional

class WF:
    def __init__(self, version="1.3"):
        self.doc = {"version": version, "start": None, "vars": {}, "states": {}}

    def start(self, state: str):
        self.doc["start"] = state; return self

    def set_var(self, k: str, v: Any):
        self.doc["vars"][k] = v; return self

    def state(self, name: str, actions: List[Dict], transitions: Optional[List[Dict]]=None, on_success: Optional[str]=None):
        s = {"actions": actions}
        if transitions: s["transitions"] = transitions
        if on_success: s["on_success"] = on_success
        self.doc["states"][name] = s; return self

    # 快捷：for 循环骨架（计数器 i 从 0..count-1）
    def for_range(self, name: str, counter: str, count_expr: str, body_actions: List[Dict], next_state: str="done"):
        loop = f"{name}_loop"
        self.set_var(counter, 0)
        self.state(loop, actions=body_actions + [
            { "do": "increment_variable", "name": counter }
        ], transitions=[
            { "if": f"@{counter} < {count_expr}", "go_to": loop },
            { "else_go_to": next_state }
        ])
        if not self.doc["start"]: self.start(loop)
        return self

    # 快捷：轮询骨架（每 period_ms 检查一次；带 HP 抢占钩子）
    def poll(self, name: str, period_ms: int, actions: List[Dict]):
        self.state(name, actions=actions + [
            { "do":"sleep_ms", "value": period_ms }
        ], on_success=name)
        if not self.doc["start"]: self.start(name)
        return self

    def build(self) -> Dict: return self.doc
```

> 这层只管**结构正确**；动作细节仍用你现有的 `instr.* / task.run`。

---

## 3) Validator（双层校验）

* **Schema 校验**：用你提供的 workflow schema（Draft-07）跑 `jsonschema`。
* **语义校验**（至少包含）：

  * `start` 必在 `states` 中；每个 `state.actions` 非空。
  * `transitions` 至少有一路可到达（无死结）。
  * 所有 `@var` 都在 `vars` 或前序 `save` 中出现。
  * **循环必须有终止条件**：

    * `for_range` 默认有 `i < count`；
    * `while`/轮询必须有**上限或哨兵**（如“出现 end\_marker”或最大轮次/超时）。
  * 高优/低优工作流互不阻塞（HP 消费一步一个消息，防止饿死）。

> 建议：`wam.validate(workflow)` 同时跑 schema 与语义；不通过就拒绝导出。

---

## 4) Simulator（动态仿真 · 可选强烈推荐）

* 输入：Workflow JSON + 虚拟 PageState（左栏 items=10，按钮“Apply”存在；或微信窗口锚点存在）。
* 规则：对 `instr.click/scroll/wait/read` 等在**虚拟环境**评估是否可达/是否需要额外等待/滚动。
* 产出：

  * 最短步数/可能路径
  * “潜在无限循环”预警（例如哨兵永远不出现）
  * 建议补丁（例如“加一条 `instr.wait` 或 `instr.scroll` 重试一次”）

---

# 两个典型任务怎么写

## A. Indeed：从上到下循环申请（不依赖稳定 ID）

**人话需求 → 结构拆解**

1. 左栏职位列表从上到下点击第 i 个 → 右栏详情更新
2. 点击“Apply”或“Quick Apply”
3. 循环 10 次

**优先用 Task（更稳）**：`indeed.apply_current(i)`

* 工作流只剩一个 `for_range` 循环 + `task.run`。

**用 WAM 构建器（示例）**

```python
wf = WF().for_range(
  name="apply",
  counter="i",
  count_expr="10",
  body_actions=[
    { "do":"task.run", "name":"indeed.apply_current", "args":{"i":"@i"}, "save":"r" }
  ],
  next_state="done"
).build()
```

**如果暂时没有 Task，用 `instr.*` 也能写：**

```python
wf = WF().for_range(
  name="apply",
  counter="i",
  count_expr="10",
  body_actions=[
    { "do":"instr.scroll", "target":{"css":"div.left-pane"}, "dir":"down", "amount": 600 },
    { "do":"instr.click",  "target":{"css":"div.left-pane .job-card:nth-child(@i+1)"} },
    { "do":"instr.wait",   "ms": 500 },
    { "do":"instr.click",  "target":{"role":"button","text":"Apply"} }
  ],
  next_state="done"
).build()
```

**WAM 帮你自动做的：**

* 给 `i` 置初值 0，保证 `@i` 存在。
* 自动生成 `transitions`（`@i < 10` 回环，否则 `done`）。
* 校验“Apply 按钮”在虚拟环境可达（Simulator 可选）。
* 通过 Schema 与语义检查。

---

## B. 微信：每 5 秒检测红点 & 回复（固定位置框架）

**人话需求 → 结构拆解**

* 红点出现在联系人列表固定处；新消息会话固定在列表第一项；输入框位置不变。
* 低优先（LP）：每 5 秒检查红点 → 读取最新消息 → 丢到 HP 队列。
* 高优先（HP）：从队列取 LLM 回复 → 找到会话 → 输入/发送。

**LP 工作流（WAM 的 poll）**

```python
wf = WF().poll(
  name="poll_new_msgs",
  period_ms=5000,
  actions=[
    { "do":"anchor.find", "template":"wx_red_dot", "region":"@wx_sidebar_bbox", "save":"dot" },
    { "do":"instr.click", "target":{"bbox_var":"@dot"} },
    { "do":"instr.read",  "target":{"bbox_var":"@chat_view_bbox"}, "fields":["lines"], "save":"msgs" },
    { "do":"queue.publish", "topic":"hp-reply", "json":{"user_anchor":"@contact_anchor","msgs":"@msgs"} }
  ]
).build()
```

**HP 工作流（WAM 的 poll + 高优队列）**

```python
hp = WF().poll(
  name="reply_once",
  period_ms=0,
  actions=[
    { "do":"queue.consume_once", "topic":"hp-reply", "save":"job" },
    { "do":"task.run", "name":"wechat.send_message",
      "args":{"user_anchor":"@job.user_anchor","text":"@job.reply"} }
  ]
).build()
```

**WAM 自动保障：**

* `poll` 生成自循环，加入 `sleep_ms`，不阻塞主线程。
* 可配置“HP 抢占”：执行引擎在状态边界优先处理 HP。
* 变量存在性检查：`@chat_view_bbox/@contact_anchor` 必须由上游初始化或锚点扫描提供。
* 可选仿真：如果 `wx_red_dot` 锚点不存在，Simulator 会给“弱失败”并建议增加 `anchor.wait` 超时或扩大 `region`。

---

# 如何保证“写出来就符合 JSON Schema & 流程正常”

1. **WAM Builder** 统一生成结构：

   * `start` 自动设置
   * `states[*].actions` 非空保障
   * `transitions` 由高阶构造（`for_range/poll`）自动生成
2. **Schema 校验**：引入你的 Draft-07 schema 作为**硬校验**（类型、字段、`oneOf`）。
3. **语义校验**：

   * 变量引用存在性（`@var` 必须已定义/保存）
   * 循环终止性（必须有上限或哨兵/超时）
   * 状态图强连通/可达性（无悬空状态）
4. **Simulator 干跑**（推荐在 CI 上跑）：

   * 用站点/应用的**虚拟 PageState**（或最近一次真实运行记录）测试可达性
   * 给出“补丁建议”与“风险评级”，例如：需要 `instr.wait`、需要 `instr.scroll` 重试
5. **一键修复（可选）**：WAM expose `apply_patch()` 把建议插入到合适动作前后，再跑一遍校验。

---

# “系统会自动更新 workflow 吗？”

**会，但分两层控制**，默认“**自愈只针对当前运行**，版本更新走**提案→晋升**”。

### A. 运行期自愈（AutoFixer）

* 触发：点击失败/目标解析失败/可达性差。
* 策略（按优先级）：

  1. 自动插入 `instr.wait` / `ext.wait_quiet`
  2. 自动 `instr.scroll` 小步试探再点
  3. 目标解析回退（DOM→坐标）
  4. 退回上一状态（有限次）
* 作用域：**仅本次运行的临时补丁**；不会直接修改存量 Workflow。

### B. 补丁草案 & 自动晋升（可配）

* 每次自愈会生成**补丁 Diff**（含原因、前后对比、风控评分）。
* 三种模式（由平台设置或 workflow metadata 控制）：

  1. `suggest_only`（默认）：只生成草案，需人工审核→生成新版本（staging）。
  2. `auto_promote_on_success`：同一补丁**连续 N 次成功**（默认 N=20）后，自动把补丁工作流**晋升为 stable**。
  3. `hot_patch_session`：仅对运行中的会话热补（紧急），不留存版本。
* 所有变更都有**审计与回滚**（上一版本 stable 随时一键回退）。

> 换句话说：**不会“静默改你的稳定工作流”**，除非你显式开启 `auto_promote_on_success` 或选了“热补会话”。这兼顾稳定与自我修复。

---

# 常用片段速查

* **读取并保存数据**

  ```json
  { "do":"instr.read", "target":{"css":"div.comment-pane"}, "fields":["texts"], "save":"comments" }
  ```
* **循环控制（for 10 次）**

  ```json
  { "do":"increment_variable", "name":"i" }
  // transitions:  { "if":"@i < 10", "go_to":"loop" }
  ```
* **轮询（每 5 秒）**

  ```json
  { "do":"sleep_ms", "value": 5000 }  // WAM.poll 自动插入
  ```
* **异步优先**

  * 巡检→`queue.publish hp-reply`
  * 回复→独立 HP workflow `queue.consume_once hp-reply` + `wechat.send_message`

---

# 最后：落地步骤（最短路径）

1. 把上面的 **WF/Builder** 和 **Validator** 放进仓库 `tools/wam/`。
2. 接入你的 **workflow\.json schema** 做 `wam.validate()`。
3. 写两个模板函数：

   * `build_indeed_loop(count=10)`（优先 `task.run(indeed.apply_current)`）
   * `build_wechat_poll_reply()`（LP/HP 各一份）
4. 在 CI 里加两步：`wam.validate` + `wam.simulate`（用虚拟 PageState）。
5. 在运行器里打开 **AutoFixer**（默认 suggest\_only），把补丁发到“提案箱”。

这样，你就有了一个**面向具体任务的“小模块”**：

* 写起来像“搭积木”，天然符合 JSON Schema；
* 对循环和轮询有**模板与哨兵**；
* 出问题先自愈、再产出补丁；
* 是否自动更新，由你**一键配置**。


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

## 7) 自动晋升算法（伪代码）

```python
def maybe_auto_promote(workflow_id, patch_sig):
    cfg = load_effective_autofix_cfg(workflow_id)
    if cfg.mode not in ("auto_promote_on_success",) or not cfg.promote.enabled:
        return

    stats = get_patch_stats(patch_sig, window=cfg.promote.threshold.window)
    if stats.runs < max(cfg.promote.threshold.min_runs, cfg.promote.threshold.successes):
        return
    if stats.successes < cfg.promote.threshold.successes: return
    if stats.error_rate > cfg.promote.threshold.max_error_rate: return
    if stats.p95_ms     > cfg.promote.threshold.p95_latency_ms: return
    if now - last_promotion(workflow_id) < cfg.promote.cooldown_minutes: return

    # 生成新版本
    new_doc = apply_json_patch(base_doc(workflow_id), patch_json(patch_sig))
    v = bump_version(base_version, policy="minor")     # eg. 1.2.3 -> 1.3.0
    create_workflow_version(workflow_id, v, new_doc, status="staging")

    # 灰度
    set_rollout(workflow_id, v, percent=cfg.promote.rollout.staging_percent)
    wait(cfg.promote.rollout.soak_minutes)
    if metrics_ok(workflow_id, v):
        promote_to_stable(workflow_id, v)
        emit_event("autofix.promoted", {...})
    else:
        rollback(workflow_id, base_version)
        emit_event("autofix.rollback", {...})
```

---

## 8) 补丁类型（allowed\_patch\_kinds）详解

| kind                     | 说明                                                | 典型 JSON Patch                                              |
| ------------------------ | ------------------------------------------------- | ---------------------------------------------------------- |
| `wait_quiet_insert`      | 在关键点击/导航前后插入 `instr.wait`（或内部映射 `ext.wait_quiet`） | `add /states/.../actions/N { "do":"instr.wait","ms":400 }` |
| `scroll_then_retry`      | 轻微滚动后重试一次点击                                       | `add` 一个 `instr.scroll` + 重试 `instr.click`                 |
| `selector_role_text`     | 把不稳定的 ID 选择器替换为 `role+text`                       | `replace` 目标 `target.css/xpath` → `target.role/text`       |
| `dom_to_coords_fallback` | DOM 失败回退到坐标点击（配合保存的 bbox）                         | `add` `target.bbox_var` 并调整编译策略                            |
| `timeout_increase_small` | 小幅上调 `timeout_ms`，不超过上限                           | `replace` `wait_for.timeout_ms` → `+300..800`              |

> **风险门**默认会禁止：跨站域、放宽上传动作、扩大执行窗口边界这类“高影响”补丁。

---

## 9) 端到端工作流（以 Indeed 为例）

1. 原始工作流：点击“Apply”前未等待 → 部分运行失败。
2. AutoFixer 检测到 `click` 前页面未稳定 → 自动注入 `wait_quiet_insert`（仅会话内）。
3. 同一补丁在 50 次窗口内成功 ≥ 20 次、错误率 <5%、p95 < 8s → 触发自动晋升：

   * 生成 `1.3.0-staging`，以 20% 流量跑 120 分钟；
   * 指标 OK → 标记为 `stable`；
   * 写入审计日志并通知（Slack/Email）。
4. 如灰度期间退化 → 一键回滚至 `1.2.3`，补丁状态标成 `rejected`。

---

## 10) UI / CLI / API 操作指南

### 10.1 工作流 JSON 中直接配置

```json
"autofix": { "mode": "auto_promote_on_success",
             "promote": { "enabled": true, "threshold": { "successes": 15, "window": 40 } } }
```

### 10.2 控制台（建议）

* 工作流详情 → “自愈与晋升”面板：

  * 模式选择（单选）：仅建议 / 会话热补 / 自动晋升
  * 阈值（数字输入，带安全提示）
  * 补丁白名单（多选 CheckBox）
  * 风险门（开关）
  * 实时补丁候选列表（每条都可“查看 JSON Patch / 运行证据 / 一键采纳为新版本”）

### 10.3 CLI

```
wf autofix set <workflow> --mode auto_promote_on_success \
  --successes 20 --window 50 --min-runs 30 --p95-ms 8000 \
  --kinds wait_quiet_insert,scroll_then_retry,selector_role_text
wf autofix status <workflow>
wf patch list <workflow>
wf patch adopt <patch_id> --as-version 1.3.0
```

### 10.4 API（选摘）

* `POST /workflows/settings/autofix`（设定工作流级自愈策略）
* `GET  /workflows/patches/list?workflow_id=...`
* `POST /workflows/promote` / `POST /workflows/rollback`

---

## 11) 审计与事件

平台会写入如下事件（可在控制台 Timeline 查看）：

* `autofix.proposed`（生成补丁草案）
* `autofix.applied_session`（本次运行临时应用）
* `autofix.promoted`（生成新版本并灰度/稳定）
* `autofix.rolled_back`（灰度失败回退）
* `autofix.rejected`（人工拒绝/风控拦截）

每条包含：工作流 ID/版本、补丁签名、原因、证据链接、触发者（系统/用户）、指标快照。

---

## 12) 安全与合规边界（再次强调）

* **默认不自动修改稳定工作流**：除非你在工作流或租户层**显式开启** `auto_promote_on_success` 或在运行级开启 `hot_patch_session`。
* 自动晋升仅允许**白名单补丁**；严禁扩大作用域（host/window）、更改上传/下载语义、注入任意新动作。
* 每次晋升都可**快速回滚**；并有**审计记录**与**通知**。

---

## 13) 示例：把微信巡检工作流开启自动晋升

```json
{
  "version": "1.1",
  "start": "poll",
  "autofix": {
    "mode": "auto_promote_on_success",
    "promote": {
      "enabled": true,
      "threshold": { "successes": 30, "window": 80, "p95_latency_ms": 5000 }
    },
    "allowed_patch_kinds": ["wait_quiet_insert","timeout_increase_small"],
    "risk_gate": { "disallow_host_widening": true }
  },
  "states": { /* poll 循环略 */ }
}
```

* 如果 AutoFixer 发现“读取聊天区前偶尔 OCR 失败”，会提议在截图前插入 `instr.wait 200ms`。
* 满足阈值后自动产出 `1.2.0-staging → stable`，你也可在控制台查看/一键回滚。

---

## 14) 回答你的确认问题

> **“我们设计的系统会自动更新 workflow 如果中间出现问题对吗？”**
> **是，但可控。**

* 默认**不会**自动更新，只会**给出补丁建议**；
* 若你在 **工作流/租户/运行层**开启 `auto_promote_on_success`（或 `hot_patch_session`），系统会：

  1. 在当前运行**临时自愈**；
  2. 达到你设置的阈值后，**自动产出新版本**并按灰度策略晋升为 `stable`；
  3. 全程有**审计与回滚**，且受**补丁白名单与风控门**约束。

