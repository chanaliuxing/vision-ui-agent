我给你一份\*\*「升级版 v2 规划 + 执行落地计划」**。它把我们刚才讨论的所有要点逐条纳入，并加上生产化/规模化所需的硬化项。结尾附**逐项对照检查清单（No-Omission Checklist）\*\*，确保零遗漏。

---

# 0) 升级目标（在你现有系统之上）

1. **稳定性与规模化**：更强的容错、人类化、幂等、优先级调度（HP/LP）、重试/熔断、灰度发布。
2. **Planner→Executor 强化**：白名单、来源校验、回合式短计划、失败快退、注入防护与内容安全。
3. **动作体系插件化 GA**：签名、权限声明、热加载、版本回滚、市场上架/购买/安装全闭环。
4. **跨聊天客户端适配**：在 WeChat 基础上，抽象成 Chat Adapter，可扩到飞书/企微/Telegram/WhatsApp 桌面端等。
5. **DOMRect→坐标点击链路 GA**：`click_coordinates` / `wheel_coordinates` 完整人类化与可见性判断、滚动容器对齐。
6. **LLM 路由与成本控制**：`llm.submit/plan` 策略化、BYOK 明文可视（管理员）+ 审计、用量计费/限额。
7. **可观测与回放 v2**：事件→时间线→快照→诊断包；SLA/告警/积压仪表盘。
8. **安全与合规**：密钥可视审计、数据脱敏、HITL 批准流、最小权限、插件沙箱。
9. **DevEx**：CLI、VSCode/Schema 补全、录制/回放、E2E & Chaos、基准评测（BrowserGym/WebArena/OSWorld）。
10. **向后兼容**：旧 JSON 工作流零修改可跑，新特性 opt-in。

---

# 1) 版本与范围

* 引擎 Schema 升级：**v1.1 → v1.2**（向后兼容）。
* 桌面客户端、浏览器扩展、服务端（API/Worker/市场/计费/密钥）均小步快跑、灰度上线。
* 金路径：**WeChat 自动回复**、**Indeed AI 搜索坐标申请**、**小红书逐帖互动** 进入 GA 水平。

---

# 2) v1.2 Schema 小升级（兼容）

新增（仅列关键）：

* 顶层：`"features": { "planner": true, "humanize": { "mouse": true, "typing": true } }`（可开关）
* 动作级额外元数据：`"guard": { "allowlist": [...], "source_vars_only": true }`
* `plan.execute` 支持：`"policy":{"max_steps":N,"max_runtime_ms":M,"per_step_timeout_ms":K,"deny":[...],"allow":[...]}`
* 事件标签：任意动作可带 `"trace_tag":"<string>"` 便于回放筛选

> 注：不破坏你 v1.1 的 JSON；老工作流不用改。

---

# 3) 工作流运行时（客户端）升级项

* **表达式引擎**加速与防注入（仅允许 `@vars`/字面量/算子；拒绝任意代码）。
* **重试/熔断**：指数退避、按动作粒度覆盖；状态级超时触发 `on_error`。
* **人类化执行**：鼠标曲线（贝塞尔/噪声）、随机停顿、误触纠正、前台焦点检测失败→`PAUSE`；键入节流与纠错重打。
* **幂等与资源锁**：`meta.resource_lock` 实施加锁；`idempotency_key` 贯穿 HP/LP。
* **断点恢复**：本地轻量快照（变量 + 执行指针），崩溃重启可接续。
* **录制/回放**：低帧率快照（默认 2 FPS）+ run\_events；一键导出诊断包。

---

# 4) 动作体系（插件化 GA）

* **插件包（.wfpack.tgz）**：`plugin.yaml`（权限/域名白名单/需要的能力）、`actions.py/js`（带 JSON Schema）。
* **签名与校验**：ed25519；安装必验签；控制台可回滚版本。
* **热加载**：无需重启客户端；失败自动回滚上个稳定版本。
* **核心动作**：

  * 坐标：`click_coordinates`、`wheel_coordinates`（DPR/窗口度量换算，容器内滚动）
  * 队列：`mq.consume/ack/publish`（FIFO + DLQ）
  * OCR：`ocr.run(roi,lang,psm,cache)`（客户端本地）
  * 聊天：`chat.*` 适配层（WeChat/可扩充），统一 `find_unread/open/capture/focus/send`
  * 计划：`llm.plan`（服务端）+ `plan.execute`（客户端，白名单/来源校验）

---

# 5) 浏览器扩展（只读 RPC）

* `getPageState()`：URL、DPR、windowMetrics、左/右容器 rect、可见控件、列表 itemRects、哨兵标记。
* `findButtons({textAnyOf})` / `getRects({selectors})`：仅返回 DOMRect，不执行点击。
* **安全**：域名白名单、最小权限、脱敏；内容仅用于定位，不采集隐私数据。

---

# 6) LLM 服务与成本控制

* **`llm.submit`**：PromptPack/Schema 路由、用量记账、幂等、结果投放 HP 队列（需要发送/提交的）。
* **`llm.plan`**：MicroPlanV1（≤5 步），白名单动作；拒绝生成不允许动作或越权参数。
* **AUTO 路由**：控制器类→Claude 3.5；视觉确认类→GPT-4o；可 `FORCE:<provider>` 覆盖。
* **BYOK 明文可视**（管理员）：PLAINTEXT/ENCRYPTED 二态，查看必须写审计（IP/时间/人）。
* **限额**：用户/工作流/设备维度配额与限流；超限降级到更便宜模型或排队。

---

# 7) SQS 编排（HP/LP）

* **Topics**：

  * `llm.request.fifo`（LP→Worker）
  * `device.{device_id}.{app}.hp.fifo`（Worker→HP）
  * `events.*`（可选外部消费）
* **属性**：FIFO + `MessageGroupId=device_id`；`visibility_timeout`、DLQ、重试策略。
* **优先**：调度器永远先 HP 后 LP；`resource_lock` 保证 UI 独占。

---

# 8) 可观测/回放 v2

* **run\_events**：动作开始/结束/耗时/变量摘要；`trace_tag` 聚合串联；错误堆栈。
* **快照**：S3/MinIO；默认脱敏（姓名/手机号/二维码等遮盖）。
* **Web 回放**：时间线、事件过滤、关键帧跳转、变量视图、重定位“卡点”。
* **SLA/告警**：SQS 积压、失败率、LLM 错误率、成本异常；PagerDuty/飞书通知。

---

# 9) 安全与合规

* **Planner 白名单**：`allow/deny` 强约束；任何 bbox/rect 必须来源于当前 `PageState` 或上一步结果。
* **HITL**：高风险动作（支付/删除）需要人工确认；可配策略。
* **最小权限**：插件/扩展声明 capability 与 host；客户端沙箱执行。
* **审计**：密钥查看/导出、安装/回滚、HITL 通过全部写审计表。
* **数据保留**：可观测数据 TTL 与脱敏策略；用户可删除导出。

---

# 10) DevEx & 测试

* **CLI**：`wf run/validate/migrate/pack/install/replay`；
* **VSCode**：v1.2 Schema 绑定、自动补全、片段库；
* **基准评测**：接入 BrowserGym/WebArena/OSWorld（回归指标：成功率/平均步数/平均时延）。
* **E2E & Chaos**：焦点丢失、黑屏、OCR 噪声、SQS 延迟、网络波动。
* **Mock 套件**：Fake WeChat/Indeed/XHS 页面；Mock LLM/OCR。

---

# 11) 执行落地计划,这里是概述，后面会有详细落地方案（按 Sprint，均为**可见成功**里程碑）

### Sprint A（2 周）：引擎与坐标链路 GA

* v1.2 Schema 支持（features/guard/trace\_tag）；
* `click_coordinates/wheel_coordinates` 人类化 + 容器可见性判断；
* 承压测试（多屏/缩放）；
* **验收**：Indeed 坐标申请在 100/125/150% 缩放 & 双屏稳定；失败跳过不断流。

### Sprint B（2 周）：插件化 GA + 市场最小闭环

* 插件签名/权限声明、热加载、回滚；
* `.wfpack.tgz` 打包/安装；工作流上架/购买/安装；
* **验收**：从市场安装 “Indeed 坐标点击” 后无需重启即可运行。

### Sprint C（2 周）：Planner→Executor 强化

* `llm.plan`（MicroPlanV1）+ `plan.execute` 白名单/来源校验/逐步刷新 `PageState`；
* 失败快退/短计划回合（≤5 步）；
* **验收**：Planner 自动决策「滚动→点击→等待→找 Apply→点击」≥90% 成功率。

### Sprint D（2 周）：LLM 成本与密钥治理

* `llm.submit`/`llm.plan` 计量/限额；AUTO 路由策略表；
* PLAINTEXT Key 可视 + 审计；
* **验收**：限额触发降级；管理员查看 Key 有审计记录。

### Sprint E（2 周）：SQS 编排与 HP/LP 强化

* FIFO/DLQ/重试/幂等；优先级调度；
* **验收**：微信 LP→HP 闭环在拥塞时仍优先发送；DLQ 无堆积。

### Sprint F（2 周）：可观测/回放 v2

* run\_events + 快照脱敏 + Web 回放 UI；
* SLA 仪表盘 + 告警；
* **验收**：一次失败能在回放中定位“哪一步/哪张图/哪个变量”，告警触发正确。

### Sprint G（2 周）：多客户端聊天适配 & HITL

* Chat Adapter 接口稳定；引入至少一个新客户端（如企微/飞书/Telegram 桌面）最小支持；
* HITL 审批流；
* **验收**：同一工作流切换适配器仍可跑；高风险路径走人工批准。

> 说明：可并行推进，但每个 Sprint 都有产线可演示的“看得见的成功”。

---

# 12) 金路径 GA 验收标准（硬指标）

* **WeChat 自动回复**：
  成功率 ≥ 98%，消息重复发送率 ≤ 0.5%，HP 响应 p95 ≤ 3s。
* **Indeed 坐标申请**：
  连续处理 20 条职位无人工干预成功率 ≥ 90%；平均步数 ≤ 人类 1.4×；
  站点结构变动 1 次内可通过插件热修 < 24h 恢复。
* **小红书逐帖互动**：
  到底哨兵识别准确率 ≥ 98%；评论成功率 ≥ 95%。

---

# 13) 风险清单与对策（摘要）

| 风险         | 对策                            |
| ---------- | ----------------------------- |
| 页面结构突变     | 选择器候选阵列 + Planner 兜底 + 插件热修灰度 |
| 反自动化检测     | 人类化轨迹/节流/随机化；速率限制；夜间限流        |
| 多屏/缩放偏移    | DPR/窗口换算统一；校准向导               |
| LLM 成本波动   | 幂等去重、缓存、AUTO 路由便宜模型、限额        |
| Planner 误操 | 白名单/来源校验/步数与时长上限/HITL         |
| 隐私与密钥泄露    | 脱敏、最小权限、PLAINTEXT 查看强审计、密钥轮换  |
| 积压与雪崩      | SQS 可视化积压、DLQ 告警、速率自适应        |

---

# 14) 迁移与兼容

* 旧工作流（v1.1/更早）零改动即可运行；
* 提供 `wf-migrate` 脚本将旧 JSON 加注 `features/guard/trace_tag`（可选）；
* 插件体系与市场为**增量**，不影响现存执行链路。

---

# 15) 交付清单（落地完成需具备）

* **代码/服务**：升级后的客户端/扩展/服务端/Worker、CLI、Schema v1.2。
* **文档**：开发者指南、Plugin SDK、PromptPack 规范、市场/计费/密钥治理、回放与诊断。
* **示例**：三条金路径 v1.2 工作流；`llm.plan`/`plan.execute` 样例；插件示例（坐标/滚动/按钮定位）。
* **测试**：E2E 套件 + Chaos；BrowserGym/WebArena/OSWorld 对接脚本与周报模板。
* **运维**：SLA 仪表盘、告警规则、应急预案（回滚/限流/停机保护）。

---

## No-Omission Checklist（逐条核对）

**从我们所有对话与你历史需求汇总：**

