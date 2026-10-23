# 自愈工作流 + 长期记忆 Roadmap

本路线图把“自愈工作流（planner/重试/回退）”与“长期记忆（路径沉淀/锚点复用）”合并，目标是在重复性任务上尽量减少 LLM 参与，实现稳定、可回放的自动化。

## 目标
- 首次运行：YOLO 检测 + 选点 LLM 探路，下一页用仲裁 LLM 交叉确认，沉淀正确路径。
- 后续运行：优先使用锚点模板直接定位 + 轻量规则验证，通过则不调用 LLM；漂移时再回退到 LLM。
- 长期：路径越跑越稳，LLM 次数逐步下降，趋近脚本化。

## 正确性的判定：多信号合取 S
- 公式：S = w1*V1 + w2*V2 + w3*LLM_confidence；S ≥ TH_PASS 视为“正确”。
- V1 硬信号（规则验证）
  - page_change（pHash/布局差异）
  - 元素出现/消失（OCR/小图标模板）
  - 状态变化（按钮高亮/置灰/Loading/Toast）
- V2 弱硬信号（期望跳转）
  - URL host/path 提示（可用则纳入）
  - 页面签名相似度 ≥ 阈值（容忍小改版）
- V3 软信号（LLM 下一页仲裁）
  - 把“上一页 overlay+点击框 + 当前页截图 + 上一步目标”发给 LLM，返回严格 JSON：
    {"is_expected":true|false,"prev_action_ok":true|false,"detected_state":"…","expected_state":"…","confidence":0.xx,"why":"…"}

实现现状（core/workflow.py）：
- 已支持：S 融合与权重/阈值（env：`W_RULE`, `W_HINT`, `W_LLM`, `TH_PASS`）。
- 已支持：跨页确认 `build_cross_confirm_messages`，并融合到 S。

## 双调用结构（落地）
- 第一次（选点）：视觉优先的 Picker，按遮罩 id 选 `click_id`；不确定返回 NEED_INPUT（已实现）。
- 第二次（跨页确认）：在下一页调用仲裁 LLM，比较上一页点击与当前页状态，给出 `confidence` 与结论（已实现）。

## 记忆与复用：路径 → 锚点模板
- Promote 条件：S ≥ TH_PASS。
- 记录内容：page 签名、目标、点击 det id/bbox、verify 规则、next_sig_hint、anchors。
- 锚点生成 anchors_from（已实现 template 匹配）：
  - 以点击框附近 ROI 生成模板（`TM_CCOEFF_NORMED`），保存 PNG 与 ROI、阈值。
  - TODO：并行加入 ORB/SIFT 特征路径以提升鲁棒性。
- 命中逻辑 anchors_match（已实现 template）：
  - 模板得分 ≥ 阈值 → 直接复用（无 LLM）；否则回退 YOLO+LLM → 成功后更新阈值/模板。

## 主循环（与代码映射）
- 签名：`_signature()` = phash_tiles + yolo_hist（core/workflow.py）。
- 记忆：MemoryStore（`out/logs/memory.jsonl`），黑名单/摘要提示（已实现）。
- 路由：RoutesStore（`out/logs/routes.jsonl`），成功路径沉淀、重放（已实现）。
- Planner：卡壳触发（重复/deny/need_input），给出微目标（已实现入口与消息）。
- Deny 遮罩：对失败 id 区域半透明遮挡，降低 LLM 误选（已实现）。

## Planner 触发与修正
- 触发条件（env，可调）：
  - 同签名连续重复：`WF_PLANNER_REPEATS`（默认 3）
  - NEED_INPUT 次数：`WF_PLANNER_NEED_INPUT`（默认 2）
  - Deny 数量：`WF_PLANNER_DENY_THRESH`（默认 3）
  - 规划最大调用数：`WF_MAX_PLANNER_CALLS`（默认 2）
- 行为：产出 2–4 个微目标，每个带一行检测条件；试探-验证-沉淀到记忆。

## 工程细节与状态
- 签名稳健：phash tiles + yolo_hist（已实现）。可扩展 layout_grid_hash / OCR 片段（TODO）。
- Deny 可视降权：半透明遮罩 + 内部黑名单（已实现）。
- 双确认保护：危险操作（发布/删除）触发二次确认（TODO 细化危险词表/策略）。
- 记忆 TTL：成功长期、失败短期 TTL 与压缩（MemoryStore 基础已具备，TTL/归档 TODO）。
- 离线重放：保存 overlay/yolo/picker/confirm，请求/响应 JSON（已保存核心工件；离线回放工具 TODO）。
- 指标：错误点击率、LLM 次数/步、锚点命中率、平均步数、回退/重跑率（Reporter 里补充计数/导出 TODO）。

