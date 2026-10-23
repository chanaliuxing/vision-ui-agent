# TODO（Planner 自愈 + 长期记忆）

优先级：✅ 已完成｜🟡 进行中｜📝 待办｜📌 建议

## 核心能力
- ✅ S 融合与参数：在 `core/workflow.py` 融合 `V1/V2/LLM`，env：`W_RULE`,`W_HINT`,`W_LLM`,`TH_PASS`。
- ✅ 跨页确认仲裁：`build_cross_confirm_messages`，在下一页二次确认并计入 S。
- ✅ 路由沉淀/重放：`RoutesStore` 记录成功路径；命中 anchors 直接复用。
- ✅ Deny 遮罩：对失败 id 区域半透明遮挡，降低 LLM 误选。
- ✅ Action Space v2（instr.*）：语义指令集，DOM优先+坐标回退（已落地）
- ✅ Chrome扩展集成：GetContent模块，DOM操作+签名验证（已落地）
- ✅ AutoFix机制：运行期热补+自动晋升（已落地）
- ✅ 工作流生成器（WAM/LLM）：链式构建+LLM生成（已落地）
- 📝 锚点增强（ORB/SIFT）：在 `core/anchors.py` 并行加入特征点匹配路径，阈值可调。
- 📝 OCR 验证规则：支持 `appear:text=...`/`disappear:text=...` 的 wait/verify 规则。
- 📝 URL hint：获取当前 URL（浏览器），并纳入 V2 评分。

## 回退与自愈
- 📝 回退动作：实现 `act_go_back()`（UI 返回键/浏览器后退）和 workflow op `go_back`。
- 📝 回退策略：S < TH_PASS 时优先后退；不可后退则重启 workflow；记录失败并加入 denylist。
- 📝 Planner 出场：基于 env 触发阈值（`WF_PLANNER_REPEATS`,`WF_PLANNER_NEED_INPUT`,`WF_PLANNER_DENY_THRESH`），产出微目标并试探。

## 记忆与存储
- ✅ Sprint H：RAG轨迹检索+在线Reflexion（已实现，pgvector+嵌入服务）
- ✅ MemoryStore：PostgreSQL数据库存储，支持向量检索
- ✅ RoutesStore：routes.jsonl 记录成功路径与锚点信息
- ✅ 嵌入服务：多提供商支持（OpenAI/SentenceTransformers）
- 📝 归档与压缩：定期滚动归档、超量裁剪、只读快照用于离线评估。

## 观测与复盘
- 📝 指标：错误点击率、LLM 次数/步、锚点命中率、平均步数、回退率、重跑率。Reporter 汇总导出。
- 📝 离线重放：基于 `overlay.png + yolo.json + picker_req/resp.json + confirm_req/resp.json` 的重放脚本。

## 开发任务拆解（本周）
1. ✅ 融合/权重暴露与文档：CLAUDE.md 和 SYSTEM_DOCUMENTATION.md 完成。
2. ✅ Sprint H-K 实现：RAG记忆、DPO训练、技能库、多模态理解全部落地。
3. ✅ Action Space v2：instr.* 语义指令集，DOM优先+坐标回退。
4. ✅ Chrome扩展集成：GetContent模块，DOM操作+签名验证。
5. ✅ AutoFix机制：运行期热补+自动晋升。
6. ✅ 工作流生成器：WAM链式构建+LLM生成工具。
7. ✅ CLI工具集：Sprint H-K 专用工具完成。
8. 📝 ORB/SIFT 锚点：`anchors_from()/anchors_match()` 增加特征路径与阈值配置。
9. 📝 OCR 验证：扩展 `act_wait_for()` 支持 `appear:text=...` 简单子串匹配（依赖 OCR API）。
10. 📝 回退动作：新增 `act_go_back()`（macOS: `⌘+[` 或 AppleScript；Windows: `Alt+←`），并在 S 不通过时调用。
11. 📝 URL hint：增加获取 URL 的小工具（Chrome/Safari），并纳入 V2。
12. 📝 指标采集：Reporter 统计并写入 run_report。
13. 📝 离线重放工具：`tools/replay_run.py`（读日志工件进行模拟）。

## 参考代码位置
- `core/workflow.py`：S 融合、跨页确认、deny 遮罩、路由沉淀与重放、planner 触发。
- `core/prompt_builder.py`：`build_cross_confirm_messages()`、planner 提示。
- `core/anchors.py`：anchors 模板匹配（需扩展 ORB/SIFT）。
- `core/memory.py`：短期记忆与黑名单。
- `core/reporter.py`：运行工件与报告（需扩展指标）。

---

## 新增：锚点自动选择 + 跨页确认 + 二次复用（专项落地）

### 设计与实现任务
- 📝 auto_select_anchors(img, bbox, ocr, siblings)
  - 生成候选：模板（周边小块 2–3）、ORB/SIFT、OCR 文本与相对坐标、结构偏移（Δx,Δy,w,h）。
  - 打分：唯一性 U（全页命中数）、稳定性 S（增强后命中率）、区分度 D（对同名兄弟的分离度）。
  - 选优：类型互补 Top-2/3，强制包含 row-key。