* [x] 变量/循环/条件转场（已落地，v1.2 兼容并优化）
* [x] DOMRect→屏幕坐标点击、`click_coordinates`、`wheel_coordinates`、容器滚动可见性判断
* [x] 仅用坐标完成 Indeed 左列→右详情→Apply（不依赖 DOM 点击）
* [x] Planner→Executor（`llm.plan`+`plan.execute`），白名单与来源校验、短计划回合、失败快退
* [x] Chrome 扩展回传 PageState（只读：rects/DPR/windowMetrics/控件/哨兵）
* [x] 本地 OCR（客户端内置，ROI/缓存）
* [x] HP/LP 双工作流，SQS（线上）/LocalStack（本地），FIFO/幂等/优先级
* [x] Chat Adapter（WeChat 已有，接口可扩展其它桌面聊天工具）
* [x] LLM 路由（AUTO/FORCE）、PromptPack/Schema、计量与限额、幂等
* [x] 明文 API Key 可视（管理员），强审计（查看/导出）
* [x] 市场/插件化动作：签名、权限、热加载、上架/购买/安装/回滚
* [x] 可观测/回放：run\_events、快照（脱敏）、时间线与诊断包
* [x] 人类化与反检测：轨迹/节流/随机化/焦点守护
* [x] 安全与合规：最小权限、HITL、高风险动作策略、数据保留与脱敏
* [x] DevEx：CLI、VSCode/Schema、录制/回放工具
* [x] 测试 & 基准：E2E、Chaos、BrowserGym/WebArena/OSWorld
* [x] 迁移/兼容：旧工作流可跑、可选迁移脚本

---
Sprint A：
这里是\*\*Sprint A（引擎与坐标链路 GA）\*\*的即刻可执行落地包：目标、交付物、实施步骤、代码骨架、测试与验收、回滚与风控，全都按“现在就能干”的粒度列好。照着清单分工即可开工。

---

# 1) Sprint A 目标（2 周内完成）

* 升级工作流 **Schema v1.2**（兼容 v1.1），新增：

  * 顶层 `features`（开关 Planner/Humanize 等）
  * 动作级 `guard`（allow/deny 白名单、`source_vars_only`）
  * 任意动作 `trace_tag`（便于回放筛选）
* 客户端实现并 GA：

  * `click_coordinates`：DOMRect→屏幕坐标转换 + 人类化鼠标移动/点击 + 多屏/缩放校准
  * `wheel_coordinates`：在容器中心滚轮（解决独立滚动容器）
  * **容器可见性判断**：判断列表项是否在容器可视区 → 滚动带入可视再点
* 基于上述能力，跑通 **Indeed「AI 搜索 → 左列逐条（坐标）点 → 右栏稳定」**（无需 DOM 点击）
* 在 **100%/125%/150%** 缩放 & **单双显示器** 场景下稳定

---

# 2) 交付物（Definition of Done）

1. `workflow.schema.v1_2.json`（向后兼容）并接入 VSCode 自动补全与 CI 校验
2. 客户端模块：

   * `humanize/mouse.py`（贝塞尔轨迹+抖动+停顿）
   * `geom/coords.py`（DPR/窗口度量换算，多屏支持）
   * `actions/click_coordinates.py`
   * `actions/wheel_coordinates.py`
   * `visibility/viewport.py`（容器可见性判断）
   * `tools/calibrate.py`（坐标校准与可视化）
3. 示例工作流：`examples/indeed_coords_apply.wf.json`（可跑）
4. 自动化测试：

   * 单元：换算/可见性/人类化不变式
   * 集成：本地伪页面（左列/右详情）+ 实机交互冒烟清单
5. 文档与 Runbook：使用方法、常见偏移排查、回滚步骤
6. 验收报告：在 3 种缩放 × 2 种显示器矩阵下的通过记录与日志

---

# 3) 目录与仓库变更（增量）

```
repo/
├─ schema/
│  ├─ workflow.schema.v1_1.json
│  └─ workflow.schema.v1_2.json       # 新增
├─ runtime/
│  ├─ engine/
│  │  ├─ evaluator.py                 # 表达式引擎（强化：仅白名单语法）
│  │  └─ runner.py                    # 读取 features/guard/trace_tag
│  ├─ actions/
│  │  ├─ click_coordinates.py         # 新增
│  │  ├─ wheel_coordinates.py         # 新增
│  │  └─ __init__.py
│  ├─ humanize/
│  │  ├─ mouse.py                     # 新增
│  │  └─ typing.py
│  ├─ geom/
│  │  └─ coords.py                    # 新增（DPR & 多屏）
│  ├─ visibility/
│  │  └─ viewport.py                  # 新增
│  └─ tools/
│     └─ calibrate.py                 # 新增（标定）
├─ extension/
│  └─ content/                        # getPageState 已有；确保返回 DPR/metrics
├─ examples/
│  └─ indeed_coords_apply.wf.json     # 新增样例
├─ tests/
│  ├─ unit/
│  │  ├─ test_coords.py
│  │  ├─ test_visibility.py
│  │  └─ test_humanize.py
│  ├─ integration/
│  │  └─ test_indeed_coords.py
│  └─ fixtures/
│     └─ mock_pagestate.json
└─ Makefile
```

---

# 4) Schema v1.2（与 v1.1 的增量）

把下面片段合入你现有 `v1_1`，保持向后兼容：

```json
{
  "properties": {
    "features": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "planner": { "type": "boolean", "default": false },
        "humanize": {
          "type": "object",
          "properties": {
            "mouse": { "type": "boolean", "default": true },
            "typing": { "type": "boolean", "default": true }
          }
        }
      }
    }
  },
  "$defs": {
    "common_action": {
      "properties": {
        "trace_tag": { "type": "string" },
        "guard": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "allowlist": { "type": "array", "items": { "type": "string" } },
            "denylist":  { "type": "array", "items": { "type": "string" } },
            "source_vars_only": { "type": "boolean", "default": false }
          }
        }
      }
    }
  }
}
```

> 引擎处理：若 `guard.source_vars_only=true`，动作参数中出现任何**非当前变量/上一步结果**的坐标/矩形，一律拒绝。

---

# 5) 关键实现（核心代码思路）

## 5.1 DOMRect→屏幕坐标换算（多屏/缩放）

* 输入：`rect`（viewport/CSS px）、`metrics`：`{ dpr, screenX, screenY, outerHeight, innerHeight, monitor_id }`
* 计算内容区域左上角（考虑浏览器工具栏高度）
* **多屏**：通过 OS API 获取当前浏览器窗口所在屏的原点与缩放；必要时做 `monitor_offsets[monitor_id]` 叠加

伪代码：

```python
def rect_center_to_screen_xy(rect, metrics, os_monitors):
    # rect: {x,y,width,height} in CSS px (viewport)
    # metrics: from extension; os_monitors: list with per-monitor offset/scale
    content_x = metrics['screenX']
    toolbar_h = metrics['outerHeight'] - metrics['innerHeight']
    content_y = metrics['screenY'] + toolbar_h

    cx = rect['x'] + rect['width'] / 2.0
    cy = rect['y'] + rect['height'] / 2.0

    # per-monitor offset
    mon = os_monitors.by_id(metrics.get('monitor_id', 0))
    px = int((content_x + cx) * metrics['dpr'] + mon.offset_x)
    py = int((content_y + cy) * metrics['dpr'] + mon.offset_y)
    return px, py
```

## 5.2 人类化鼠标

* 贝塞尔曲线（起/终点+两个控制点）+ 速度分布（先快后慢）
* 抖动：±1～2px 微扰；每 200–400ms 随机 dwell 10–30ms
* 防抖：移动后等待 `5–12ms` 再点击；可选 “双击确认”

接口：

```python
def human_move_and_click(x, y, button='left'):
    path = bezier_path(current_pos(), (x,y))
    for pt in path:
        move_mouse(pt, jitter=1)  # ±1 px
        sleep(rand(6, 14) / 1000)
    sleep(rand(8, 20) / 1000)
    click_mouse(button)
```

## 5.3 `click_coordinates` 动作

* 入参：`bbox`（DOMRect 或屏幕坐标），允许 `trace_tag`、`guard`
* 流程：解析 → 校验来源（`guard.source_vars_only`）→ 换算 → humanize → 事件记录
* 失败重试：`retry` 指数退避（已在 v1.1 支持）

## 5.4 `wheel_coordinates` 动作

* 入参：`at_bbox`（容器 DOMRect），`amount`（正上负下）
* 流程：取容器中心 → humanize.move → 滚轮 `amount`
* 用于「左列独立滚动容器」

## 5.5 容器可见性判断

```python
def is_visible_in_container(item, pane, margin=6):
    top_in = item['y'] >= (pane['y'] + margin)
    bot_in = (item['y'] + item['height']) <= (pane['y'] + pane['height'] - margin)
    return top_in and bot_in

def bring_item_into_view(item, pane):
    if item['y'] < pane['y']:
        wheel_coordinates(pane, amount=+600)   # 向上滚
    elif (item['y'] + item['height']) > (pane['y'] + pane['height']):
        wheel_coordinates(pane, amount=-600)   # 向下滚
```

## 5.6 标定工具 `tools/calibrate.py`

* 展示十字准星 → 点击两点 → 回读屏幕点、扩展返回的 rect，对齐误差
* 输出当前机器的偏移/比例修正（写入本地 profile）

---

# 6) 示例工作流（可直接跑）

`examples/indeed_coords_apply.wf.json`（节选关键 states）：

```json
{
  "version": "1.2",
  "features": { "humanize": { "mouse": true, "typing": true } },
  "start": "open",
  "states": {
    "open": { "...": "（与之前一致，打开 Indeed 搜索 ai）", "on_success": "harvest" },

    "harvest": {
      "actions": [
        { "do": "ext.extract",
          "args": {
            "container_sel_any_of": ["#mosaic-provider-jobcards","[data-testid='jobResults']"],
            "item_sel_any_of": [".jobCard_mainContent","[data-testid^='jobCard-']"],
            "fields": ["bbox"],
            "collect": "rects",
            "return_metrics": true,
            "return_container_bbox": true
          },
          "save": "list",
          "trace_tag": "grab_list"
        },
        { "do": "get_list_length", "from": "@list['rects']", "save": "n" },
        { "do": "set_variable", "name": "i", "value": 0 }
      ],
      "on_success": "each"
    },

    "each": {
      "actions": [
        { "do": "get_list_item", "from": "@list['rects']", "index": "@i", "save": "rect" },
        { "do": "query_data", "from": "@list", "query": "container_bbox", "save": "pane" },

        { "do": "branch", "if": "!is_visible(@rect, @pane)", "then": "scroll_into_view" },

        { "do": "click_coordinates",
          "bbox": "@rect",
          "trace_tag": "click_list_item",
          "guard": { "source_vars_only": true }
        },
        { "do": "wait_for", "until": { "type": "ext.wait_quiet", "timeout_ms": 8000 } }
      ],
      "on_success": "try_apply",
      "on_error": "advance"
    },

    "scroll_into_view": {
      "actions": [
        { "do": "wheel_coordinates", "at_bbox": "@pane", "amount": -600 }
      ],
      "on_success": "each"
    },

    "try_apply": {
      "actions": [
        { "do": "ext.extract",
          "args": { "mode": "find_button_bbox", "button_text_any_of": ["Apply", "Quick Apply", "立即申请"] },
          "save": "apply_btn"
        },
        { "do": "branch", "if": "@apply_btn != null", "then": "click_apply", "else": "advance" }
      ]
    },

    "click_apply": {
      "actions": [
        { "do": "click_coordinates",
          "bbox": "@apply_btn['bbox']",
          "trace_tag": "click_apply",
          "guard": { "source_vars_only": true }
        },
        { "do": "wait_for", "until": { "type": "ext.wait_quiet", "timeout_ms": 12000 } }
      ],
      "on_success": "advance",
      "on_error": "advance"
    },

    "advance": {
      "actions": [ { "do": "increment_variable", "name": "i" } ],
      "transitions": [
        { "if": "@i < @n", "go_to": "each" },
        { "else_go_to": "harvest" }
      ]
    }
  }
}
```