## 近期里程碑（MVP）
1) 跨页确认接口 + S 融合 + 权重/阈值（已落地，env 可调）。
2) 锚点匹配增强：在 anchors 中加入 ORB/SIFT 路径（TODO）。
3) 记忆结构完善：成功/失败分轨存储与 TTL、归档（部分具备，优化 TODO）。
4) Deny 遮罩策略（已落地）。
5) 回退策略：UI 返回/浏览器后退/重启的统一实现与策略注入（TODO）。

## [高优先级] 策略选择层（Strategy LLM + 通用算子）

目标（兼容性 & 成本）
- 跨场景泛化：基于相对地标/属性/序号/几何关系的“策略锚”，弱化对易变文本/人名的依赖。
- 可控 LLM：LLM 仅选“策略”，不返回像素坐标；像素定位由系统（YOLO/OCR/Template/ORB）执行。
- 低 Token：仅在新签名/卡死/歧义时触发一次策略选择，其余走本地 CV + 记忆复用。

组件与调用关系
- 已有：Picker LLM（选点）、Arbiter LLM（跨页确认）
- 新增：Strategy LLM（选“策略”，严格 JSON，无坐标）

策略库（可扩展 ID）
- LIST_TOPMOST_WITH_ATTR(attr)
- NEAREST_BELOW(landmark)
- NTH_IN_CONTAINER(container, n)
- TEXT_MATCH_NEAREST(text, landmark)
- GRID_BY_ROWCOL(container, r, c)
- FORM_FIELD_BY_LABEL(label)
- TAB_SWITCH_BY_TITLE(title)
- ACTION_IN_ROW(row_attr, action_role)
- FIRST_RESULT_BELOW_SEARCH(container?)
- LATEST_ITEM_BY_TIME(container?)

结构化算子（系统执行）
- 空间：within/below/right_of/nearest_to/ordinal
- 归组：cluster_list/group_by_rows/gridize
- 属性：has_attr(unread|badge|selected|sponsored)（掩膜模板+颜色/形状/OCR 推断）
- 选择：sort_by_y/topmost/nth/text_match
- 落点：click_region(target, role=row|action)（复用 ORB→SIFT→Template 和 Relation）
- 验证：状态锚投票 + V1/V2 + Arbiter

触发条件（严格）
- 新页面签名（memory 未见）
- 歧义：候选 > 1 且 CV 分数拉不开
- 漂移/改版：复用失败 ≥ N 或 state_vote 不足
- Planner 触发：卡死后微目标建议需要策略更新
（其余时间直接用记忆策略 + 本地算子，零 LLM）

I/O 协议（严格 JSON，可缓存）
- 输入：签名摘要（page_kind/url_hint/top_ocr）、候选地标（YOLO+OCR）、检测摘要（Top-K 类计数/少量框元数据）、任务、一行历史 hint
- 输出：{strategy_id, params{...}, fallback?, confidence, why}（严禁返回坐标）

系统执行（策略→像素）与锚点结合
1) 地标定位 → 2) 聚类/筛选/排序/序号 → 3) Action 锚生成与点击 → 4) 验证与 promote → 5) 自愈回退与替换

记忆与老化（策略维度）
- key=(page_signature, goal) → strategy_json + confidence_ema；失败衰减、TTL 老化、健康阈值回退/复询。

成本控制
- Strategy 只传结构摘要，不发整图；命中记忆 0 调用；三 LLM 分别限流；缓存 (sig,goal,landmark_hash,yolo_hist_hash) → strategy。

交付标准（DoD）
- 通用任务集 PASS：未读/首条/Tab/表单下一步/第一卡片
- 直达率（无 Picker/Arbiter）≥ 85%；降级 ≤ 15%；策略重用命中 ≥ 90%；错误点击 ≤ 1%/步；Planner 触发 ≤ 5%

里程碑
1) 框架落地：core/strategy_selector.py + core/ops.py + core/landmarks.py（骨架/缓存/时间线埋点）
2) 3 个策略原型：FIRST_RESULT_BELOW_SEARCH / LIST_TOPMOST_WITH_ATTR / NTH_IN_CONTAINER
3) 规则触发与缓存：新签名/歧义/失败复询，仅一次触发；其余命中记忆
4) 集成验证：状态锚投票 + Arbiter 降级；DoD 指标达标

---