- 📝 hierarchical anchors（Row + Action + Relation）数据结构与序列化（JSONL）。
- 📝 locate_instance(img, row_anchor, action_anchor, relation) 执行时匹配与几何校验。
- 📝 state_anchors 生成：进入第二页后自动选取标题/图标/LOGO 等稳定锚，vote_k=2/3。
- 📝 cross_page_confirm() 融合：w1·本地 + w2·命中率 + w3·LLM_conf，落地 env 权重/阈值。
- 📝 预检/微验证：hover/probe 200–300ms 高亮/tooltip；点击后亮度/置灰/Loading/Toast。
- 📝 自适应阈值：成功抬高/失败下调，按分布自适应（每锚点独立维护）。
- 📝 次页确认失败的回退策略：优先 UI 返回 → 浏览器后退 → 工作流重启；同时更新 deny 与 fail_log。

### 配置与阈值（默认建议）
- 模板阈：`ANCHOR_TM_TH=0.82`；特征比率：`ANCHOR_ORB_RATIO=0.75`；最少 inliers：`ANCHOR_ORB_INLIERS=12`。
- OCR 子串：`ANCHOR_OCR_MINCONF=0.78` 或 `LEVENSHTEIN_MAXDIST=2`。
- 关系容差：`ANCHOR_REL_TOL_X=0.15`（相对 Row 宽）、`ANCHOR_REL_TOL_Y=0.15`。
- 次页投票：`STATE_ANCHOR_VOTE_K=2`（总 3）。
- 合取阈：`TH_PASS=0.7`；`W_RULE=0.35,W_HINT=0.45,W_LLM=0.20`（按需调）。

### 集成点（代码改动建议）
- `core/workflow.py`：
  - 在 autostep 成功点击后：生成复合锚与 state_anchors；S≥TH_PASS 时 promote 到 RoutesStore。
  - 在 autostep 开头：尝试用复合锚 locate_instance，命中即跳过 LLM；失败再回退 YOLO+LLM。
  - 在跨页验证阶段：加入 state_anchors 命中率计算并写入 S。
- `core/anchors.py`：新增 ORB/SIFT 路径；行锚/动作锚/关系锚结构；匹配与评分；自适应阈值存储。
- `core/memory.py`：记录成功/失败，维护 deny 与锚点权重/阈值的历史（可与 routes 合并或并行存储）。
- `core/reporter.py`：增加锚点匹配得分、投票结果、S 分解项的可视化与导出。

### 验证与评估
- 📝 用小红书“发长文”流：
  - 场景 A：同名按钮多实例（列表行）—验证 row+action+relation 定位正确率；
  - 场景 B：进入编辑器页—验证 state_anchors 一致性；
  - 指标：误点率、LLM 调用次数/步、锚点命中率、回退率、平均步数。

---

## 收尾清单（高优先，Definition of Done 前必须完成）

1) Loading/Toast 检测器（从启发式到小模板）
- 📝 收集 8–12 个组件模板（骨架屏/转圈/短 Toast），封装 `core/detectors.py`：`detect_loading(bgr)`, `detect_toast(bgr)`；
- 📝 支持 verify.rules: `appear/disappear:loading|toast`；
- 📝 报表：在步骤卡片显示命中的模板名称/分数。

2) Modal 显式识别（modal-sig）
- 📝 新增 `modal_sig(bgr)`：遮罩直方图/边缘特征 + ESC 关闭探测；
- 📝 `sig_stack` 改为基于 modal-sig 入栈/出栈；路由记忆包含 `modal=true/false`；
- 📝 报表记录 modal 入栈/出栈事件与截图。

3) 报表可观测性增强
- 📝 HTML 增加“逐步 S/Vote 表”：每步显示 `S(V1/V2/LLM)` 与 `state_vote(模板/OCR/URL)`；
- 📝 汇总卡片：显示 direct-run、downgrade、error-click、go_back 成功率（已部分实现，补全表格化）。

4) OCR 锚点几何化
- 📝 从 app_ocr 读取行/字框多边形；
- 📝 state_vote 使用 IoU/置信度加权（而非纯文本）；
- 📝 报表高亮命中字框，显示分数与文本。

5) Anchor Health 与自动替换
- 📝 为每条 route 维护滑动窗口命中率（如近 N=50 次）；
- 📝 命中率 < 阈值 自动触发 `auto_select_anchors()` 重新选锚并替换；
- 📝 报表显示 anchor 更替历史、阈值变化与健康度趋势。

6) 自动化 Smoke/回归套件
- 📝 一键脚本 `tools/smoke_suite.py`：同名多实例、轻改版、±10% 缩放、明暗主题、模态、网络慢速；
- 📝 产出门槛报告：Direct-run ≥85%、Downgrade ≤10%、Error-click ≤1%/步、Go-back ≥80%；
- 📝 可选 CI 集成：低于阈值即失败。

## DoD（发布门槛）
- Direct-run（无 LLM）≥ 85%；Downgrade ≤ 10%；Error-click ≤ 1%/步；Go-back ≥ 80%。
- S 通过率 ≥ 97%；Danger 双确认 漏判 < 1%，误阻 < 2%。
- LLM 调用较基线下降 ≥ 50%；p95 步时 ≤ 3–5s。
- routes.jsonl 滚动切段，无单文件 >100MB；回放一致性 100%。