> 其中 `is_visible(@rect, @pane)` 由运行时在表达式里注册（调用 `visibility/viewport.py`）。

---

# 7) 实施步骤（任务拆分 + 负责人建议）

**T1 Schema 升级（后端 & DevEx）**

* 合并 v1.2 增量；更新 VSCode `json.schemas` 映射；CI ajv 校验脚本支持 v1.2
* 输出：`schema/workflow.schema.v1_2.json`、迁移说明

**T2 运行时增强（客户端）**

* 读取 `features/guard/trace_tag`；表达式引擎仅白名单操作
* 事件记录打上 `trace_tag`

**T3 坐标换算与多屏支持（客户端）**

* `geom/coords.py`：DPR/窗口度量/多屏偏移；Windows/macOS API 封装
* 单元测试：常见分辨率/缩放组合

**T4 人类化鼠标（客户端）**

* `humanize/mouse.py`：贝塞尔轨迹、随机抖动、停顿、后延迟点击
* 配置：可通过 `features.humanize.mouse` 开关

**T5 新动作实现**

* `actions/click_coordinates.py`：来源校验 + 坐标换算 + humanize
* `actions/wheel_coordinates.py`：容器中心滚轮

**T6 容器可见性与滚动（客户端）**

* `visibility/viewport.py`：判断/带入可视逻辑；表达式绑定 `is_visible()`

**T7 标定工具（客户端）**

* `tools/calibrate.py`：两点标定、输出偏移/比例修正；写入本机 profile

**T8 示例工作流与手册（DevEx）**

* `examples/indeed_coords_apply.wf.json`
* README：如何开启扩展→运行→校准→查看回放

**T9 测试矩阵 & 冒烟**

* 缩放：100/125/150%；显示器：单/双；分辨率：1080p/1440p
* 场景：打开 Indeed → 搜索 → 逐条点击 → 右栏稳定 → 找 Apply → 坐标点击

---

# 8) 测试与验收（清单）

## 单元（tests/unit）

* `test_coords.py`：多组 `rect + metrics + monitor` → `px,py` 与期望误差 ≤ 2px
* `test_visibility.py`：边界情况（恰好贴边/超出 1px/有 margin）
* `test_humanize.py`：路径长度、最大瞬时速度限制、抖动范围、停顿分布

## 集成（tests/integration）

* 伪页面（fixtures）模拟左列滚动容器（固定宽度、高度可变）
* 脚本驱动动作，验证在不同缩放是否能“滚入可视并点击中心”成功

## 实机冒烟（Runbook）

1. 启动扩展与客户端；`tools/calibrate.py` 运行一次
2. 打开 Chrome→Indeed→搜索 “ai”
3. 执行示例工作流；观察 run\_events 与快照
4. 切换缩放比例、切换第二屏；重复 2–3 次

## 验收标准（必须同时满足）

* 在 **100/125/150%** 缩放 & **单/双屏** 下，连续处理 ≥ 10 个列表项，**点击偏移 ≤ 3px**，失败率 ≤ 5%（失败可自动跳过）
* 人类化轨迹平均速度与停顿符合设定阈值（日志统计）
* 发生点击失败时有明确事件与快照可定位（`trace_tag` 清晰）

---

# 9) 风险与回滚

* **多屏偏移异常**：回退使用“单屏模式”开关（暂时禁用多屏偏移），并提示用户仅在主屏运行
* **缩放读取失败**：回退到 `calibrate.py` 的手动标定修正
* **人类化轨迹导致超时**：降低轨迹弯曲度/停顿时长（可配置），或暂时关闭 `features.humanize.mouse`
* **动作误点**：启用 `guard.source_vars_only=true`（默认开启），并在坐标执行前加“安全半径验证”（比对目标 rect 与预期容器交集）

---

# 10) 今日即可执行（快速启动指令）

**Makefile（节选）**

```makefile
.PHONY: dev schema test calibrate demo

dev:
\tpnpm --filter server dev & \\
\tpython runtime/tools/dev_runner.py

schema:
\tnode scripts/validate.js examples/indeed_coords_apply.wf.json schema/workflow.schema.v1_2.json

test:
\tpytest -q tests/unit && pytest -q tests/integration

calibrate:
\tpython runtime/tools/calibrate.py

demo:
\tpython runtime/tools/run_workflow.py examples/indeed_coords_apply.wf.json
```

**VSCode 绑定**

```json
{
  "json.schemas": [
    { "fileMatch": ["*.wf.json","workflows/**/*.json"], "url": "./schema/workflow.schema.v1_2.json" }
  ]
}
```

---

# 11) 不遗漏核对（Sprint A 覆盖）

* [x] v1.2 Schema 增量（features/guard/trace\_tag）
* [x] `click_coordinates`（DOMRect→屏幕，humanize，guard）
* [x] `wheel_coordinates`（容器中心滚轮）
* [x] 容器可见性判断 + 滚动带入
* [x] 多屏/缩放支持 + 标定工具
* [x] 示例工作流（Indeed 坐标点击）
* [x] 单元/集成/实机冒烟测试矩阵
* [x] 文档与回滚策略

---
Sprint B：
先**简短回顾**一下我们的大图与上一 Sprint，确认路线不跑偏：

* 大图（v2 升级十条）：插件化动作、Planner→Executor、DOMRect→坐标点击、人类化执行、LP/HP+SQS、本地 OCR、LLM 路由与计费、市场与密钥（明文可视+审计）、可观测回放、测试与基准。
* Sprint A（已完成）：落地 **Schema v1.2**（features/guard/trace\_tag），实现 **click\_coordinates / wheel\_coordinates**、容器可见性判断、多屏/缩放校准、人类化鼠标；用示例工作流跑通 Indeed「AI 搜索→左列坐标点击→右侧稳定→Apply」。

接下来进入**Sprint B：插件化 GA + 市场最小闭环**。目标是：**让动作像插件一样热插拔并可上架/购买/安装/回滚**，在你现有引擎上不改核心逻辑即可扩展能力库。

---

# Sprint B 目标（2 周）

1. 客户端：**插件运行时（Plugin Runtime）** GA

   * 插件声明（`plugin.yaml`）、动作注册（带 JSON Schema）、权限/域名白名单、签名校验（ed25519）、**热加载与回滚**。
2. 服务端：**市场最小闭环**

   * `.wfpack.tgz` 包格式（含 workflow\.json/插件/元数据/签名）、上架/购买/安装/回滚 API。
3. DevEx：**CLI**（打包/签名/安装/回滚）与 VSCode 片段模板。
4. 验收：从市场安装“Indeed 坐标点击”插件与工作流，**不重启客户端**即可运行。

---

## 交付物（DoD）

* `runtime/plugins/loader`、`runtime/plugins/registry`、`runtime/plugins/signer`（校验签名/版本/权限）
* `schema/plugin.schema.json`（校验 `plugin.yaml`）
* 包格式：`.wfpack.tgz`（目录结构与 Manifest）
* Server API：`/market/publish|purchase|install|rollback` & `GET /workflows/:id`
* DB：沿用你已有的 `workflows/purchases/installs`（如需补字段，本 Sprint 迁移）
* CLI：`wf pack|sign|install|rollback|list`
* 示例插件：`indeed_coords`（暴露 `click_coordinates`/`wheel_coordinates`，但指向我们 Sprint A 的实现，以验证管线）
* E2E：上架→购买→安装→热加载→回滚 流程测试
* 文档：插件开发指南、签名/权限、市场发布流程、回滚 Runbook

---

## 目录与文件（增量建议）

```
repo/
├─ schema/
│  ├─ plugin.schema.json
│  └─ workflow.schema.v1_2.json (已)
├─ runtime/
│  ├─ plugins/
│  │  ├─ loader.py          # 扫描/校验/热加载/回滚
│  │  ├─ registry.py        # register_action/卸载/版本选择
│  │  ├─ signer.py          # ed25519 验证工具
│  │  └─ sandbox.py         # 受限执行环境（可留空壳，下一 Sprint 强化）
│  ├─ actions/              # 内建动作仍保留（优先级低于插件同名动作）
│  └─ tools/
│     └─ wf_cli.py          # wf pack/sign/install/rollback/list
├─ server/
│  ├─ routes/market.ts      # publish/purchase/install/rollback
│  ├─ services/wfpack.ts    # 解包/元数据验签/存储/S3
│  └─ services/signature.ts # ed25519 验签
├─ examples/
│  ├─ plugins/indeed_coords/
│  │  ├─ plugin.yaml
│  │  ├─ actions.py
│  │  └─ README.md
│  └─ marketplace_demo/
│     ├─ indeed_coords_apply.wf.json
│     └─ wfpack.manifest.json
└─ tests/
   ├─ unit/test_plugin_loader.py
   ├─ unit/test_signer.py
   ├─ integration/test_market_install.py
   └─ e2e/test_market_flow.py
```

---

## 包格式（`.wfpack.tgz`）

```
wfpack/
  manifest.json            # 包元信息（见下）
  workflows/*.wf.json      # 一个或多个工作流（v1.2）
  plugins/*                # 插件目录（可多个）
  assets/*                 # 锚点/图片等
  SIGNATURE                # 对 (manifest + workflows + plugins + assets) 的 detached 签名
```

`manifest.json`（关键字段）

```json
{
  "name": "Indeed Coords Pack",
  "version": "1.0.0",
  "publisher": "your-org",
  "workflows": ["workflows/indeed_coords_apply.wf.json"],
  "plugins": ["plugins/indeed_coords"],
  "min_engine": "1.2.0",
  "permissions": { "hosts": ["https://*.indeed.com"], "capabilities": ["mouse","ext_messaging"] },
  "changelog": "Initial GA",
  "signature": { "algo": "ed25519", "pubkey_id": "org_main_2025_01" }
}
```

---

## `plugin.yaml`（受 `schema/plugin.schema.json` 约束）

```yaml
name: indeed_coords
version: 1.0.0
engine_min: 1.2.0
permissions:
  hosts:
    - "https://*.indeed.com"
  capabilities:
    - mouse
    - ext_messaging
actions:
  - name: click_coordinates
    entry: actions.py:click_coordinates
    schema:
      type: object
      required: ["bbox"]
      properties:
        bbox: { type: "object" }
        trace_tag: { type: "string" }
        guard:
          type: object
          properties:
            source_vars_only: { type: "boolean" }
  - name: wheel_coordinates
    entry: actions.py:wheel_coordinates
    schema:
      type: object
      required: ["at_bbox", "amount"]
      properties:
        at_bbox: { type: "object" }
        amount: { type: "integer" }
```

**动作实现（示例）**（指向 Sprint A 的实现；这里作为“插件形态”演示）

```python
# examples/plugins/indeed_coords/actions.py
from runtime.plugins.registry import register_action
from runtime.geom.coords import rect_center_to_screen_xy
from runtime.humanize.mouse import human_move_and_click, human_scroll
from runtime.engine.context import get_page_metrics

@register_action("click_coordinates")
def click_coordinates(ctx, bbox, trace_tag=None, guard=None, **_):
    if guard and guard.get("source_vars_only", False):
        ctx.assert_source_from_vars("bbox", bbox)
    metrics = get_page_metrics(ctx)
    x,y = rect_center_to_screen_xy(bbox, metrics, ctx.os_monitors)
    ctx.events.log("action.click_coordinates", {"x":x,"y":y,"trace":trace_tag})
    human_move_and_click(x,y)
    return {"ok": True}

@register_action("wheel_coordinates")
def wheel_coordinates(ctx, at_bbox, amount, **_):
    metrics = get_page_metrics(ctx)
    x,y = rect_center_to_screen_xy(at_bbox, metrics, ctx.os_monitors)
    human_scroll(x,y, amount)
    ctx.events.log("action.wheel_coordinates", {"x":x,"y":y,"amount":amount})
    return {"ok": True}
```

---

## 客户端插件运行时要点