参考模块
- `core/workflow.py`：主循环、S 融合、跨页确认、deny 遮罩、路由沉淀/重放。
- `core/prompt_builder.py`：Picker/Planner/跨页确认提示构建。
- `core/anchors.py`：anchors_from / anchors_match（模板匹配）。
- `core/memory.py`：短期记忆与失败黑名单。
- `core/reporter.py`：运行工件与报告。

---

## 完成版收尾（Remaining + DoD）

### 验收项（Remaining Requirements）
- Loading/Toast 检测强化：由启发式升级为“小模板/微形态”检测（骨架屏、旋转圈、短 Toast 组件），降低假阴/假阳；与 verify.rules 的 `appear/disappear:loading|toast` 打通。
- Modal 显式识别：将“模态栈”从启发式改为显式 modal-sig/overlay 探测（遮罩/阴影/边框/ESC 可关闭）并写入签名与路由；入栈/出栈事件可观测。
- 报表可观测性：HTML 报表逐步渲染 S 分解（V1/V2/LLM）与 state_vote 命中详情（模板/OCR/URL），支持审计/灰度。
- OCR 锚点几何化：state_vote 使用行/字框多边形与 IoU/置信度加权，而非纯文本；报表高亮命中字框。
- 路线健康度与自动替换：在 EMA 之外增加滑动窗口命中率与自动换锚策略；显示 “anchor health” 趋势与更替历史。
- 自动化 Smoke/回归：一键跑 6 组场景（同名多实例、轻改版、缩放、主题、模态、网络慢速），输出 Direct-run、Downgrade、Error-click、Go-back 等核心指标。

### Definition of Done（发布门槛）
- Direct-run 直达率（无 LLM）≥ 85%（标准任务集，暗/亮主题、缩放±10%、微改版混测）。
- Downgrade→LLM ≤ 10%；错误点击率 ≤ 1.0%/步；go_back 恢复成功 ≥ 80%（注入错误场景）。
- 跨页判定 S 通过率 ≥ 97%；Danger 双确认漏判 < 1%，误阻 < 2%。
- Planner 触发率 < 5% 于正常路径；触发后修复成功 ≥ 70%。
- 成本/时延：LLM 调用量较基线 下降 ≥ 50%；p95 步时 ≤ 3–5s（不含页面加载）。
- 稳定性：routes.jsonl 滚动切段，无单文件 > 100MB；回放一致性 100%。

### 立刻可做的收尾清单（优先级从高到低）
1) 小模板 Loading/Toast 检测器：收集 8–12 个常见组件模板，阈值化+备选模板；verify.rules 全面打通；报表展示。
2) 显式 Modal-sig：遮罩直方图/边缘特征 + ESC 关闭探测 → 入栈/出栈记录 + 报表事件。
3) HTML 报表渲染表格：每步 S(V1/V2/LLM)、state_vote（模板/OCR/URL 子分），最终判定/路径来源（compound/legacy/llm）。
4) OCR 多边形锚：vote 使用字框 IoU 与置信度加权；命中字框在报表中高亮。
5) Anchor Health 策略：窗口命中率 < 阈值自动触发 re-select & 替换；显示更替历史与趋势曲线。
6) Smoke/回归脚本：一键运行 6 组场景，输出 DoD 指标与对比报告；CI 集成阈值门禁。

---

## AI 自动选锚点 + 跨页确认 + 二次复用（同名按钮/第二页确认专题）

### 0) 结论
- 锚点是“复合锚点集”（Row 行锚 → Action 动作锚 → Relation 关系锚），辅以多模特征（模板/特征点/OCR/几何）。
- “点对没”采用多信号合取：局部状态变化 + 第二页状态锚点命中 +（可选）LLM 仲裁。
- 记忆“正确路径”包含【上一页复合锚】与【下一页状态锚】，下次直接匹配，无需 LLM。

### 1) AI 自动选锚点（bbox 周边 → 候选 → 打分 → 选优）
- 候选类型：
  - Template 模板：bbox 周边裁 2–3 个稳定小块（图标/边角/纹理）。
  - 特征点：ORB/SIFT 多尺度，保存 desc 哈希。
  - OCR 文本：按钮文本与邻近关键字，保存 token+相对位置信息。
  - 结构：与行元素（标题/价格/作者/缩略图）的 Δx,Δy,w,h 关系约束。