* **加载顺序**：内建动作 < 已安装插件动作（同名覆盖需带版本告警）
* **热加载**：文件监控或显式 API 触发加载；加载失败 → 回滚到上一版本
* **安全**：

  * 检查 `engine_min` 与当前引擎版本
  * 校验签名（ed25519）；签名不通过 → 拒绝安装
  * 权限合规：插件声明的 `hosts/capabilities` 必须在引擎允许范围内
* **隔离**：首版可用**进程内隔离+能力白名单**；后续 Sprint 可引入 `subprocess` 沙箱

---

## 服务端市场 API（最小）

* `POST /market/publish`：上传 `.wfpack.tgz`，校验签名与 `manifest`，入库 `workflows` 并存储包
* `POST /market/purchase`：{workflow\_id, seats} → 生成 `purchases`
* `POST /market/install`：{device\_id, workflow\_id, version} → 生成 `installs` 并下发安装指令（WS/SSE）
* `POST /market/rollback`：{device\_id, workflow\_id, to\_version} → 下发回滚指令
* `GET /workflows/:id`：详情（含 plugins/permissions/changelog）

> 客户端收到安装/回滚指令后：拉取包 → 验签 → 部署到本地 `plugins/` 与 `workflows/` → 触发热加载 → 上报结果事件。

---

## CLI（开发者体验）

```
# 打包
wf pack --src ./examples/marketplace_demo --out ./dist/indeed_coords.wfpack.tgz
# 签名
wf sign --in ./dist/indeed_coords.wfpack.tgz --key ./keys/ed25519_sk.pem
# 安装到本机（跳过市场）
wf install --wfpack ./dist/indeed_coords.wfpack.tgz
# 列表/回滚
wf list
wf rollback --workflow Indeed Coords Pack --to 1.0.0
```

---

## 数据库与迁移

* 如需补充字段：

  * `workflows.signature_pubkey_id`、`workflows.min_engine`、`workflows.permissions`
  * `installs.status`（installing/active/rolled\_back/failed）、`installs.logs_url`
* 迁移脚本：`V0XX__market_ga.sql`

---

## 测试与验收

### 单元

* `test_signer.py`：签名/验签通过与失败用例
* `test_plugin_loader.py`：正常/缺 schema/权限超界/签名失败/版本不兼容/回滚

### 集成

* `test_market_install.py`：服务端 publish→purchase→install（使用本地包与 Local S3）

### E2E（关键）

1. **发布**：`wf pack` + `wf sign` → `POST /market/publish` 成功
2. **购买**：`POST /market/purchase`（seats=2）
3. **安装**：`POST /market/install` 到一台测试机 → 客户端热加载成功（事件回传）
4. **运行**：执行 `examples/marketplace_demo/indeed_coords_apply.wf.json` 成功
5. **回滚**：`POST /market/rollback` 到旧版本 → 继续可运行
6. **安全**：尝试安装伪造包 → 被拒绝并记录审计

**验收标准**

* 从“上架”到“安装运行”端到端 ≤ 2 分钟；
* 客户端安装后**无须重启**即可识别新动作；
* 回滚成功、且日志有迹可循；
* 伪造签名包被拒，审计记录完整。

---

## 风险与回滚策略

* **签名校验不通过**：拒绝安装，保留旧版本继续执行
* **插件加载崩溃**：自动回滚至上一个 `active` 版本；标红并报警
* **权限超界**：安装前检查，提示 Publisher 修改 `plugin.yaml`
* **市场服务异常**：支持离线安装（本地 `wf install --wfpack …`）；恢复后再补登记

---

## 与路线图对齐（不跑偏校验）

* ✅ 插件化 GA（本 Sprint 核心）
* ✅ 市场最小闭环（发布/购买/安装/回滚）
* ✅ 保持与 Sprint A 的坐标链路兼容（插件示例即复用 A 的动作）
* ⏭ 下一步 Sprint C：**Planner→Executor 强化**（`llm.plan` + `plan.execute` 白名单/来源校验/短计划回合）

---
好的。我把前面 A–C（坐标链路、插件化+市场、Micro-Plan Planner→Executor）**全部当作已落地的基础**，在不跑偏的前提下，重新规划**后续的强化路线**，把 **AgentQ 与 MCTS** 系统性纳入，且确保与现有 HP/LP、SQS、坐标点击、人类化执行、可观测/回放完全兼容、可灰度发布、可随时回退。

---

# 核心设计原则（先定边界）

* **不替换**现有引擎：新增“搜索式决策层（Search Layer）”，以策略插件形式插到 `llm.plan` 上游/旁路。
* **先安全后智能**：白名单动作 + 参数来源校验 + 预算/步数上限 + HITL（高风险动作）始终有效。
* **可灰度/可回退**：新策略全部通过策略标志位启用（workflow/租户/设备三级开关），默认仍用贪心 Micro-Plan。
* **成本可控**：严格请求/时间/分支预算；优先用**启发式/历史经验**，减少 LLM 次数。
* **对齐现有工件**：沿用 PageState、坐标点击、SQS HP 抢占、可观测时间线与快照。

---

# 路线图（C 之后的新版 Sprint 规划）

## Sprint D｜Search Layer 基础 & Mini-MCTS（多候选 + 轻量模拟）

**目标**：把单条贪心计划升级为**多候选评估**，不做真实点击，先在本地“轻量模拟（simulate）”后再执行最优候选。

**关键增量**

* **策略接口**：`planner.strategy = greedy | beam | mcts-mini`（workflow v1.2 中以 `features.planner.strategy` 配置）。
* **候选生成**（Server）：`/llm/plan` 支持 `N` 条候选（Beam-like），每条 ≤ 5 步。
* **轻量模拟**（Client）：`plan.simulate` 新模块，基于 PageState + 规则做**无副作用预测**：

  * 点击列表项 → 预测“右栏标题将变更/网络静默”
  * 滚动容器 → 预测“候选元素进入可视区域”
  * 找 Apply → 预测“按钮文案/可见性”
* **评分函数（Reward v0）**：是否达成子目标 + 预计步数/超时惩罚 + 预估稳定性（ext.wait\_quiet 命中概率）。
* **选择与落地**：选分数最高的候选 → 正式 `plan.execute`。

**产出**

* 新动作：`plan.simulate`
* Server：`/llm/plan` 扩展 `num_candidates`、`strategy`
* 可观测：`plan.branch`、`plan.choice` 事件（记录候选及分数）

**验收**

* 在 Indeed “AI 搜索→坐标申请”路径，**成功率提升**（相对 C），且 HP 抢占不受影响。

---

## Sprint E｜Plans History & Fingerprint（为 AgentQ/MCTS 打地基）

**目标**：把“哪种候选在什么页面状态下效果好”记录下来，支持回放/复盘/离线评估。

**关键增量**

* **状态指纹（Fingerprint）**：`page_state_fingerprint`（域名、路径模式、左/右容器布局 hash、列表长度/密度、关键控件集合、DPR/缩放等）。
* **历史表**：`plans_history(goal, fingerprint, candidate_plan, score, outcome, reward, latency, errors)`。
* **离线回放**：`wf replay --plan-id xxx`，重渲染事件时间线、对比当时 PageState。
* **A/B 标记**：运行时把策略标签写入事件，支持报表。

**验收**

* 控制台能按“goal + fingerprint”检索历史计划，看到成功/失败分布与典型错误。

---

## Sprint F｜AgentQ（基于经验的候选重排）

**目标**：把历史成功经验沉淀成“动作质量估计（Q-value）”，在生成候选时**先验重排**，减少无效探索与 LLM 次数。

**关键增量**

* **Q 表结构**：`agentq_qvalues(fingerprint, action_signature, q, n, last_updated)`

  * `action_signature`：抽象动作模板（如“wheel\@leftPane(-600)”、“click\@list\[i+1]”）。
* **融合策略**：候选打分 = `α * normalize(历史Q) + (1-α) * 模拟打分`；冷启动时靠模拟，跑久了靠 Q。
* **在线更新**：执行完成后按 `TD(0)` 或加权回溯更新 Q：`Q <- Q + η*(reward - Q)`。
* **ε-贪心**：小概率探索非最优候选，避免早熟。

**验收**

* 同一站点/目标重复运行若干次后，平均步数下降、成功率提升；LLM 计划调用次数下降。

---

## Sprint G｜Full MCTS（受限深度 + rollout + 回溯）

**目标**：在复杂站点（多层弹窗、动态表单）开启**有限深度的 MCTS**：选择（UCB1/PUCT）、扩展（LLM 产子动作）、rollout（启发式或廉价 LLM 估值）、回溯（累计 reward）。

**关键增量**

* **搜索管理器**：`search/mcts.py`（树节点存 `state_key, prior, value, visits`）。
* **节点扩展**：以 `llm.plan` 生成下一步候选；每次扩展不超过 `B` 个子节点。
* **rollout**：

  * 首选启发式 roll-out（基于 PageState 规则），
  * 必要时调用**便宜模型/小上下文**做估值（禁止真实点击）。
* **预算**：`max_nodes/max_depth/max_time`（从 workflow 配置），超预算即停止，返回根节点最优分支。
* **安全**：仍受白名单动作/参数来源/HP 抢占/预算约束。

**验收**

* 在“复杂表单申请/多弹窗”页面，较 D/F 明显提升成功率；回放能看到搜索树摘要（访问次数、价值分布）。

---

## Sprint H｜策略治理 & 生产化硬化

**目标**：把搜索式 Planner 生产化：策略开关、灰度、AB、报表、告警、回退。

**关键增量**

* **策略开关**：租户/工作流/设备三级 `planner.strategy` 与预算阈值；一键回退到 `greedy`。
* **AB/报表**：策略对照（成功率、步数、耗时、LLM 次数、成本/任务）。
* **告警**：某域名在某策略下失败率/成本飙升即自动回退并告警。
* **文档**：站点级“最佳策略”建议（例如 Indeed→F，某政务网→G）。

**验收**

* 策略切换/回退一键生效；AB 报表能看到清晰的收益曲线；异常能自动回退。

---

# 关键实现要点（跨 Sprint 的共性设计）

### 1) Workflow 扩展（仍兼容 v1.2）

```json
{
  "features": {
    "planner": {
      "strategy": "greedy | beam | mcts-mini | agentq | mcts-full",
      "budget": { "max_steps": 5, "max_time_ms": 15000, "max_nodes": 50, "max_depth": 6 },
      "ab_tag": "exp_2025_indeed"
    }
  }
}
```

### 2) Reward 统一规范

* +1：达成“子目标/关键状态”（如出现 Apply/发送成功/评论区到底哨兵命中）
* −λ：步数/时间/滚动次数/HP 抢占后未恢复
* −∞：安全违规（越权动作/来源不合规）

### 3) PageState 指纹（Fingerprint）建议

* `host + path pattern + panes rect ratio + list_density + key_controls(text/aria roles) + DPR/zoom` → 哈希
* 作为 Q 表与 plans\_history 的主键之一

### 4) 成本控制

* 先候选→后模拟→再执行；MCTS 只在“失败率较高的路由/页面”打开
* provider AUTO：控制器（Claude3.5）/视觉估值（GPT-4o 微上下文）

### 5) 可观测 & 回放

* 事件：`plan.branch/choice/expand/rollout/backprop`
* 搜索树摘要：节点数、访问次数热度、最优分支
* 回放里展示“原计划 vs 实际动作 vs HP 抢占点”

---

# 风险与兜底

* **成本上涨**：将 MCTS 设为按站点白名单 & 有失败阈值才触发；强预算。
* **计划质量波动**：默认退回 `greedy`；F（AgentQ）上线后先在可控站点灰度。
* **模拟偏差**：simulate 只用于**相对排序**，执行前仍要 `wait_quiet` 与按钮再确认；必要时视觉兜底。
* **数据稀疏**：AgentQ 引入 ε-贪心与相似指纹聚类；不足时回落到模拟评分。

---

# 落地顺序建议（每个 Sprint 都有“可演示的成功”）

1. **D**：多候选 + `plan.simulate`，可观测到候选与选择；Indeed 成功率上扬。
2. **E**：历史与指纹；控制台能按指纹回放与聚类分析。
3. **F**：AgentQ 先验重排；同域名/目标复跑越跑越稳、越便宜。
4. **G**：MCTS 只开在“难站点”；展示搜索树摘要与收益。
5. **H**：策略治理与自动回退；运维闭环。
---
Sprint D：
我们已完成
A（坐标链路 GA）→ B（插件化+市场闭环）→ C（Planner→Executor：Micro-Plan 贪心）。
**Sprint D** 目标是把 Planner 升级为\*\*“多候选 + 轻量模拟”的 Mini-MCTS\*\*（非真实点击），在你的既有坐标链路/HP 优先/SQS/可观测框架内无缝接入。

---

# Sprint D｜Mini-MCTS Planner（多候选 + 轻量模拟）

**周期**：2 周
**核心产出**：`llm.plan` 支持多候选；客户端新增 `plan.simulate` 对候选进行**无副作用评分**，选最优后再 `plan.execute`；可观测记录“候选/选择/评分”。**不改**现有安全边界（白名单动作 + 参数来源校验 + 预算 + HP 抢占）。

## 1) 范围与接口变化（兼容 v1.2）

### 1.1 Workflow 新增（向后兼容）

```json
{
  "features": {
    "planner": {
      "strategy": "mcts-mini",          // 默认仍可用 "greedy"
      "num_candidates": 3,              // 2~5
      "budget": { "max_steps": 5, "max_time_ms": 15000 },
      "ab_tag": "exp_2025_d"
    }
  }
}
```

### 1.2 Server：`POST /llm/plan` 扩展

* **新增参数**：`strategy: "mcts-mini"`, `num_candidates: int`
* **返回**：`{ candidates: MicroPlanV1[], usage, provider }`（`candidates[0]`可为“贪心主路径”）

### 1.3 Client 新动作

* `ext.get_pagestate`（标准化 PageState，沿用 C 阶阶段定义）
* `llm.plan`（调用服务端，拿回 candidates）
* **`plan.simulate`（本次新增）**：对 `candidates` 基于 PageState 做**轻量模拟**，返回每个候选的 `score` 与 `explain`
* 选最高分 → `plan.execute`（沿用 C）
* 可观测事件：`plan.branch`（列候选+原始估分）、`plan.simscore`、`plan.choice`

---

## 2) 轻量模拟（simulate）设计

**目的**：0 风险评估**潜在效果**，不做真实点击/滚动，仅在**虚拟状态**上推演 1\~N 步，估算 reward。

### 2.1 可支持步型（本 Sprint）

* `wheel_coordinates(at_bbox, amount)`

  * 规则：若 `at_bbox == leftPane.rect` → 预测列表“上/下滚一屏”；更新虚拟 `scrollTop`，判断目标 item 是否进入可视区。
* `click_coordinates(bbox)`

  * 规则：若点在左 Pane 的 itemRect → 预测“右侧详情变更 + network 静默一次”；
* `wait_for(ext.wait_quiet)`

  * 规则：增加预计等待成本（`~0.6~1.2s`），并提高“稳定成功”的置信度。
* `ext.extract(mode=find_button_bbox, button_text_any_of=[…])`

  * 规则：若当前 PageState `visibleControls` 中已有匹配按钮 → 高分；若**预测在点击后**将出现 → 中分；否则低分。

### 2.2 评分函数（Reward v0，可配置）

```
R = + Wgoal * goal_hit
    - Wstep * steps
    - Wscroll * scrolls
    - Wwait * expected_wait_s
    - Wuncert * (1 - confidence)
```

建议默认：`Wgoal=3, Wstep=0.5, Wscroll=0.3, Wwait=0.2, Wuncert=0.5`

* `goal_hit`：候选最后一步**有较高概率**达到“Apply 按钮可点击/右栏稳定”
* `confidence`：规则命中多则高，需预测/假设多则降

### 2.3 参数来源与安全

* `plan.simulate` **只读** `@page_state` 与候选 `steps`；
* 仍做**参数来源校验**（任何 bbox/rect 必来自 `@page_state`/上一步结果），与 `plan.execute` 一致；
* 超预算（步数/时间）直接丢弃候选。

---

## 3) 模块与代码骨架

### 3.1 目录增量

```
runtime/
├─ search/
│  └─ minimcts.py             # evaluate_candidates()
├─ actions/
│  ├─ ext.get_pagestate.py
│  ├─ llm.plan.py
│  ├─ plan.simulate.py        # 新增
│  └─ plan.execute.py         # 复用 C（步间仍可 HP 抢占）
└─ engine/
   └─ provenance.py           # 参数来源校验（已在 C）
server/
├─ routes/llm.plan.ts         # 支持 strategy/num_candidates
└─ schemas/microplan.v1.json  # 无变（C 已有）
```

### 3.2 `plan.simulate`（伪代码）

```python
def simulate_candidate(candidate, page_state, budget, heuristics):
    sim = VirtualState.from_page_state(page_state)
    score, steps, scrolls, wait_s, conf = 0, 0, 0, 0.0, 0.5
    goal_hit = 0

    for st in candidate["steps"][:budget.max_steps]:
        steps += 1
        if st["do"] == "wheel_coordinates":
            scrolls += 1
            sim.scroll_container(st["args"]["at_bbox"], st["args"]["amount"])
            conf *= 0.98
        elif st["do"] == "click_coordinates":
            # 如果点击落在左侧 item，预测右栏变化
            if sim.is_in_left_list(st["args"]["bbox"]):
                sim.predict_right_pane_changed()
                wait_s += heuristics.wait_quiet
                conf *= 1.05
            else:
                conf *= 0.95
        elif st["do"] == "wait_for":
            wait_s += heuristics.wait_quiet
            conf *= 1.02
        elif st["do"] == "ext.extract":
            if sim.visible_apply_button_now() or sim.apply_button_likely_after_click():
                goal_hit = 1
                conf *= 1.05
            else:
                conf *= 0.95

        if time_budget_exceeded(): break

    R = (heuristics.Wgoal*goal_hit
         - heuristics.Wstep*steps
         - heuristics.Wscroll*scrolls
         - heuristics.Wwait*wait_s
         - heuristics.Wuncert*(1.0 - clamp(conf,0,1)))
    return {"score": R, "explain": {...}, "goal_hit": goal_hit}
```

### 3.3 `search/minimcts.py`

```python
def evaluate_candidates(ps, candidates, budget, heuristics):
    scored = []
    for c in candidates:
        s = simulate_candidate(c, ps, budget, heuristics)
        scored.append({ "plan": c, **s })
    best = max(scored, key=lambda x: x["score"])
    return best, scored
```

---

## 4) 示例工作流（Indeed 坐标申请，使用 Mini-MCTS）

```json
{
  "version": "1.2",
  "start": "loop",
  "features": { "planner": { "strategy": "mcts-mini", "num_candidates": 3, "budget": { "max_steps": 5, "max_time_ms": 15000 }, "ab_tag": "exp_2025_d" }, "humanize": { "mouse": true } },
  "vars": { "i": 0 },
  "states": {
    "loop": {
      "actions": [
        { "do": "ext.get_pagestate", "save": "ps" },
        { "do": "llm.plan", "strategy": "mcts-mini",
          "allowed_actions": ["click_coordinates","wheel_coordinates","ext.extract","wait_for"],
          "constraints": { "max_steps": 5, "no_dom_click": true, "must_stay_in_host": "indeed.com" },
          "num_candidates": 3, "inputs": { "page_state": "@ps", "context": { "i": "@i" } }, "schema": "MicroPlanV1",
          "save": "cands" },
        { "do": "plan.simulate", "from": "@cands", "page_state": "@ps",
          "policy": { "max_steps": 5, "max_time_ms": 15000 }, "save": "choice" },
        { "do": "plan.execute", "from": "@choice['plan']",
          "policy": { "allowed": ["click_coordinates","wheel_coordinates","ext.extract","wait_for"], "max_runtime_ms": 15000, "per_step_timeout_ms": 5000 },
          "save": "res" }
      ],
      "transitions": [
        { "if": "@res['ok']==true", "go_to": "advance" },
        { "else_go_to": "fallback_scroll" }
      ]
    },
    "advance": { "actions": [ { "do": "increment_variable", "name": "i" } ], "on_success": "loop" },
    "fallback_scroll": {
      "actions": [ { "do": "wheel_coordinates", "at_bbox": "@ps['panes']['left']['rect']", "amount": -800 }, { "do": "sleep_ms", "value": 600 } ],
      "on_success": "loop"
    }
  }
}
```

---

## 5) 可观测与回放

* 事件新增：

  * `plan.branch`：`{count, candidates_digest}`
  * `plan.simscore`：`[{idx, score, goal_hit, explain}]`
  * `plan.choice`：`{picked_idx, picked_score}`
* 回放 UI：在时间线中展示三栏：**候选 → 评分 → 选择**；失败时可快速定位“评分偏差”的原因。

---

## 6) 测试与验收

### 单元

* `test_simulate_scroll_visibility`：滚动后 item 进入可视 → `goal_hit` 升高
* `test_simulate_click_detailchange`：点击左列 item → 预测右栏变化 & `wait_quiet` 成本
* `test_score_budget_limits`：超步数/超时丢弃候选
* `test_source_provenance`：候选含非来源 bbox → 被拒绝评分

### 集成

* `test_planner_candidates`：Server 返回 N 个候选，结构合规
* `test_minimcts_pick_best`：模拟 3 个候选 → 选择最优 → 执行成功率高于贪心

### E2E（实机）

* 在 Indeed “ai” 搜索页，连续处理 20 条职位：

  * **成功率** ≥ C 阶段基线 +5%（例如从 85% → ≥90%）
  * **平均步数** 不高于 C 阶段 +0.5 步
  * HP 抢占时，步间让出不超过 1 步延迟

---

## 7) 任务拆解（建议分工）

* **Server（1人）**：`/llm/plan` 扩展（strategy/num\_candidates），Provider 路由与限额；返回 candidates。
* **Client-Search（1人）**：`plan.simulate` + `search/minimcts.py` + 评分函数。
* **Client-Engine（1人）**：与 `plan.execute` 对接，事件打点（branch/simscore/choice）。
* **QA（1人）**：单测/集成/E2E 场景与基线/对比；冒烟脚本。
* **DevEx（0.5人）**：示例工作流、CLI `wf plan-simulate --dump`、文档与回放 UI 强化。

---

## 8) 风险与回退

* **评分偏差** → 降低 `Wuncert`、提高 `Wwait`；若仍不稳，降级为 `strategy="greedy"`（workflow 热切）。
* **成本上升** → 限制 `num_candidates<=3`、缩短 `max_steps=4`；Provider 走 AUTO（便宜模型）。
* **HP 抢占受阻** → `plan.execute` 步间强制 `yield`；评分阶段也插入轻量 `yield`。
* **异常候选**（越权/越域）→ 服务器端先过滤，客户端再校验，直接丢弃并记录审计事件。

---

### 对齐检查（不跑偏）

* 坐标点击、人类化、HP/LP、SQS、白名单/来源校验 → **全部沿用**；
* 仅在 Planner 侧引入**候选 + 模拟**，**不改变**执行与安全基线；
* 可灰度：`features.planner.strategy` 一键回退。

---
Sprint E：


* 已完成：
  **A**（坐标链路 + 人类化）、**B**（插件化 + 市场闭环）、**C**（Micro-Plan Planner→Executor）、**D**（Mini-MCTS：多候选 + 轻量模拟 + 评分选优）。
* 本 Sprint **E** 的定位：为后续 **AgentQ** / **Full MCTS** 打地基——**把“计划—选择—执行—结果—奖励”完整记录**起来，可查询、可回放、可用于离线评估与在线学习。

下面是**Sprint E：Plans History & Fingerprint**的落地计划（可以直接按条推进）。

---

# Sprint E 目标（2 周）