- 打分：
  - 唯一性 U：全页快速匹配命中数 n → U=1/(1+n)。
  - 稳定性 S：增强（缩放/亮度/旋转/模糊）后命中率。
  - 区分度 D：与兄弟（同名按钮其他行）的可分性 D=1-max(sim_to_siblings)。
  - 综合：Score=αU+βS+γD（α=0.5,β=0.3,γ=0.2）。
- 选择策略：Top-2/3 且类型互补（模板/特征/文本至少各 1），必须包含“行键锚（row-key）”。

### 2) 避免同名按钮误点（列表多实例）
- 层级锚点集：Row（必选）+ Action（必选）+ Relation（必选）。
- 执行匹配：
  1) 全页匹配 Row（文本+模板综合，n>1 取最高）。
  2) 在 Row 局部窗口匹配 Action。
  3) Relation 几何误差 < 阈值（σx/σy/比例）。
- 阈值自适应：成功抬高、失败下调，记录分布做自适应边界。

### 3) 第二页确认与状态锚（State Anchors）
- 次页自动生成全局稳定锚：标题/面包屑（OCR）、关键图标（模板+特征）、独特纹理/LOGO（模板）。
- 以“多模三选二”投票（vote_k=2/3），形成“状态签名”。
- 确认流水线：
  1) 本地轻验证（toast/高亮/Loading）
  2) LLM 仲裁（上一页 overlay+点击 JSON+当前页图+微目标）→ confidence
  3) 状态锚命中率 → 比例分
  4) S = w1·本地 + w2·命中率 + w3·LLM_conf，S≥TH_PASS 判定“点对了”。
- 记录跨页边（A→B）：把【A 页复合锚】与【B 页状态锚】一起写入记忆，供下次无 LLM 重放。

### 4) 数据结构建议
```json
// 第二页状态锚
{"state_sig":"B:...","goal":"publish_longform","anchors":[
 {"type":"template","roi":[x,y,w,h],"sha":"...","th":0.84},
 {"type":"orb","roi":[x,y,w,h],"kpts":512,"desc_sha":"...","ratio":0.75},
 {"type":"ocr","text":"编辑器","bbox":[x,y,w,h],"mode":"substring"}
],"vote_k":2}

// 跨页边（A→B）
{"from_sig":"A:...","to_state_sig":"B:...",
 "row_anchor":{...},"action_anchor":{...},
 "relation":{"dx":120,"dy":0,"tol_x":18,"tol_y":12,"scale_tol":0.15},
 "verifiers":["page_change","appear:text=标题"],
 "stats":{"success":7,"fail":1}}
```

### 5) 核心伪代码
```python
def auto_select_anchors(img, bbox, ocr, siblings):
    # 生成模板/特征/OCR 候选 → 计算 U/S/D → 选互补 Top-K
    ...

def locate_instance(img, row_anchor, action_anchor, relation):
    # Row→局部窗口→Action→Relation 校验
    ...

def cross_page_confirm(prev_overlay, curr_img, local_verify, state_anchors, llm_conf=None):
    # 多信号合取评分并阈值判定
    ...
```

### 6) 点击前后的保险丝
- 预检（hover/probe 200–300ms）：看高亮/光标变化/tooltip。
- 点击后微验证：亮度/置灰/Loading/Toast。
- 不通过→回退（优先 UI 返回）并加入 deny；必要时重启工作流。

### 7) 初始阈值建议
- 模板匹配：TM_CCOEFF_NORMED ≥ 0.82。
- ORB 比率：ratio ≤ 0.75 且 inliers ≥ 12。
- OCR 子串：Lev 距离 ≤ 2 或 OCR 置信度 ≥ 0.78。
- 关系容差：tol_x=0.15·w_row，tol_y=0.15·h_row。
- 跨页通过：TH_PASS=0.7；权重 w1=0.35,w2=0.45,w3=0.20。

### 8) 实践要点
- 列表虚拟化：用行文本当 row-key，必要时小步滚动补搜。
- 亮/暗主题：模板保存双版本；特征锚跨主题更稳。
- DPI/缩放：统一归一化（长边 1280/1440），按比例修阈。
- 锚点老化：失败≥2 或连续不匹配降权；成功多次后晋升主锚。
- 多语言：OCR 文本锚存多语言同义词。

### 9) 最小集成路线
1) 首次：YOLO+LLM 选点 → auto_select_anchors 产出 Row+Action+Relation 与 state_anchors → 点击 → cross_page_confirm → 通过即写入记忆。
2) 下次：locate_instance 直接点击；到第二页用 state_anchors 验证；不符再回退到 YOLO+LLM 并更新锚点/阈值。
3) 失败：回退或重启，并记录硬失败与 deny。