1. 建立\*\*状态指纹（Fingerprint）**与**计划历史（Plans History）\*\*标准化存储。
2. 客户端在 `plan.simulate → plan.choice → plan.execute` 全链路**自动打点**，计算**奖励（Reward）**。
3. 提供**回放（Replay）**与**检索（Query）**：按 goal / 域名 / 指纹 / 策略 / AB 标签查看过去的候选、评分、选择、结果。
4. **对 D 保持完全兼容**：Mini-MCTS 原有调用不改；仅新增持久化与可观测层。

---

## 1) 产出（Definition of Done）

* Postgres 表：`plans_history`、`plan_candidates`、（可选）`plan_steps`、索引与保留策略。
* Server API：

  * `POST /plans/log`（批量写入历史，或复用 run\_events 管道由后端异步落库）
  * `GET /plans/history`（查询）
  * `GET /plans/:id`（详情 + 回放素材）
* 客户端：

  * 在 `plan.simulate`、`plan.choice`、`plan.execute` 后**自动记录**并上传；
  * 统一**Reward 计算**（可配置权重）；
  * 失败也要写（含错误码与上下文）。
* DevEx & 工具：

  * `wf history`（CLI 查询）
  * `wf replay --run-id ...`（时间线 + 快照回放；或 `--plan-id ...` 离线重放）
* 控制台：最小报表（按指纹/策略的成功率、平均步数、平均耗时、LLM 次数/成本）。
* 文档：指纹规范、奖励函数、回放使用说明。
* 测试：单元 / 集成 / E2E（见下）。

---

## 2) 数据库设计（DDL 示例）

```sql
-- 计划历史（一次“候选→选择→执行”的聚合）
CREATE TABLE plans_history (
  id              BIGSERIAL PRIMARY KEY,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  user_id         BIGINT NOT NULL,
  device_id       BIGINT NOT NULL,
  workflow_id     BIGINT NOT NULL,
  run_id          BIGINT NOT NULL,             -- 对应一次 workflow_run
  strategy        TEXT NOT NULL,               -- greedy | mcts-mini | agentq | mcts-full
  ab_tag          TEXT,                        -- 实验分组
  goal            TEXT NOT NULL,
  goal_hash       TEXT NOT NULL,               -- sha256(goal 标准化)
  host            TEXT NOT NULL,               -- from PageState
  fingerprint     TEXT NOT NULL,               -- state 指纹（见下）
  page_state_meta JSONB,                       -- 摘要（pane布局、dpr、zoom 等）
  num_candidates  SMALLINT NOT NULL,
  picked_index    SMALLINT,                    -- 选择的候选索引
  picked_score    DOUBLE PRECISION,
  outcome         TEXT NOT NULL,               -- success | partial | fail
  reward          DOUBLE PRECISION NOT NULL,
  steps           SMALLINT NOT NULL,           -- 实际执行步数
  duration_ms     INTEGER NOT NULL,            -- 实际执行耗时
  llm_calls       SMALLINT NOT NULL,           -- 本阶段 LLM 次数
  llm_tokens      INTEGER NOT NULL,            -- 估算 tokens
  error_code      TEXT,                        -- 若失败
  error_detail    TEXT
);

-- 候选明细（可截断大字段）
CREATE TABLE plan_candidates (
  id              BIGSERIAL PRIMARY KEY,
  history_id      BIGINT REFERENCES plans_history(id) ON DELETE CASCADE,
  idx             SMALLINT NOT NULL,           -- 候选序号
  score           DOUBLE PRECISION,
  goal_hit        BOOLEAN,
  confidence      DOUBLE PRECISION,
  candidate_json  JSONB,                       -- MicroPlanV1（可做压缩）
  explain         JSONB
);

-- 可选：存储实际执行步，以便精细回放/统计（也可复用 run_events）
CREATE TABLE plan_steps (
  id              BIGSERIAL PRIMARY KEY,
  history_id      BIGINT REFERENCES plans_history(id) ON DELETE CASCADE,
  seq             SMALLINT NOT NULL,
  action          TEXT NOT NULL,
  args_digest     TEXT,
  ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
  ok              BOOLEAN,
  elapsed_ms      INTEGER
);

-- 索引
CREATE INDEX idx_plans_history_fingerprint ON plans_history(fingerprint);
CREATE INDEX idx_plans_history_host_goal ON plans_history(host, goal_hash);
CREATE INDEX idx_plans_history_strategy ON plans_history(strategy);
CREATE INDEX idx_plans_history_created_at ON plans_history(created_at);

-- 数据保留策略（示例：90 天）
-- 可用 pg_partman/TTL job 定期清理，或把 candidate_json 过期后裁剪为摘要
```

---

## 3) 指纹（Fingerprint）规范

**目的**：把“可影响决策的页面态”编码成稳定键，用于聚类统计与 AgentQ 索引。

**推荐组成（取子集做 hash）：**

* `host + path_pattern`（/jobs + 查询参数关键子集）
* `pane_layout`（左/右容器存在与否、rect 比例，如 `left:0.32,right:0.68` 离散化到 2 位）
* `list_density`（可见 item 数、平均高度/间距离散）
* `key_controls`（可见按钮文本/ARIA 角色 Top-K 排序后 join）
* `dpr_zoom`（dpr 与缩放档位，如 1.0/1.25/1.5）
* `locale`（en/zh 等）

**实现建议：**

```python
def page_state_fingerprint(ps) -> str:
    host = urlparse(ps['url']).hostname
    path_ptn = normalize_path(ps['url'])          # 去变量片段，只保留模式
    left, right = pane_rects_ratio(ps)
    density = bucket_list_density(ps)             # e.g. "L7" 表示 ~7 项可见
    controls = topk_controls(ps, k=6)             # 取文本/aria 短词，排序后 join
    dpr_zoom = f"{ps['dpr']:.2f}:{zoom_bucket(ps)}"
    raw = f"{host}|{path_ptn}|L{left:.2f}-R{right:.2f}|D{density}|C[{controls}]|Z{dpr_zoom}"
    return sha256(raw)[:32]
```

> **稳定性原则**：尽量用**离散化后的特征**，避免小抖动导致指纹抖动。

---

## 4) 奖励（Reward）统一函数

与 D 的评分一致，正式落地为可配置函数（服务端下发权重；客户端执行）：

```
reward = + Wgoal * goal_hit
         - Wstep * steps
         - Wwait * wait_seconds
         - Wscroll * scroll_count
         - Wuncert * (1 - confidence)
         - Werror * error_flag
```

默认：`Wgoal=3, Wstep=0.5, Wwait=0.2, Wscroll=0.3, Wuncert=0.5, Werror=3`

* `goal_hit`：最终是否达成关键状态（如出现 Apply 按钮并点击成功 / 发送成功）。
* `confidence`：来自 `plan.simulate` 聚合，或执行期实际验证加权修正。
* 失败时强负分（`Werror`）。

---

## 5) Server API

### 5.1 `POST /plans/log`

* **用途**：客户端在 plan 完成后一次性上报（或分阶段上报，后端合并）。
* **请求（示例）**：

```json
{
  "run_id": 12345,
  "strategy": "mcts-mini",
  "ab_tag": "exp_2025_d",
  "goal": "click and apply the i-th job",
  "host": "ca.indeed.com",
  "fingerprint": "8a9c2f...d1",
  "page_state_meta": { "left_ratio": 0.33, "right_ratio": 0.67, "dpr": 1.25 },
  "num_candidates": 3,
  "picked_index": 1,
  "picked_score": 2.14,
  "outcome": "success",
  "reward": 1.78,
  "steps": 4,
  "duration_ms": 6920,
  "llm_calls": 2,
  "llm_tokens": 4800,
  "candidates": [
    { "idx": 0, "score": 1.2, "goal_hit": false, "confidence": 0.62, "candidate_json": { ... }, "explain": { ... } },
    { "idx": 1, "score": 2.14, "goal_hit": true,  "confidence": 0.74, "candidate_json": { ... }, "explain": { ... } },
    { "idx": 2, "score": 0.85, "goal_hit": false, "confidence": 0.58, "candidate_json": { ... }, "explain": { ... } }
  ]
}
```

* **响应**：`{ "history_id": 777 }`

> 也可选择**不暴露该 API**：让客户端把这些信息以 `run_events` 发送，由服务端事件消费器（已有）异步拼装落库。

### 5.2 `GET /plans/history`

* 过滤项：`host, goal, strategy, ab_tag, fingerprint, created_from/to, outcome`
* 支持分页与导出（CSV/JSON）

### 5.3 `GET /plans/:id`

* 返回 `plans_history + plan_candidates + (optional) plan_steps`，并附最近的相关 runs/snapshots 链接用于回放。

---

## 6) 客户端集成点（自动打点）

* `plan.simulate`：将候选与评分写入**临时缓存**，以 `run_id` 关联。
* `plan.execute` 结束（或超时/失败）后：

  * 计算 `reward`、统计步数/耗时/等待时长/滚动次数；
  * 汇总 LLM 次数/Token（从现有 LLM 用量日志聚合）；
  * 一次性 `POST /plans/log`。
* **隐私**：不上传快照原图；仅上传结构化摘要（快照仍走原有可观测管道，并遵循脱敏）。

---

## 7) 回放（Replay）与控制台最小报表

* CLI：

  * `wf history --host ca.indeed.com --goal "apply job" --limit 20`
  * `wf replay --plan-id 777`（从 DB 读取候选、选择与事件；在 Web 控制台打开时间线与关键帧）
* 控制台“计划历史”页（最小）：

  * 维度筛选：host / goal / strategy / AB / 指纹；
  * 指标：成功率、平均步数、平均耗时、平均 reward、LLM 次数/成本；
  * Top 指纹与失败原因分布；
  * 点进详情可看：候选列表（分数/解释）→ 被选中候选 → 实际执行事件与快照。

---

## 8) 测试与验收

### 单元

* `test_fingerprint_stability`：轻微 UI 抖动（±2px）指纹不变；布局变化指纹变化。
* `test_reward_function`：达成目标增加分；增加步数/等待/滚动降低分；失败强负分。
* `test_history_schema_validation`：上传非法结构被拒。

### 集成

* `test_log_and_query`：模拟一次 D 的流程，上报→查询→字段完整。
* `test_replay_binding`：history 关联 run\_events/snapshots 正确。

### E2E（实机）

* Indeed “ai” 20 条职位；小红书 10 帖；微信 10 次回复：

  * 三条金路径均产生 `plans_history` 记录；
  * 控制台可按 **host/goal/策略**查看统计；
  * 任意挑 1 条记录可回放看到“候选—评分—选择—执行”的时间线。

**验收标准**

* 数据写入成功率 ≥ 99%（含断网重试机制）
* 指纹碰撞率低：相同页面结构应稳定映射；不同结构应区分
* 回放页面打开 ≤ 3s；关键帧可用

---

## 9) 任务拆解（建议分工）

* **Server（1人）**：DDL + `/plans/log`/`GET` 两个接口 + 事件消费器（如选择复用 run\_events）；索引/TTL。
* **Client（1人）**：指纹/奖励函数实现；`plan.simulate` 与 `plan.execute` 的打点与汇总上报。
* **Console（0.5人）**：历史查询页 + 最小指标卡片 + 回放入口。
* **QA（1人）**：单元/集成/E2E；基线对比与稳定性测试。
* **DevEx（0.5人）**：CLI（history/replay）；文档。

---

## 10) 风险与回退

* **指纹过于敏感** → 加强离散化与归一化；引入“软聚类标签”（把极近似指纹并到同组）。
* **数据量增长** → 分区表/TTL/候选 JSON 压缩存储；只保留评分摘要与被选候选的完整 JSON。
* **隐私/合规** → 仅结构化摘要入库；快照走既有脱敏与权限；支持历史删除（对用户请求）。
* **上报失败** → 本地 WAL/重试队列；服务端幂等键（`run_id + strategy + created_at bucket`）。

---

## 11) 与路线图对齐（不跑偏校验）

* 完全**兼容 D**：不改变 Mini-MCTS 流程，只是把“候选—评分—选择—执行”沉淀成数据资产；
* 为 **F（AgentQ）** 提供 `fingerprint → reward` 的历史先验；
* 为 **G（Full MCTS）** 提供回放/评测与成本/收益可视化依据；
* 保持安全边界与 HP/LP/SQS、不影响坐标点击与人类化执行。

---
Sprint F:
收到！先校准方向，确保不跑偏：

* 你已完成：A（坐标链路）、B（插件化+市场）、C（Micro-Plan）、D（Mini-MCTS：多候选+轻量模拟）、E（Plans History+Fingerprint+Replay）。
* **Sprint F 目标**：在 D/E 的基础上，上线 **AgentQ** —— 用“历史经验（Q 值）”重排候选，做到“越跑越聪明、越跑越省”。

下面给出**可直接执行的落地方案**。

---

# Sprint F｜AgentQ（基于经验的候选重排）

## 1) 目标（2 周）

* 在 `/llm/plan` 的 `strategy:"agentq"` 下，引入**Q 值先验**对候选做重排/剪枝，与 D 的模拟评分**融合**再选最优。
* 运行后**在线学习**：按每次执行的 `reward` 更新 Q 值（TD(0) 简化）。
* **灰度可回退**：任意工作流/设备粒度切换 `greedy | mcts-mini | agentq`。

---

## 2) 产出（Definition of Done）

* **Server**

  * `/llm/plan` 支持 `strategy:"agentq"`；返回 `candidates` 及 `agentq_scores`（先验分）。
  * Q 值存储与读取服务：`agentq_qvalues` 表 + 缓存层（Redis/LRU）。
* **Client**

  * `plan.simulate` 维持不变；在选优前与 Q 先验**做加权融合**。
  * 执行完成后：基于 E 的 `reward` 调用 `/agentq/update`（或复用 `/plans/log` 的后端消费者）更新 Q。
* **Workflow 配置（兼容 v1.2）**

  * `features.planner.strategy:"agentq"`；`features.planner.agentq = {alpha, epsilon, eta, decay, min_samples}`
* **可观测**

  * 新事件：`agentq.lookup`（命中/未命中）、`agentq.score`（先验分）、`agentq.update`（ΔQ）
* **测试与验收**

  * 在 Indeed/小红书/微信三条金路径上，连续多轮后**成功率↑、步数↓、LLM 次数↓**。

---

## 3) 数据库与缓存

### 3.1 表结构

```sql
CREATE TABLE agentq_qvalues (
  id            BIGSERIAL PRIMARY KEY,
  fingerprint   TEXT NOT NULL,          -- 来自 E 的 page_state_fingerprint
  action_sig    TEXT NOT NULL,          -- 动作签名（见下）
  q             DOUBLE PRECISION NOT NULL DEFAULT 0,
  n             INTEGER NOT NULL DEFAULT 0,   -- 样本数
  last_updated  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (fingerprint, action_sig)
);

-- 索引
CREATE INDEX idx_agentq_fp ON agentq_qvalues(fingerprint);
CREATE INDEX idx_agentq_fp_q ON agentq_qvalues(fingerprint, q DESC);
```

### 3.2 动作签名（action\_sig）

* 目的：把候选里的关键动作“抽象成模板”，便于统计与迁移。
* 规则建议（可扩展）：

  * `wheel@leftPane(-600)`、`wheel@leftPane(+600)`
  * `click@list[i]`、`click@list[i+1]`
  * `click@applyButton`（匹配 textAnyOf）
  * `wait@quiet(~1s)`
* 生成方式：对 MicroPlan 的前 K 步提取模板（K=2\~3），`action_sig` 用 `;` 连接形成**候选签名**；也可单步存 Q（推荐**单步**作为最小粒度，易复用）。

---

## 4) Server 侧接口与逻辑

### 4.1 `/llm/plan`（新增 agentq 模式）

输入新增：

```json
{
  "strategy": "agentq",
  "num_candidates": 3,
  "agentq": { "alpha": 0.6, "epsilon": 0.1, "min_samples": 5 }
}
```

* 生成流程：

  1. 按现有方式生成候选（与 D 一致，或让 LLM 直接给 3 条）。
  2. 为每个候选生成 `sig = [sig1, sig2, ...]`（单步或前缀）。
  3. **Q 查表**：对 `fingerprint` 下的每个 `sig` 取平均 `q_bar`，得到 `prior_q`。
  4. 计算**先验分**：`S_prior = agg(prior_q)`（如均值/加权和；无样本则 `null`）。
  5. 返回 `candidates` + `agentq_scores: [S_prior...]`。

响应示例：

```json
{
  "candidates": [ { /* MicroPlanV1 */ }, { ... }, { ... } ],
  "agentq_scores": [0.21, 0.55, null],
  "usage": {...}, "provider": "claude-3.5"
}
```

> 说明：**不在服务器做融合**，融合留给客户端（与 `plan.simulate` 分数结合）。

### 4.2 Q 更新（两种接入）

* 方案 A（推荐）：沿用 E 的 `/plans/log`，由**后端消费者**在入库时同步更新 Q。
* 方案 B：单独开放 `/agentq/update`，客户端提交 `{fingerprint, sig, reward}`；服务端做幂等/聚合。

**更新公式（TD(0) 简化）**
对每个单步 `sig`：

```
Q <- (1 - η) * Q + η * reward
n <- n + 1
```

* `η`（learning rate）可随 `n` 衰减：`η = max(η0 / sqrt(n), η_min)`
* **时间衰减**：周期性衰减 `Q := λ*Q`（λ=0.98/月）以适应页面变化

---

## 5) Client 侧融合与执行

### 5.1 评分融合（选择候选）

客户端拿到：

* `S_prior`：Server 返回的 AgentQ 先验分
* `S_sim`：D 阶段 `plan.simulate` 的模拟分
* 组成总分：

```
S_total = α * norm(S_prior) + (1 - α) * norm(S_sim)
```

* **探索（ε-greedy）**：以概率 `ε` 随机选一个非最优候选（或 Top-2 随机）
* 默认：`α=0.6, ε=0.1`（可配置），`min_samples` 未满足时降为 `α=0.2`（更依赖模拟）

事件打点：

* `agentq.lookup`：每个候选的 prior 命中情况、样本数
* `plan.simscore`：保留（D 已有）
* `agentq.score`：`S_prior` 与 `S_total`
* `plan.choice`：最终选择的 `idx`、`S_total`

### 5.2 执行与更新

* 正常执行 `plan.execute`（白名单/参数来源校验/HP 抢占）
* 结束后：由 E 的上报链路带上 `fingerprint`、候选 `sig 列表`、最终 `reward`，后端**批量更新 Q**

---

## 6) Workflow 配置（v1.2 向后兼容）

```json
{
  "features": {
    "planner": {
      "strategy": "agentq",
      "num_candidates": 3,
      "budget": { "max_steps": 5, "max_time_ms": 15000 },
      "agentq": {
        "alpha": 0.6,
        "epsilon": 0.1,
        "eta0": 0.3,
        "eta_min": 0.05,
        "decay": 0.98,
        "min_samples": 5
      }
    }
  }
}
```

---

## 7) 测试与验收

### 单元

* `test_sig_extraction`：不同候选生成稳定一致的 `action_sig`；微小坐标差不影响签名。
* `test_q_update`：TD(0) 更新、η 衰减、时间衰减效果正确。
* `test_score_fusion`：`S_total` 随 α/ε 变化合理；`min_samples` 触发降权。

### 集成

* `test_agentq_lookup`：有/无样本下的先验命中与分数。
* `test_fallback_to_sim`：无历史时仍靠 `plan.simulate` 选到可行路径。
* `test_plans_log_to_qupdate`：走 `/plans/log` 后端消费者自动更新 Q。

### E2E（实机）

* 场景：Indeed（AI 搜索坐标申请），重复运行 ≥ 50 次（可脚本化）
* 指标（与 D 基线对比）：

  * 成功率 ↑ ≥ 3–5%
  * 平均步数 ↓ ≥ 0.3 步
  * LLM 调用次数 ↓（因失败重试与不良候选减少）
* 小红书、微信各跑 20 次验证泛化（不过度依赖某域名）

**通过标准**

* 指标达到上述门槛；
* 失败不升高；
* 有任何异常可一键切回 `strategy:"mcts-mini"` 或 `greedy"`。

---

## 8) 风险与回退

* **数据稀疏**：`min_samples` 门槛 + 更依赖 `plan.simulate`；探索（ε）保持多样性。
* **页面结构漂移**：Fingerprint 漂移 → 结合“相似指纹聚类”（后续可做），当前先用时间衰减 + 无命中降权。
* **先验误导**：α 设上限（≤0.7），并保留 ε 探索；异常域名可策略黑名单。
* **成本上升**：`num_candidates` ≤ 3；LLM 走 AUTO；失败重试限额。
* **安全边界**：白名单/来源校验 unchanged；任何越权候选直接丢弃。

---

## 9) 任务拆分（建议分工）

* **Server（1人）**

  * DDL：`agentq_qvalues`
  * `/llm/plan` 扩展（返回 `agentq_scores`）
  * Q 更新消费者（从 `/plans/log` 入手）+ 缓存
* **Client（1人）**

  * `action_sig` 生成器（与候选解析）
  * 融合打分 + ε-greedy 选择
  * 事件打点与上报（沿用 E）
* **QA（1人）**

  * 单测/集成/E2E，基线对比与长跑统计脚本
* **DevEx（0.5人）**

  * 配置文档、回放页加入 `agentq` 先验/更新可视化

---

## 10) 与路线图对齐（不跑偏校验）

* **完全复用**：坐标点击、人类化、HP/LP、SQS、`plan.simulate`、Plans History。
* **仅新增**：先验 Q 值 → 候选重排与在线更新；灰度可回退。
* **为下一步 G（Full MCTS）** 提供**更强的先验与剪枝**能力，降低 MCTS 成本。

---

Sprint G:
收到！先对齐一下大图，防止跑偏：

* 已完成：
  A（坐标链路）→ B（插件化+市场）→ C（Micro-Plan 贪心）→ D（多候选+轻量模拟 Mini-MCTS）→ E（Plans History+Fingerprint+Replay）→ F（AgentQ：用历史 Q 值重排候选、在线学习）。
* 本次进入 **Sprint G：Full MCTS（受限深度的树搜索 + rollout + 回溯）**。
  目标：在复杂页面（多层弹窗、动态表单）中把成功率继续拉高，同时**严格成本/安全/HP 抢占**受控、可灰度回退。

---

# Sprint G｜Full MCTS（受限深度 + rollout + 回溯）

## 1) 目标（2 周）

* 在 Planner 侧引入**完整的蒙特卡洛树搜索**：选择（PUCT/UCT）、扩展（LLM/启发式提子动作）、**rollout（启发式或廉价 LLM 估值）**、回溯（累计 reward）。
* 与 **AgentQ**、**Mini-MCTS 模拟评分**深度融合：

  * 用 AgentQ 作为**先验概率/价值**的来源（剪枝和排序）。
  * 用 D 的 `plan.simulate` 作为轻量估值/rollout 的第一选择。
* 预算与安全：严格 `max_depth / max_nodes / max_time_ms`，动作白名单 + 参数来源校验，**步间 HP 抢占优先**。
* 失败可一键回退到 `agentq` 或 `mcts-mini`。

---

## 2) 交付物（Definition of Done）

* **Server**

  * `/llm/plan` 支持 `strategy:"mcts-full"`；可配置 `expand_width`, `max_depth`, `max_nodes`, `c_puct`, `rollout_policy`。
  * 扩展响应：返回**最优分支**（MicroPlanV1），并附搜索统计（节点数、深度、估值）。
* **Client**

  * 新增搜索器：`search/mcts.py`（完整树搜索）。
  * `plan.rollout`：启发式/廉价 LLM 估值接口；与 `plan.simulate` 复用。
  * `plan.execute` 无改动（继续白名单/来源校验/HP 让出）。
* **Workflow 配置（兼容 v1.2）**

  ```json
  {
    "features": {
      "planner": {
        "strategy": "mcts-full",
        "budget": { "max_depth": 6, "max_nodes": 60, "max_time_ms": 12000 },
        "mcts": { "expand_width": 3, "c_puct": 1.2, "rollout_policy": "simulate_then_cheap_llm", "rollout_limit": 3 }
      }
    }
  }
  ```
* **可观测**：新增事件 `mcts.select` / `mcts.expand` / `mcts.rollout` / `mcts.backprop` / `mcts.summary`；控制台展示**搜索树摘要**。
* **测试与验收**：复杂页面成功率较 F 再提升；成本与延迟符合预算；HP 抢占稳定。

---

## 3) 端到端流程（高层）

1. `ext.get_pagestate` → `fingerprint`（沿用 E）。
2. `/llm/plan strategy=mcts-full`（Server 或 Client 内部调度见下）生成：

   * 根状态 `S0`（PageState）
   * 循环直到 `max_time / max_nodes / max_depth` 任何触发：

     * **Select**：在树上用 **PUCT**（或 UCT）选一路到叶子；
     * **Expand**：调用**廉价 LLM 或启发式**提出 ≤`expand_width` 个子动作；融合 **AgentQ 先验** 排序；
     * **Rollout**：优先 `plan.simulate` 快速估值，不够时用**短上下文低成本模型**补估值（≤`rollout_limit`）；
     * **Backprop**：把 rollout 的 reward/value 回传到根，更新访问计数/价值；
     * 步间调用 `sched.cooperative.yield_if_hp_pending()`，保证 **HP 优先**。
3. 取根的最优子分支（或从根到当前最佳叶子的**可执行路径**），输出 **MicroPlanV1**。
4. `plan.execute` 落地执行（白名单/来源校验/HP 让出）。

> **注意**：整个搜索阶段不做真实点击，仅做模拟和估值；执行只发生在最终确定的路径上。

---

## 4) MCTS 细节设计

### 4.1 节点结构

```python
class Node:
    state_key: str           # 由 PageState 派生的“可搜索化”键（含可见项索引、按钮集合等）
    prior: float             # 来自 AgentQ 或启发式的先验概率（归一化）
    value: float             # 累计回传的价值均值
    visits: int
    action_from_parent: Optional[ActionSig]
    children: List[Node]
    is_terminal: bool
```

### 4.2 选择（PUCT）

```
UCB = Q(s,a) + c_puct * P(s,a) * sqrt(Σ_b N(s,b)) / (1 + N(s,a))
- Q = child.value
- P = child.prior（来自 AgentQ/Q 值 → softmax 归一；或 1/k 均匀）
- N = child.visits
```

### 4.3 扩展（Expand）

* 用**启发式**或**廉价 LLM**在叶子处生成 ≤ `expand_width` 个“下一步动作”。

  * 启发式：

    * 若目标是“让第 i 项进入可视并点击”，则优先生成：`wheel@leftPane(±)`、`click@list[i +/- δ]`。
    * 若目标是“寻找 Apply/发送按钮”，则优先生成：`ext.extract(find_button_bbox)`、`click@applyButton`。
  * LLM：使用短提示，限定动作白名单与参数来源描述（来自 PageState 的 rect 索引/标识）。
* 对每个候选动作生成 `action_sig`，查 **AgentQ**：

  * `prior = softmax(Q_sig / τ)`；无命中则 `prior = 1/k`。
* 新节点 `child.prior = prior_k`。

### 4.4 rollout（估值）

* 首选 **`plan.simulate`** 在虚拟状态上推演 1\~n 步（n ≤ `rollout_limit`），估计 reward。
* 若不确定（confidence 低）或命中零，调用**廉价小模型**（如相对更便宜的推理模型）给一个 `value_head` 分数（简短上下文：目标 + PageState 摘要 + 几个动作模板）。
* rollout 返回 `value ∈ [−1, +1]` 或按我们 reward 规范的有界值，统一线性归一化。

### 4.5 回溯（backprop）

* 从叶节点回到根，逐层更新：

  * `node.visits += 1`
  * `node.value = (node.value * (visits-1) + value) / visits`

### 4.6 终止与择优

* 终止条件：`nodes >= max_nodes` 或 `depth >= max_depth` 或 `elapsed >= max_time_ms`。
* 择优：

  * 若根节点已有子 → 选 `visits` 最大或 `value` 最大的子；
  * 把“根→该子→…→某一叶”的动作链压缩为 **MicroPlanV1**（≤5 步）。

---

## 5) 与 AgentQ / Mini-MCTS 的融合

* **先验（P）**：来自 AgentQ 的 Q 值（单步 `action_sig` 或短前缀），温度 τ 控制平滑（避免过拟合）。
* **价值（Q 起点）**：rollout 的返回值 +（可选）来自 AgentQ 的均值作为**偏置**。
* **剪枝**：若某候选 `prior` 很低且 rollout 也低，可直接剪去。
* **回退**：若在预算内搜索未得到“可执行路径”（或值太低），降级到 `agentq` 或 `mcts-mini` 的最佳候选。

---

## 6) 成本与 HP 抢占

* **预算**：默认 `max_nodes=60, max_depth=6, max_time_ms=12s, expand_width=3, rollout_limit=3`。
* **让出**：每次 `select/expand/rollout/backprop` 循环尾调用 `yield_if_hp_pending()`，HP 任务优先。
* **LLM 次数**：

  * 扩展：仅在确需时调用，优先用启发式。
  * rollout：先 `plan.simulate`；若 `confidence>=阈值`，不再调用 LLM。
* **日志**：统计每次搜索的 LLM 调用数，进入 `plans_history.llm_calls`。

---

## 7) 代码与目录增量

```
runtime/
├─ search/
│  ├─ minimcts.py          # 已有（D）
│  └─ mcts.py              # 新：Full MCTS 实现
├─ actions/
│  ├─ plan.rollout.py      # 新：封装 rollout 策略（simulate→cheap LLM）
│  └─ ...                  # 其余沿用
server/
├─ routes/llm.plan.ts      # 扩展 strategy=mcts-full 的参数解析与响应
└─ services/agentq.ts      # 读取 Q 值提供先验（已在 F，复用）
console/
└─ views/mcts_summary.tsx  # 新：搜索树摘要可视化（节点数/深度/价值热力）
```

**核心函数签名（示例）**

```python
# runtime/search/mcts.py
def search_mcts_root(ps, goal, constraints, mcts_cfg, agentq_provider, simulate_fn, rollout_fn, budget, yield_fn):
    root = Node(state_key=key_of(ps), prior=1.0)
    stats = Stats()
    t0 = now()
    while not budget.exceeded(t0, stats):
        yield_fn()  # HP 抢占
        leaf = select(root, mcts_cfg.c_puct)
        children = expand(leaf, ps, goal, mcts_cfg.expand_width, agentq_provider)
        for ch in children:
            v = rollout_fn(ch, ps, mcts_cfg.rollout_policy, mcts_cfg.rollout_limit)
            backprop(ch, v)
            stats.count_node()
    best = best_child(root)
    plan = to_microplan(best)
    return plan, stats
```

---

## 8) 示例工作流（复杂表单申请）

```json
{
  "version": "1.2",
  "start": "apply_flow",
  "features": {
    "planner": {
      "strategy": "mcts-full",
      "budget": { "max_depth": 6, "max_nodes": 60, "max_time_ms": 12000 },
      "mcts": { "expand_width": 3, "c_puct": 1.2, "rollout_policy": "simulate_then_cheap_llm", "rollout_limit": 3 }
    },
    "humanize": { "mouse": true }
  },
  "states": {
    "apply_flow": {
      "actions": [
        { "do": "ext.get_pagestate", "save": "ps" },
        { "do": "llm.plan",
          "strategy": "mcts-full",
          "allowed_actions": ["click_coordinates","wheel_coordinates","ext.extract","wait_for"],
          "constraints": { "max_steps": 5, "must_stay_in_host": "indeed.com", "no_dom_click": true },
          "inputs": { "page_state": "@ps", "context": {} },
          "schema": "MicroPlanV1",
          "save": "plan_mcts"
        },
        { "do": "plan.execute",
          "from": "@plan_mcts",
          "policy": { "allowed": ["click_coordinates","wheel_coordinates","ext.extract","wait_for"], "per_step_timeout_ms": 5000, "max_runtime_ms": 15000 },
          "save": "res"
        }
      ],
      "transitions": [
        { "if": "@res['ok']==true", "go_to": "done" },
        { "else_go_to": "fallback_agentq" }
      ]
    },
    "fallback_agentq": {
      "actions": [
        { "do": "llm.plan", "strategy": "agentq", "num_candidates": 3, "save": "plan_q" },
        { "do": "plan.simulate", "from": "@plan_q", "page_state": "@ps", "save": "choice" },
        { "do": "plan.execute", "from": "@choice['plan']", "save": "res2" }
      ],
      "on_success": "done"
    },
    "done": { "actions": [ { "do": "sleep_ms", "value": 200 } ] }
  }
}
```

---

## 9) 可观测与回放

* 新事件：

  * `mcts.select`（节点 key、UCB、depth）
  * `mcts.expand`（候选动作、AgentQ 先验、expand\_width）
  * `mcts.rollout`（策略、估值、confidence、是否触发廉价 LLM）
  * `mcts.backprop`（更新后 value/visits）
  * `mcts.summary`（nodes/depth/time/最佳分支）
* 控制台：在计划历史详情页展示“树摘要卡片”，并能点击查看最优路径与备选路径对比。

---

## 10) 测试与验收

### 单元

* `test_puct_selection`：PUCT 数值正确，访问计数影响选择符合预期。
* `test_expand_with_agentq_prior`：先验为 0/高/低 时排序与剪枝合理。
* `test_rollout_policies`：simulate→cheap LLM 的切换与 return 值范围正确。
* `test_budget_termination`：超节点/超深度/超时能正确终止。

### 集成

* `test_mcts_vs_agentq`：在 mock 复杂页面上 MCTS 胜过 AgentQ 的成功率/步数。
* `test_hp_preemption`：搜索循环能在 ≤50ms 内让出时间片处理 HP 任务。

### E2E（实机）

* 选一个“**多弹窗/表单**”页面（如求职流程二级弹框），比较三策略：

  * `agentq`、`mcts-mini`、`mcts-full`
* 指标（相对 F 基线）：

  * 成功率 ↑ ≥ 5–10%
  * 平均步数变化可接受（≤ +0.5 步）
  * 平均时延在预算内（p95 ≤ `max_time_ms` + 3s）
  * LLM 调用次数受控（不超预算 20%）

**验收标准**

* 达到上述指标；
* 任何异常可一键切回 `agentq`；
* 回放可复原“选择→扩展→rollout→回溯”的过程。

---

## 11) 任务拆解（建议分工）

* **Planner（1人）**：`search/mcts.py`、PUCT/节点管理/预算；与 AgentQ/Simulate/rollout 集成。
* **Server（1人）**：`/llm/plan` strategy 扩展；廉价 LLM 路由；统计字段。
* **Client-Exec（0.5人）**：与 `plan.execute` 对接、步间让出；可观测事件接入。
* **Console（0.5人）**：树摘要可视化卡片。
* **QA（1人）**：单/集/ E2E、对照实验脚本与报告模板。

---

## 12) 风险与回退

* **成本上升**：限制 `expand_width` 与 `rollout_limit`；优先启发式扩展；命中 AgentQ 高先验时**跳过 LLM 扩展**。
* **rollout 偏差**：simulate 的 confidence 低时才启用廉价 LLM；回溯加入不确定性惩罚。
* **搜索卡顿影响 HP**：每轮循环末尾强制 `yield`；设置最大单轮片长（≤ 30–50ms）。
* **页面大变动**：时间衰减 + 失败阈值触发自动回退为 `agentq`。

---

## 13) 与路线图对齐（不跑偏校验）

* 保持 **坐标点击/人类化/HP 优先/安全白名单** 的基线不变；
* 与 D（simulate）与 F（AgentQ）**融合**，不是替代；
* 可灰度、可回退；所有数据进入 `plans_history`，方便后续分析与继续学习。

---

