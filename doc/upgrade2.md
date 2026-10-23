你一套**可以马上开工的落地计划**，把**RAG 轨迹检索 + Reflexion（自我反思）+ DPO/RLAIF 离线训练**逐步拉通。按之前节奏，我把它拆成**Sprint H / I / J**，每个都有目标、交付物、接口/表结构、示例、测试与验收、风险与回退。你只要把任务分给对应同学就能动起来。

---

# Sprint H｜RAG 轨迹检索 + 在线 Reflexion（2 周）

**目标**

1. 让 Planner 在生成计划前能**检索历史成功轨迹**（基于 E 阶段的 plans\_history），把“相似成功片段”当参考；
2. 引入**在线 Reflexion**：当执行失败或 reward 偏低时，自动产出“反思短评”，下次计划时纳入提示，快速纠错。

## 产出（DoD）

* **DB & 索引**：在 `plans_history` 增加向量字段（pgvector 或 Milvus），存 `fingerprint_embed` 与 `trajectory_embed`。
* **Embedding 服务**：`/embeddings/batch`（后端离线/在线均可调用）。
* **Recall API**：`GET /plans/recall?fingerprint=...&k=5` 返回 Top-k 成功轨迹摘要（步骤模板、关键 bbox 模式、平均 reward）。
* **新动作**：

  * `mem.recall`：在工作流里拉取相似案例（供 `llm.plan` 参考块）。
  * `plan.reflect`：当 `plan.execute` 失败或 reward 低时，生成短评（critique + 修正建议）落库。
* **Workflow 配置**（兼容 v1.2）：

  ```json
  {
    "features": {
      "planner": {
        "strategy": "agentq", 
        "memory": { "rag": true, "k": 5, "use_reflexion": true, "reward_threshold": 0.5 }
      }
    }
  }
  ```
* **CLI**：`wf recall --host ca.indeed.com --goal "apply job"`；`wf reflect --run-id 123`。
* **可观测**：事件 `mem.recall`（命中条数、相似度分布）、`plan.reflect`（短评摘要）。

## 表结构与迁移（示例）

```sql
-- 向量列（pgvector）
ALTER TABLE plans_history ADD COLUMN fingerprint_embed vector(768);
ALTER TABLE plans_history ADD COLUMN trajectory_embed  vector(768);

CREATE INDEX idx_ph_fpvec ON plans_history USING ivfflat (fingerprint_embed vector_cosine_ops);
CREATE INDEX idx_ph_trvec ON plans_history USING ivfflat (trajectory_embed  vector_cosine_ops);

-- 反思表
CREATE TABLE plan_reflections (
  id BIGSERIAL PRIMARY KEY,
  history_id BIGINT REFERENCES plans_history(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT now(),
  critique TEXT NOT NULL,
  suggestions JSONB,
  reward_before DOUBLE PRECISION,
  tags TEXT[]
);
```

## 服务与动作（接口）

* `GET /plans/recall`：入参 `fingerprint`（或 ps 摘要），可带 `goal/host/strategy` 过滤；出参包含**步骤模板**（动作签名序列）、平均 reward、示例片段。
* `POST /plans/reflect`：由客户端在失败/低奖赏时调用，或后端根据 `/plans/log` 自动触发。
* `mem.recall` 动作参数：`{ goal, fingerprint, k, filters } -> save: recall_refs`
* `llm.plan` 追加字段：`references: recall_refs`（作为提示块注入）。

## 工作流示例（节选）

```json
{
  "actions": [
    { "do": "ext.get_pagestate", "save": "ps" },
    { "do": "mem.recall", "goal": "apply current item", "fingerprint": "@fingerprint(@ps)", "k": 5, "save": "refs" },
    { "do": "llm.plan", "strategy": "agentq", "references": "@refs", "save": "cands" },
    { "do": "plan.simulate", "from": "@cands", "page_state": "@ps", "save": "choice" },
    { "do": "plan.execute", "from": "@choice['plan']", "save": "res" },
    { "do": "plan.reflect", "when": "@res['ok']==false || @res['reward'] < 0.5", "save": "rx" }
  ]
}
```

## 测试与验收

* 单元：向量检索命中稳定性；RAG 引入后 `llm.plan` 的候选更贴近历史模板。
* 集成：Recall→Plan→Execute 成功率相对 F 基线 ↑ ≥3%，LLM 计划 token ↓。
* E2E：Indeed/小红书/微信三条金路径均验证；失败时生成反思短评并能在下一次被引用。

## 风险与回退

* 检索误召回：加阈值与过滤（只用成功 reward>阈值的轨迹）。
* 成本上升：限制 `k<=5`，引用片段仅摘要（不含大图）。
* 无历史：自动降级为 AgentQ + simulate（D/F）。

---

# Sprint I｜DPO / RLAIF 离线训练与上线（2–3 周）

**目标**

1. 基于 E/H 的历史与反思，产出**偏好对 (A > B)**，执行**DPO 微调**（或 Prompt 调优）；
2. 引入**Teacher 打分（RLAIF）**，在缺人标注时用老师 LLM 生成偏好；
3. 灰度发布新版 Planner 策略，成本与收益可观测、可回退。

## 产出（DoD）

* **数据生成器**：从 `plans_history` 采偏好对：

  * 同一 fingerprint 下，选 `reward` 更高的候选/轨迹为 **preferred**，低的为 **rejected**；
  * 结合 `plan_reflections` 作为反例注解。
* **训练流水线**：`/trainer/dpo/run`（离线 Job 或 Airflow/Dagster）

  * 目标对象：

    * 方案 A（轻量）：Planner Prompt 模板（few-shot + 策略指令）自动化**Prompt 优选**；
    * 方案 B（进阶）：小型策略模型（LoRA/参数高效），输出 MicroPlanV1。
* **Teacher（可选）**：`/teacher/score` 给候选 plan/轨迹打分，生成 pseudo-preference（RLAIF）。
* **模型/Prompt 版本管理**：`models/planner_versions` 表 + 灰度开关（租户/域名/设备级）。
* **AB/回退**：`/deploy/ab` 指定某域名走新版本 10–20%，失败阈值自动回退。

## 表结构（示例）

```sql
CREATE TABLE planner_versions (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ DEFAULT now(),
  name TEXT NOT NULL,
  type TEXT NOT NULL,           -- "prompt" | "lora"
  path TEXT NOT NULL,           -- 存储路径
  base_provider TEXT NOT NULL,  -- "claude-3.5" | "gpt-4o-mini" | ...
  notes TEXT,
  status TEXT NOT NULL          -- "staging" | "prod" | "rollback"
);

CREATE TABLE ab_assignments (
  id BIGSERIAL PRIMARY KEY,
  host TEXT NOT NULL,
  strategy TEXT NOT NULL,       -- agentq | mcts-full | ...
  planner_version_id BIGINT REFERENCES planner_versions(id),
  traffic_pct SMALLINT NOT NULL DEFAULT 20,
  enabled BOOLEAN DEFAULT TRUE
);
```

## 训练数据生成（伪码）

```python
def build_preference_pairs(host, goal, start_ts, end_ts):
    runs = fetch_plans_history(host, goal, start_ts, end_ts)
    pairs = []
    for fp, group in groupby_fingerprint(runs):
        good = topk(group, key=reward, k=3)
        bad  = bottomk(group, key=reward, k=3)
        for g in good:
            for b in bad:
                if g.reward - b.reward > margin:
                    pairs.append({
                      "context": make_context(g.fingerprint, g.page_state_meta),
                      "references": recall_refs(fp),
                      "preferred": g.candidate_plan,   # MicroPlanV1 JSON
                      "rejected":  b.candidate_plan,
                      "critique":  merge_reflection_texts(fp)
                    })
    return pairs
```

## 训练与上线流程（建议）

1. **数据集构建**：选 2–3 个站点（Indeed/XHS/WeChat），最近 2–4 周历史，生成 3–5k 对偏好。
2. **DPO 微调**：

   * Prompt 版本：网格搜索/贝叶斯优化 few-shot 案例与指令权重；
   * 模型版本：如需 LoRA，训练小型策略模型（只输出 MicroPlanV1）。
3. **离线评测**：用 E 的回放 & mock 页面跑回放测试，指标（成功率、步数、token）。
4. **灰度**：`ab_assignments` 指定域名 10–20% 流量；仪表盘实时监控失败率/成本；触发阈值自动回退。
5. **推广**：指标稳定后扩大到 50–100%。

## 集成到在线系统

* `llm.plan` 新参数：`planner_version_id`（或根据 host/ab\_assignments 自动填充）。
* 记录在 `plans_history`：哪次使用了哪个 planner 版本 → 便于 A/B 分析与回滚定位。

## 测试与验收

* **离线**：DPO 模型在离线回放集上胜出基线 ≥ 5% 成功率；
* **在线灰度**：新版本在 2 个站点的 20% 流量上，成功率↑（≥3–5%）、平均步数↓、token 下降或持平；
* **回退**：一键回退生效，5 分钟内指标恢复。

## 风险与回退

* 偏好对噪声：设置 `reward` 差值门槛；过滤不稳定指纹；用 Teacher 帮忙打分校准。
* 成本：Teacher 只在“难站点/失败率高”启用；训练放夜间批；在线严格限流。
* 法务/隐私：训练数据仅用**结构化动作与指纹摘要**，不含原图/敏感内容；保留删除权。

---
# Sprint J｜技能库（Skill Library）与宏动作自动化（1–2 周）

**目标**
把“高支持度的成功子序列”沉淀为**可重用宏动作/插件**，进入市场灰度发布，让常见模式“一键安装即用”。

## 产出（DoD）

* **挖掘作业**：离线 Job 从 `plans_history` 中找频繁子序列（如 “wheel\@leftPane(-600) → click\@list\[i+1] → wait\_quiet → click\@Apply”）。
* **宏动作定义**：

  ```yaml
  name: apply_click_flow
  version: 1.0.0
  params: { index_offset: int }
  steps: [ ...MicroPlanV1 子序列... ]
  ```
* **插件化打包**：自动生成 `.wfpack.tgz`，可直接安装（沿用 B 的市场闭环）。
* **Workflow 支持**：`do: macro.apply_click_flow` with params。
* **可观测**：宏动作展开后的步骤仍写事件，便于诊断。

## 验收

* 在 Indeed/小红书常见动作链路用宏后：工作流 JSON 更短、开发时间下降；
* 宏动作从市场安装后**无需重启**即可用；
* 失败可回退到非宏版（等价展开）。

---

## 一键启动清单（今天就能做）

* 建分支：`feature/h-rag-reflexion`、`feature/i-dpo-rlaif`、`feature/j-skill-lib`
* 执行顺序：H → I（可与 J 并行 50%）
* 提供的最小实现骨架（你可直接照着写）：

  * `server/routes/plans.recall.ts`（取向量近邻 + 结构化摘要）
  * `runtime/actions/mem.recall.py`（调用 recall API，落到 `@refs`）
  * `runtime/actions/plan.reflect.py`（失败→生成 critique→POST /plans/reflect）
  * `trainer/dpo/prepare_pairs.py`、`trainer/dpo/train.py`（读偏好对→DPO）
  * `server/routes/deploy.ab.ts`（灰度/回退）
  * `jobs/skills/mine_subsequences.py`（频繁子序列→宏动作）

---

## 对齐检查（不跑偏）

* 仍以**安全白名单/参数来源校验/HP 抢占/可观测与回放**为基线；
* H = **RAG + Reflexion 在线增强**（无侵入，失败即降级）；
* I = **离线对齐**（DPO/RLAIF），通过**灰度**安全上线；
* J = **工程化复用**（技能库/宏动作/插件市场），缩短开发与运维成本。

Sprint H：
下面给你一份**可直接开工**的 Sprint H（RAG 轨迹检索 + 在线 Reflexion）落地包：数据库迁移、向量与回填脚本、后端 API、客户端新动作、Workflow 接入样例、可观测与 CLI、测试与验收、风险与回退。把这些文件按目录放进仓库，按顺序执行即可跑通。

---

# 一、目标回顾（防跑偏）

* 在生成计划前，**检索历史成功轨迹**，将 Top-k 案例作为参考注入 `llm.plan` 提示块，降低盲选与 token 消耗。
* 在执行失败或 reward 偏低时，**在线生成“反思短评”**，写入库中，供下次计划参考（Reflexion）。
* 不改变安全基线（动作白名单、参数来源校验、HP 抢占、预算），完全兼容现有 A→G 架构。

---

# 二、数据库迁移（Postgres + pgvector）

> 若你已安装 pgvector，可跳过 `CREATE EXTENSION`。

```sql
-- 1) 启用 pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- 2) 在 plans_history 上增加两列：指纹向量与轨迹向量
-- 统一使用 1024 维，若嵌入返回维度不同，客户端做 pad/trunc（见下）。
ALTER TABLE plans_history ADD COLUMN IF NOT EXISTS fingerprint_embed vector(1024);
ALTER TABLE plans_history ADD COLUMN IF NOT EXISTS trajectory_embed  vector(1024);

-- 3) 建索引（IVFFLAT 需要设置 lists；根据数据量调参）
CREATE INDEX IF NOT EXISTS idx_ph_fpvec ON plans_history USING ivfflat (fingerprint_embed vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_ph_trvec ON plans_history USING ivfflat (trajectory_embed  vector_cosine_ops) WITH (lists = 100);

-- 4) 仅保存“反思短评”的表
CREATE TABLE IF NOT EXISTS plan_reflections (
  id BIGSERIAL PRIMARY KEY,
  history_id BIGINT REFERENCES plans_history(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT now(),
  critique TEXT NOT NULL,      -- 简短可读的反思
  suggestions JSONB,           -- 结构化的修正建议，如 { "prefer_actions": ["wheel@leftPane(-600)"] }
  reward_before DOUBLE PRECISION,
  tags TEXT[]
);

-- 5) 常用索引
CREATE INDEX IF NOT EXISTS idx_plans_history_host_goal ON plans_history(host, goal_hash);
CREATE INDEX IF NOT EXISTS idx_plan_reflections_hist ON plan_reflections(history_id);
```

---

# 三、Embedding 服务与回填作业

## 3.1 Provider 抽象（后端）

`server/services/embeddings.ts`

```ts
export interface EmbeddingProvider {
  model: string;
  dim: number;          // 期望维度（例如 1024）
  embed(texts: string[]): Promise<number[][]>;
}

export class OpenAIEmbProvider implements EmbeddingProvider {
  model = "text-embedding-3-large"; // 1536 维（示例）
  dim = 1536;
  async embed(texts: string[]) { /* 调用实际 API，返回 number[][] */ }
}

/** 统一到 1024 维：高维 -> 截断；低维 -> 零填充 */
export function toDim(vecs: number[][], targetDim = 1024): number[][] {
  return vecs.map(v => {
    if (v.length === targetDim) return v;
    if (v.length > targetDim)   return v.slice(0, targetDim);
    const pad = new Array(targetDim - v.length).fill(0);
    return v.concat(pad);
  });
}
```

> 你可以切换任何嵌入模型，**只需保证最终入库是 1024 维**。

## 3.2 回填脚本（离线 Job）

`jobs/backfill_embeddings.ts`

```ts
/**
 * 对历史 plans_history 回填 fingerprint_embed / trajectory_embed
 * 运行方式：node jobs/backfill_embeddings.ts --since=30d
 */
import { OpenAIEmbProvider, toDim } from "../server/services/embeddings";
import { pg } from "../server/services/pg";

function buildFingerprintText(row:any): string {
  // 与 E 阶段的 fingerprint 组成逻辑一致（host/path/pane/layout/controls/DPR等）
  return `${row.host}|${row.fingerprint}|${row.page_state_meta?.left_ratio}|${row.page_state_meta?.right_ratio}|${row.page_state_meta?.dpr||1}`;
}

function buildTrajectoryText(row:any): string {
  // 将候选被选路径或实际执行的动作签名序列拼接
  // 示例："wheel@leftPane(-600);click@list[i];wait@quiet"
  return row.candidate_action_sigs?.join(";") || row.action_sigs?.join(";") || "";
}

async function main() {
  const since = process.argv.find(a=>a.startsWith("--since="))?.split("=")[1] || "30d";
  const rows = await pg.manyOrNone(
    `SELECT id, host, fingerprint, page_state_meta, candidate_action_sigs, action_sigs
     FROM plans_history
     WHERE created_at > (now() - $1::interval)
       AND (fingerprint_embed IS NULL OR trajectory_embed IS NULL)`,
     [since]
  );

  const provider = new OpenAIEmbProvider();
  const fpTexts = rows.map(buildFingerprintText);
  const trTexts = rows.map(buildTrajectoryText);
  const fpVecs  = toDim(await provider.embed(fpTexts), 1024);
  const trVecs  = toDim(await provider.embed(trTexts), 1024);

  const q = `
    UPDATE plans_history
       SET fingerprint_embed = $2, trajectory_embed = $3
     WHERE id = $1
  `;
  for (let i=0; i<rows.length; i++){
    await pg.none(q, [rows[i].id, fpVecs[i], trVecs[i]]);
  }
  console.log(`Backfilled ${rows.length} rows`);
}

main().catch(e=>{ console.error(e); process.exit(1); });
```

---

# 四、Recall API（相似轨迹检索）

`server/routes/plans.recall.ts`

```ts
/**
 * GET /plans/recall
 * 查询条件：
 *   fingerprint? : string  （优先）
 *   host?        : string
 *   goal_hash?   : string
 *   k=5
 *   min_reward=0.5
 *   since=30d
 * 返回：Top-k 成功轨迹摘要（仅结构化文本与动作签名，不含快照）
 */
import express from "express";
import { pg } from "../services/pg";

export const plansRecall = express.Router();

plansRecall.get("/plans/recall", async (req, res) => {
  const { fingerprint, host, goal_hash, k="5", min_reward="0.5", since="90d" } = req.query as any;
  if (!fingerprint && !host) return res.status(400).json({ error: "fingerprint or host required" });

  // 若给 fingerprint，用向量近邻；否则退化为 host + 过滤
  let rows:any[] = [];
  if (fingerprint) {
    // 这里假设你有一个函数 textToVec()，或前端传 vec。简单起见，我们从库里近似找“同 host 最近”的向量邻居
    rows = await pg.manyOrNone(`
      WITH seed AS (
        SELECT fingerprint_embed AS vec, host AS h FROM plans_history
        WHERE fingerprint = $1
        ORDER BY created_at DESC
        LIMIT 1
      )
      SELECT id, host, goal_hash, reward, candidate_action_sigs, page_state_meta
      FROM plans_history, seed
      WHERE host = seed.h
        AND reward >= $2
        AND created_at > (now() - $3::interval)
      ORDER BY fingerprint_embed <#> seed.vec   -- cosine distance
      LIMIT $4::int
    `, [fingerprint, min_reward, since, k]);
  } else {
    rows = await pg.manyOrNone(`
      SELECT id, host, goal_hash, reward, candidate_action_sigs, page_state_meta
      FROM plans_history
      WHERE host = $1
        AND ($2::text IS NULL OR goal_hash = $2)
        AND reward >= $3
        AND created_at > (now() - $4::interval)
      ORDER BY reward DESC
      LIMIT $5::int
    `, [host, goal_hash||null, min_reward, since, k]);
  }

  const refs = rows.map(r => ({
    history_id: r.id,
    host: r.host,
    goal_hash: r.goal_hash,
    avg_reward: r.reward,                // 简化：取样本 reward
    step_templates: r.candidate_action_sigs || [],
    meta: r.page_state_meta
  }));
  res.json({ k: refs.length, refs });
});
```

> 生产化时可将“输入的 fingerprint 文本→向量”也做成 API（这里用库内最近一个 fingerprint 的向量近似）。

---

# 五、客户端新动作

## 5.1 `mem.recall`（检索相似成功轨迹）

`runtime/actions/mem.recall.py`

```python
from runtime.engine.context import http_post, http_get

def register_action(name):
    def deco(fn):
        # 注册到动作表（你项目已有）
        return fn
    return deco

@register_action("mem.recall")
def mem_recall(ctx, goal:str=None, fingerprint:str=None, k:int=5, min_reward:float=0.5, since:str="90d", filters:dict=None, save:str=None, **_):
    """
    调用后端 /plans/recall，返回 Top-k 参考片段。
    """
    params = { "k": k, "min_reward": min_reward, "since": since }
    if fingerprint: params["fingerprint"] = fingerprint
    else:
        # 回退：仅按 host/goa_hash 过滤
        ps = ctx.vars.get("ps") or {}
        params["host"] = ctx.helpers.url_host(ps.get("url",""))
        if goal:
            params["goal_hash"] = ctx.helpers.sha256(goal)
    if filters:
        params.update(filters)

    res = http_get("/plans/recall", params=params, timeout=5_000)
    ctx.events.log("mem.recall", { "k": res.get("k",0) })

    # 整理成 LLM Prompt 可用的参考块（节省 token）
    block = []
    for ref in res.get("refs", []):
        block.append({
            "history_id": ref["history_id"],
            "avg_reward": ref["avg_reward"],
            "step_templates": ref.get("step_templates", [])[:6],  # 控制长度
            "meta": ref.get("meta", {})
        })
    if save:
        ctx.vars[save] = block
    return { "ok": True, "refs": block }
```

## 5.2 `plan.reflect`（失败/低奖赏时在线反思）

`runtime/actions/plan.reflect.py`

```python
from runtime.engine.context import http_post
from datetime import datetime

@register_action("plan.reflect")
def plan_reflect(ctx, when=None, max_len:int=320, save:str=None, **_):
    """
    在条件满足时生成短评，并上传到后端。
    约定：ctx.vars["res"] 内含执行结果，ctx.vars["reward"] / ctx.vars["last_error"] 可用
    """
    cond_ok = True
    if isinstance(when, str):
        # 简易表达式求值（你已有 evaluator）
        cond_ok = ctx.evaluator.eval(when, ctx.vars)
    if not cond_ok:
        return {"ok": True, "skipped": True}

    # 构造最小上下文：目标、关键动作、最近失败点
    goal = ctx.vars.get("goal") or ""
    plan  = ctx.vars.get("plan") or {}
    last_error = ctx.vars.get("last_error") or ""
    reward = float(ctx.vars.get("reward") or 0)

    critique = ctx.llm.generate(
        system="你是流程纠错助手。输出中文简短反思，不超过 5 句。",
        user=f"目标: {goal}\n计划摘要: {str(plan)[:500]}\n错误: {last_error}\n当前奖励: {reward}\n请给出简短反思与下次可尝试的两条改进建议（动作级、可执行）。"
    )
    critique = critique[:max_len]

    payload = {
      "history_id": ctx.vars.get("history_id"),
      "critique": critique,
      "suggestions": ctx.extract_suggestions(critique),  # 可选：正则解析出动作偏好
      "reward_before": reward,
      "tags": ["auto"]
    }
    http_post("/plans/reflect", json=payload, timeout=5_000)
    ctx.events.log("plan.reflect", {"len": len(critique)})

    if save:
        ctx.vars[save] = {"critique": critique}
    return {"ok": True, "critique": critique}
```

> 如果你担心在线 LLM 成本，可先做“模板化反思”：根据 `last_error` 与 `res` 自动拼接两条建议，后续再切换到 LLM。

---

# 六、Workflow 接入样例（节选）

```json
{
  "version": "1.2",
  "start": "loop",
  "features": {
    "planner": { "strategy": "agentq", "memory": { "rag": true, "k": 5, "use_reflexion": true, "reward_threshold": 0.5 } },
    "humanize": { "mouse": true }
  },
  "vars": { "i": 0, "goal": "apply current item" },
  "states": {
    "loop": {
      "actions": [
        { "do": "ext.get_pagestate", "save": "ps" },
        { "do": "mem.recall", "goal": "@goal", "fingerprint": "@fingerprint(@ps)", "k": 5, "save": "refs" },
        { "do": "llm.plan",
          "strategy": "agentq",
          "allowed_actions": ["click_coordinates","wheel_coordinates","ext.extract","wait_for"],
          "constraints": { "max_steps": 5, "no_dom_click": true, "must_stay_in_host": "indeed.com" },
          "inputs": { "page_state": "@ps", "context": { "i": "@i" } },
          "references": "@refs",
          "schema": "MicroPlanV1",
          "save": "cands"
        },
        { "do": "plan.simulate", "from": "@cands", "page_state": "@ps", "save": "choice" },
        { "do": "plan.execute", "from": "@choice['plan']", "save": "res" },
        { "do": "plan.reflect", "when": "@res['ok']==false || @res['reward'] < 0.5", "save": "rx" }
      ],
      "transitions": [
        { "if": "@res['ok']==true", "go_to": "advance" },
        { "else_go_to": "fallback_scroll" }
      ]
    },
    "advance": { "actions": [ { "do": "increment_variable", "name": "i" } ], "on_success": "loop" },
    "fallback_scroll": {
      "actions": [
        { "do": "wheel_coordinates", "at_bbox": "@ps['panes']['left']['rect']", "amount": -800 },
        { "do": "sleep_ms", "value": 600 }
      ],
      "on_success": "loop"
    }
  }
}
```

---

# 七、可观测与 CLI

## 7.1 事件

* `mem.recall`：`{k, picked_host, goal_hash}`
* `plan.reflect`：`{len, tags}`
* 这些会与现有 `plan.branch / simscore / choice / execute` 一起展示在回放里。

## 7.2 CLI

`tools/wf_cli.ts`

```ts
// wf recall --host ca.indeed.com --goal "apply job" --k 5
// wf reflect --run-id 123
```

* `recall`：便于本地调试向量召回；
* `reflect`：对某次 run 触发在线/离线反思生成并查看内容。

---

# 八、测试与验收

## 8.1 单元

* 向量维度统一（embed→toDim 1024）
* 召回排序：reward 低的不会进入 Top-k（设定 min\_reward）
* 反思生成：当 `when` 条件不满足不产生调用；长度受 `max_len` 约束

## 8.2 集成

* `GET /plans/recall`：fingerprint 与 host 两种路径；返回结构完整
* `mem.recall` + `llm.plan`：引用参考后，候选更贴近历史模板（可以检查 step\_templates 是否影响计划）

## 8.3 E2E（实机）

* Indeed / 小红书 / 微信 三条路径各跑 ≥ 20 次

  * **成功率**：相对 Sprint F 基线 **↑ ≥ 3%**
  * **Plan tokens**：平均下降（因为参考块减少试探）
  * **失败/低 reward**：能产生反思短评，并在下一次被引用（可在 prompt 中看到）

**验收通过标准**

* 回填作业完成率 ≥ 95%
* 召回命中率稳定；无历史时自动降级不报错
* 反思短评入库并在下一次计划被纳入 prompt（日志可见）

---

# 九、风险与回退

* **向量质量差/误召回**：提高 `min_reward`、限制 `since`、增加 host/goal 筛选；必要时引入 rerank（BM25 + 轻量 LLM 打分）。
* **成本上升**：`k ≤ 5`；参考块仅保留**动作签名模板**与 1–2 条关键提示；在线反思可先走模板版。
* **隐私/合规**：只存结构化步骤与指纹摘要，不入库截图内容；保留“清除历史”的工具。
* **不可用时回退**：Workflow `features.planner.memory.rag=false` 即刻关闭；`plan.reflect` 可禁用。

---

# 十、今天就能做的 10 个动作

1. 执行上方 **SQL 迁移** 并安装 `pgvector`。
2. 合并 `server/services/embeddings.ts` 与 `jobs/backfill_embeddings.ts`，跑一次 **回填**（30 天）。
3. 上线 `GET /plans/recall` 路由。
4. 新增客户端动作 `mem.recall`、`plan.reflect` 并写入事件。
5. 在 Indeed 工作流中插入 `mem.recall → llm.plan(references)`。
6. 增加 Feature Flag：`features.planner.memory.rag`、`use_reflexion`。
7. 写 **单测/集成** 并本机通过。
8. 用 CLI 验证 `wf recall`。
9. 在测试机真实跑一轮 20 次回合，观察指标。
10. 记录验收报告与回滚按钮（关闭 flag 即回退）。

---
Sprint I：


先校准一下方向避免跑偏：

* 已完成：A（坐标链路）→ B（插件化+市场）→ C（Micro-Plan）→ D（多候选+模拟）→ E（Plans History+Fingerprint+Replay）→ F（AgentQ）→ **H（RAG 轨迹检索 + 在线 Reflexion）**。
* 现在进入**Sprint I：DPO / RLAIF 离线训练与灰度上线**，把“历史数据→偏好对→训练→部署→AB/回退”打通。

---

# Sprint I｜DPO / RLAIF 离线训练与上线（2–3 周）

## 目标

1. 基于 `plans_history` + `plan_reflections` 产出**偏好对 (preferred > rejected)**。
2. 跑两条可选训练路径：

   * **Prompt 优化**（轻量、见效快）
   * **小策略模型 + DPO/LoRA**（中期收益更好）
3. **Teacher（RLAIF）** 可选介入，缺少人类偏好时用老师 LLM 打分生成偏好。
4. 上线**版本化 Planner**，按域名/工作流灰度，指标异常自动回退。

---

## 一、交付物（DoD）

* 数据生成器：从历史运行构造偏好对 JSONL（含上下文/参考片段/胜出理由）。
* 训练脚本：`trainer/prompt/tune.py` 与 `trainer/dpo/train.py`（LoRA 可选）。
* Teacher 服务（可选）：`POST /teacher/score` 返回候选 plan/轨迹的评分或偏好。
* 版本管理与灰度：`planner_versions` / `ab_assignments`，部署 API 与回退策略。
* 在线集成：`/llm/plan` 支持指定 `planner_version_id` 或按 host 自动路由；历史表记录使用版本。
* 评测：离线回放集 + 在线灰度 AB Dashboard。
* 文档与Runbook：训练/发布/回退流程、质量门槛。

---

## 二、数据：偏好对构建

### 1) 样本来源

* **候选级**：同一次 `llm.plan` 的多个候选（D/H 阶段已保存）；被选中且成功/高 reward 的为 **preferred**，失败/低 reward 的作为 **rejected**。
* **轨迹级**：同一 `fingerprint` 下不同 run 的最终计划/轨迹，以 `reward` 高低配对。
* **反思增强**：`plan_reflections` 的 critique 里标注的“错误模式/改进建议”可用于构造 hard negative/positive。

### 2) 采样准则

* 仅取 `reward` 差值 ≥ `margin`（默认 0.8）且二者来源相同 `host + fingerprint`。
* 去重：同一对模板/签名的重复配对只保留一次。
* 清洗：过滤含异常/越权动作、token 过长的 case。

### 3) 偏好对 JSONL（示例）

`data/prefs/train.jsonl`

```json
{"context":{"host":"ca.indeed.com","fingerprint":"8a9c2f...","goal":"apply current item","page_meta":{"left_ratio":0.33,"right_ratio":0.67,"dpr":1.25}},"references":[{"step_templates":["wheel@leftPane(-600)","click@list[i]","wait@quiet","ext.extract(apply)"]}],"preferred":{"steps":[{"do":"wheel_coordinates","args":{"at_bbox":"@ps.panes.left.rect","amount":-600}},{"do":"click_coordinates","args":{"bbox":"@ps.lists[0].itemRects[@i]"}},{"do":"wait_for","args":{"until":{"type":"ext.wait_quiet","timeout_ms":6000}}},{"do":"ext.extract","args":{"mode":"find_button_bbox","text_any_of":["Apply","Quick Apply"]}}]},"rejected":{"steps":[{"do":"click_coordinates","args":{"bbox":"@ps.lists[0].itemRects[@i+2]"}}]},"meta":{"reward_pref":1.9,"reward_rej":0.4,"why":"preferred reaches Apply reliably; rejected skips visibility/quiet wait"}}
```

> 训练时会把 `context + references` 作为提示的**上文**，`preferred/rejected` 作为**输出比较**。

### 4) 生成器脚本（骨架）

`jobs/dpo/prepare_pairs.py`

```python
# 读取 plans_history / plan_candidates / plan_reflections → 生成 train/val/test JSONL
# 关键：同 fingerprint 分组、reward 差值、去重、长度约束
```

---

## 三、Teacher 打分（RLAIF，可选）

### 1) 路由与接口

`server/routes/teacher.score.ts`

```ts
/**
 * POST /teacher/score
 * body: { context, references, candidates: [MicroPlanV1, ...] }
 * return: { scores: number[], preference?: [winner_idx, loser_idx], rationales?: string[] }
 */
```

### 2) 评分 Rubric（放在系统提示里）

* 是否保持域名与容器边界（安全）
* 步数/等待/滚动成本
* 关键按钮可见/可点击概率
* 抗动态波动能力（是否包含 wait\_quiet / 视区滚动）
* 过去反思建议是否被采纳

> 成本控制：只在**数据稀缺**或**失败率高**的 fingerprint 上调用；batch 评分缓存结果入表 `teacher_judgments`。

---

## 四、训练流水线

### 方案 A｜Prompt 优化（fast path）

* 目标：优化 `planner.web.coords.v1` 的 few-shot 与指令权重。
* 方法：

  * 网格/贝叶斯搜索多个 Prompt 变体；
  * 离线回放集评测成功率/步数/估计 token；
  * 选 Pareto 最优成为 `planner_version`。
* 脚本：`trainer/prompt/tune.py`

  * 输入：`data/prefs/*.jsonl`（用作自动评测集，而非监督）
  * 输出：`versions/prompt_XYZ.md` + 指标报告

### 方案 B｜DPO + LoRA（策略微调）

* 选择一个**小/中型开源基座**（如 Llama-3-8B-Instruct 或轻量指令模型）作为**Planner 生成头**（输出 MicroPlanV1）。
* 流程：

  1. **SFT（可选）**：用成功 plan 的 `steps` 做少量监督预热。
  2. **DPO**：用 JSONL 偏好对训练；LoRA 低秩适配（r=8\~16, α=16）。
  3. **冻结输出模板**：强约束输出为 MicroPlanV1（结构头用 adapter 控制或后处理 Validator）。
* 脚本：`trainer/dpo/train.py`（HuggingFace TRL）
* 超参建议：

  * 学习率 `5e-5`（LoRA），batch 64（accum 可用），epochs 1–2
  * β（DPO）= 0.1–0.2；max\_seq\_len 2048
  * 提前停止：val 成功率不再提升 2 个评估周期

**评测基线**：离线回放集（来自 E 阶段数据 + H 的 recall 注入），指标：成功率、平均步数、估计 tokens；用 `plan.simulate` 与规则校验做代理评测。

---

## 五、版本化与灰度上线

### 1) 版本表（已在前一轮给出，可直接使用）

* `planner_versions`：存放 Prompt/LoRA 文件及元数据
* `ab_assignments`：按 host/策略配置流量百分比

### 2) 部署 API

`server/routes/deploy.planner.ts`

```ts
/**
 * POST /deploy/planner
 * body: { name, type: "prompt"|"lora", file_url, base_provider, notes }
 * → 新建 planner_version (staging)
 */
```

`server/routes/deploy.ab.ts`

```ts
/**
 * POST /deploy/ab
 * body: { host, strategy, planner_version_id, traffic_pct, enabled }
 * → 写入 ab_assignments
 */
```

### 3) 在线集成

* `/llm/plan` 读取 `ab_assignments`，按 host/strategy 灰度选择版本；或工作流显式设置 `planner_version_id`。
* `plans_history` 记录 `planner_version_id`，便于 AB 分析与回退定位。

### 4) 自动回退

* 监控 **失败率/平均 reward/LLM 成本**：若 15 分钟窗口内超阈值（例如失败率 > 基线 + 5pp 或 成本 +30%），自动把流量切回上一个版本；写入审计事件。

---

## 六、在线工作流小改动（兼容 v1.2）

```json
{
  "features": {
    "planner": {
      "strategy": "agentq",
      "memory": { "rag": true, "k": 5, "use_reflexion": true },
      "planner_version_id": "auto"    // 或指定具体版本ID
    }
  }
}
```

---

## 七、测试与验收

### 单元

* `prepare_pairs`：边界数据、去重、margin 过滤。
* `teacher.score`：打分范围与稳定性；错误处理与缓存。
* `validator`：确保模型输出严格符合 MicroPlanV1（结构/字段/步数上限）。

### 集成

* **Prompt 调优**：自动评测脚本对比 baseline；报告生成。
* **DPO 训练**：过拟合检查（train/val gap），推理速度与内存监控。
* **灰度流量**：AB 路由正确，异常触发自动回退。

### E2E（实机）

* 选 2–3 个域（Indeed / 小红书 / 微信）各 20–50 次回合对比：

  * 成功率 ↑ ≥ 3–5%
  * 平均步数 ↓ 或持平
  * 计划 token ↓ 或持平
  * 无明显安全违规（越权动作为 0）

**通过标准**：满足以上门槛；回退按钮可用，5 分钟内恢复基线。

---

## 八、目录与样例文件（最小骨架）

```
trainer/
├─ prompt/
│  ├─ tune.py                 # Prompt 网格/贝叶斯搜索 + 离线评测
│  └─ templates/
│     └─ planner.web.coords.v2.md
├─ dpo/
│  ├─ prepare_pairs.py        # 读取历史→生成 JSONL 偏好对
│  ├─ train.py                # TRL DPO + LoRA
│  └─ eval_offline.py         # 回放集评测
server/
├─ routes/
│  ├─ teacher.score.ts        # RLAIF Teacher
│  ├─ deploy.planner.ts       # 上线 Planner 版本
│  └─ deploy.ab.ts            # 灰度
└─ services/
   ├─ planner_router.ts       # 读取 ab_assignments
   └─ validator.microplan.ts  # 严格校验输出
runtime/
└─ actions/
   └─ llm.plan.py             # 支持 planner_version_id 透传
jobs/
└─ dpo/
   └─ prepare_pairs.ts        # （若统一 TS）
data/
└─ prefs/
   ├─ train.jsonl
   ├─ val.jsonl
   └─ test.jsonl
versions/
└─ planner/
   ├─ prompt_XYZ.md
   └─ lora_XYZ.bin
```

---

## 九、风险与回退

* **数据噪声/偏好失真**：使用 `reward` 差值阈值与 fingerprint 分组，Teacher 校准边界；保留人工抽检面板。
* **成本上升**：Teacher 只在“难站点”启用；DPO 训练离线夜间跑；线上严格限流。
* **输出不合Schema**：上线前强制 Validator；在线失败自动降级到 `agentq` + simulate。
* **收益不稳定**：先上线 Prompt 版（轻量），LoRA 版小流量灰度，异常即回退。

---

## 十、今天就能做的 10 个动作

1. 创建分支 `feature/i-dpo-rlaif`。
2. 跑 `jobs/dpo/prepare_pairs.py` 生成首批 JSONL（先 Indeed）。
3. 写 `trainer/prompt/tune.py`，在回放集上自动评测 3–5 个 Prompt 变体。
4. 打通 `trainer/dpo/train.py`（TRL + LoRA），用 3–5k 对偏好开第一版训练。
5. 实现 `server/routes/teacher.score.ts` 的骨架（暂时可返回固定打分，先把链路跑通）。
6. 加 `planner_versions` 发布接口与 AB 路由。
7. 在线 `llm.plan` 支持 `planner_version_id` 并写入 `plans_history`。
8. 做离线评测报告（baseline vs 新版）。
9. 小流量灰度（10–20%），设置自动回退阈值。
10. 复盘与文档化：训练参数、数据过滤、收益曲线、回退记录。

---
Sprint J:
在 A→I 都已落地的基础上，**下一个 Sprint = J：技能库（Skill Library）与宏动作（Macro Actions）**。目标是把高频成功子序列沉淀成“可安装、可复用、可灰度”的宏动作/插件，让常见站点和桌面场景**一键复用**，显著降低新工作流编写与维护成本，同时继续遵守你现有的安全与计费边界（客户端不直连 DB，只走 API）。

---

# Sprint J｜技能库 & 宏动作（1–2 周）

## 目标

1. 从 `plans_history` 自动挖掘**高支持度子序列**，生成可配置宏动作（宏 = MicroPlan 片段 + 参数化 + 约束）。
2. 宏以 **`.wfpack.tgz`** 形式上架/安装/签名校验，支持**版本化、灰度、回滚**。
3. 工作流 JSON 支持 `do: macro.<name>` 及参数绑定，仍然走**坐标点击白名单**与**来源校验**。
4. 控制台可视化：宏使用率、成功率、失败分布、热力图。

---

## 交付物（DoD）

* **服务端**

  * 挖掘 Job：`jobs/skills/mine_subsequences.py`（FP-growth 或 PrefixSpan）
  * 宏元数据表 & API：`/skills/list`、`/skills/publish`、`/skills/install`、`/skills/versions`
  * 宏打包器：将宏定义 + 资源打成 `.wfpack.tgz`，生成签名
  * 许可/计费钩子：尊重现有用户/设备权限（仅 API，客户端不直连 DB）
* **运行时（客户端）**

  * 宏注册表：`runtime/macros/registry.py`
  * 新动作：`macro.run`（展开并执行）、`macro.validate`（离线校验）
  * 与 `plan.execute` 无缝对接（执行时仍逐步写事件，HP 步间让出）
* **工作流 Schema 扩展（兼容 v1.2）**

  * `action_macro` 类型与参数校验、`features.macros` 开关
* **控制台/CLI**

  * CLI：`wf skills mine/publish/install/list`
  * 控制台：宏详情页（参数/版本/依赖/指标）
* **样例宏**

  * `apply_click_flow`（Indeed 左列→详情→Apply）
  * `xhs_expand_comments_to_bottom`（小红书评论展开至底部）
  * `wechat_reply_cycle`（优先级回复的一段公共片段）

---

## 数据库与 API

### 表（示例）

```sql
CREATE TABLE skills (
  id BIGSERIAL PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,          -- e.g., apply_click_flow
  title TEXT,
  description TEXT,
  host TEXT,                          -- 目标域或 app 标识（可为 "desktop.wechat"）
  params JSONB,                       -- { index_offset:int, apply_texts:[...] }
  constraints JSONB,                  -- { must_stay_in_host, no_dom_click:true, max_steps:5 }
  microplan JSONB,                    -- 内嵌的 MicroPlan 片段（模板化）
  version TEXT NOT NULL,
  status TEXT NOT NULL,               -- "staging" | "prod" | "deprecated"
  signature TEXT NOT NULL,            -- 包签名
  created_at TIMESTAMPTZ DEFAULT now(),
  author_id BIGINT
);

CREATE TABLE skill_stats_daily (
  day DATE, skill_name TEXT, version TEXT,
  runs INT, success INT, avg_steps FLOAT, avg_reward FLOAT, p95_latency_ms INT,
  PRIMARY KEY(day, skill_name, version)
);
```

### API

* `GET /skills/list?host=ca.indeed.com` → 列出适配技能
* `POST /skills/publish` → 上传 `.wfpack.tgz`（服务端校验签名 & schema）
* `POST /skills/install` → 设备/工作流级安装绑定（鉴权 + 计费校验）
* `GET /skills/versions?name=apply_click_flow`

> **计费/权限**：延用你已有“登录→设备识别码→权限控制”机制，API 层面校验用户套餐/可用设备数。

---

## 宏定义（推荐 schema）

`skill.apply_click_flow.yaml`（逻辑上会被打包进 `.wfpack.tgz`）

```yaml
name: apply_click_flow
version: 1.0.0
host: ca.indeed.com
title: Click & Apply current job (left pane → right detail)
description: |
  Scroll to reveal i-th item in left pane, click, wait for quiet, find and click Apply.
params:
  index_offset: { type: integer, default: 0, min: -2, max: 2 }
  apply_texts:  { type: array,  default: ["Apply","Quick Apply","立即申请"], items: { type: string } }
constraints:
  must_stay_in_host: indeed.com
  no_dom_click: true
  max_steps: 5
microplan:
  steps:
    - { do: wheel_coordinates,   args: { at_bbox: "@ps.panes.left.rect", amount: -600 }, expect: "left list visible" }
    - { do: click_coordinates,   args: { bbox: "@ps.lists[0].itemRects[@i + @index_offset]" }, expect: "right pane updates" }
    - { do: wait_for,            args: { until: { type: "ext.wait_quiet", timeout_ms: 6000 } } }
    - { do: ext.extract,         args: { mode: "find_button_bbox", text_any_of: "@apply_texts" }, expect: "apply located" }
    - { do: click_coordinates,   args: { bbox: "@last_found_bbox" }, expect: "apply clicked" }
```

> **要点**：宏里的 **参数**（如 `@index_offset`）在运行时从工作流变量/宏调用参数注入；所有 bbox/rect **必须**来源于 `@ps` 或上一步 `save`，仍走**来源校验**。

---

## 运行时：宏动作执行

### 注册与展开

`runtime/macros/registry.py`

```python
class MacroRegistry:
    def __init__(self):
        self.catalog = {}  # name -> MacroDef
    def load_from_wfpack(self, path): ...
    def get(self, name): return self.catalog[name]

REGISTRY = MacroRegistry()
```

`runtime/actions/macro.run.py`

```python
@register_action("macro.run")
def macro_run(ctx, name:str, args:dict=None, save:str=None, **_):
    macro = REGISTRY.get(name)
    bound = bind_params(macro, ctx.vars, args or {})
    # 1) schema & constraints 校验（host/domain/no_dom_click/max_steps）
    enforce_constraints(macro.constraints, ctx.vars.get("ps"))
    # 2) 展开为临时状态的 MicroPlan
    plan = expand_to_microplan(macro.microplan, bound)
    # 3) 交给 plan.execute 执行（白名单 & 来源校验照常）
    res = ctx.actions["plan.execute"](ctx, _from=plan, policy=ctx.policies.microplan)
    if save: ctx.vars[save] = res
    return res
```

### 校验器

* **Schema 校验**：宏包安装时即校验；运行前再次快速校验。
* **来源校验**：沿用 `provenance.py`，凡是 `bbox/rect/selector` 必须源自 `@ps` 或上一步 `save`。
* **白名单**：宏中只允许 `click_coordinates`, `wheel_coordinates`, `wait_for`, `ext.extract` 等**安全动作**。

---

## 工作流 JSON 接入（示例）

```json
{
  "version": "1.3",
  "start": "loop",
  "features": { "macros": { "enabled": true }, "planner": { "strategy": "agentq", "memory": { "rag": true } } },
  "vars": { "i": 0, "index_offset": 0, "apply_texts": ["Apply","Quick Apply","立即申请"] },
  "states": {
    "loop": {
      "actions": [
        { "do": "ext.get_pagestate", "save": "ps" },
        { "do": "macro.run", "name": "apply_click_flow", "args": { "index_offset": "@index_offset", "apply_texts": "@apply_texts" }, "save": "mres" }
      ],
      "transitions": [
        { "if": "@mres['ok']==true", "go_to": "advance" },
        { "else_go_to": "fallback_scroll" }
      ]
    },
    "advance": { "actions": [ { "do": "increment_variable", "name": "i" } ], "on_success": "loop" },
    "fallback_scroll": {
      "actions": [
        { "do": "wheel_coordinates", "at_bbox": "@ps['panes']['left']['rect']", "amount": -800 },
        { "do": "sleep_ms", "value": 600 }
      ],
      "on_success": "loop"
    }
  }
}
```

---

## 挖掘 Job（把历史变成宏候选）

`jobs/skills/mine_subsequences.py`（思路）

1. 选定 host + goal，取 **成功**且 `reward` 高于阈值的轨迹；
2. 将每条轨迹转为 **动作签名序列**（如 `wheel@leftPane(-600) → click@list[i] → wait@quiet → extract@app`）；
3. 用 **PrefixSpan / FP-growth** 找频繁子序列；
4. 用启发式把变量位置参数化（`i → i+offset`、按钮文本作为 `apply_texts` 参数）；
5. 过滤高风险动作，产出 **宏定义 YAML**；
6. 调用 `/skills/publish` 进入 **staging**，人工审阅后升 **prod**。

---

## 打包与发布

* **打包器**：读取宏 YAML + 依赖（可选截图模板、提示块），生成 `.wfpack.tgz` + `manifest.json` + `SIGNATURE`。
* **签名**：沿用你的插件市场签名机制。
* **安装流程**：`/skills/install` 校验用户权限 → 下发到设备 → `REGISTRY.load_from_wfpack()` 热加载。
* **回滚**：版本状态切回 `staging/rollback`，设备端定时拉取更新，宏注册表热替换。

---

## 可观测与报表

* 新事件：`macro.run.start` / `macro.run.end`（ok/err/steps/duration）
* 控制台：按技能/版本统计成功率、失败原因、平均奖励、p95 时延；Top 失败指纹热力。
* 计费：把宏执行计数/时长写入已有计量表。

---

## 测试与验收

### 单元

* 宏 Schema/约束/参数绑定校验
* 来源校验：宏里的 bbox 必须源自 `@ps` 或上一步 `save`
* 展开正确性：`macro.run` → `plan.execute` 输出一致事件流

### 集成

* 安装/卸载/升级/回滚流程
* 两个示例宏（Indeed、小红书）在模拟 PageState 下正确运行

### E2E（实机）

* Indeed：使用 `apply_click_flow` 连续 20 次，**成功率≥AgentQ+simulate 基线**，工作流 JSON 行数下降 ≥ 30%
* 小红书：`xhs_expand_comments_to_bottom` 宏完成评论展开与下拉到底，成功率 ≥ 90%
* 微信：将“查找联系人→聚焦输入框”做成宏，HP 抢占不受影响

**通过标准**：指标达标；安装/回滚 5 分钟内生效；安全边界零回归。

---

## 风险与回退

* **宏过拟合/脆弱**：通过参数化与指纹约束（仅在匹配指纹范围启用）；失败自动降级到普通流程（AgentQ/MCTS）。
* **安全**：宏仅允许坐标/滚动/等待/提取等白名单动作；安装时和运行时双重校验。
* **版本冲突**：使用 `name@version` 与依赖图；安装器做冲突检测与回滚。
* **成本**：宏本身不调用 LLM（通常更省），仅在失败时触发 fallback 计划。

---

## 今天就能做的 10 个动作

1. 建分支 `feature/j-skill-macros`。
2. 落表并开 `/skills/*` API。
3. 写 `MacroRegistry` 与 `macro.run`、`macro.validate`。
4. 做 YAML Schema 与安装签名校验。
5. 写挖掘 Job（先用 PrefixSpan），生成首个 `apply_click_flow.yaml`。
6. 打包器产 `.wfpack.tgz`，`/skills/publish`→`/skills/install` 跑通。
7. 在 Indeed 工作流中替换为 `macro.run`。
8. 接入事件与控制台统计卡片。
9. 单测/集成/E2E 冒烟。
10. 写 Runbook：如何创建/发布/回滚一个宏。

---

太好了✅。我把刚才承诺的**三个最小可跑模板**直接给你，拷进仓库就能开干。这样 Sprint J（技能库 & 宏动作）马上能跑出首条链路。

---

# 1) 示例宏定义（可打包为 `.wfpack.tgz`）

`skills/defs/skill.apply_click_flow.yaml`

```yaml
name: apply_click_flow
version: 1.0.0
host: ca.indeed.com
title: Click & Apply current job (left pane → right detail)
description: |
  Scroll to reveal i-th item in left pane, click it, wait for quiet, find Apply and click.
params:
  index_offset: { type: integer, default: 0, min: -2, max: 2 }
  apply_texts:  { type: array,  default: ["Apply","Quick Apply","立即申请"], items: { type: string } }
constraints:
  must_stay_in_host: indeed.com
  no_dom_click: true
  max_steps: 5
microplan:
  steps:
    - { do: wheel_coordinates, args: { at_bbox: "@ps.panes.left.rect", amount: -600 }, expect: "left list visible" }
    - { do: click_coordinates, args: { bbox: "@ps.lists[0].itemRects[@i + @index_offset]" }, expect: "right pane updates" }
    - { do: wait_for, args: { until: { type: "ext.wait_quiet", timeout_ms: 6000 } } }
    - { do: ext.extract, args: { mode: "find_button_bbox", text_any_of: "@apply_texts" }, expect: "apply located" }
    - { do: click_coordinates, args: { bbox: "@last_found_bbox" }, expect: "apply clicked" }
```

---

# 2) 运行时宏执行动作（最小实现）

`runtime/actions/macro.run.py`

```python
# -*- coding: utf-8 -*-
from typing import Dict, Any
from runtime.engine.registry import register_action   # 你已有的注册器
from runtime.macros.registry import REGISTRY          # 见下方说明
from runtime.engine.errors import ValidationError

def _bind_params(tpl: Any, vars: Dict[str, Any], args: Dict[str, Any]) -> Any:
    """
    递归绑定参数：把 @var / @args.key 替换为实际值。
    仅示意：你项目里若已有模板展开工具，可直接复用。
    """
    if isinstance(tpl, str):
        if tpl.startswith("@"):
            key = tpl[1:]
            if key.startswith("args."):
                return args.get(key.split(".",1)[1])
            # 允许 @ps.xxx / @i 等
            return vars.get(key)
        return tpl
    if isinstance(tpl, list):
        return [_bind_params(x, vars, args) for x in tpl]
    if isinstance(tpl, dict):
        return {k: _bind_params(v, vars, args) for k, v in tpl.items()}
    return tpl

def _enforce_constraints(cons: Dict[str, Any], ps: Dict[str, Any]):
    if not cons: return
    if cons.get("must_stay_in_host"):
        host = (ps or {}).get("host") or (ps or {}).get("url","")
        if cons["must_stay_in_host"] not in host:
            raise ValidationError(f"macro host mismatch: expect {cons['must_stay_in_host']}")
    if cons.get("no_dom_click", False):
        # 执行期由 plan.execute 的白名单再校验一次
        pass
    if cons.get("max_steps") is not None and cons["max_steps"] <= 0:
        raise ValidationError("max_steps must be > 0")

@register_action("macro.run")
def macro_run(ctx, name: str, args: Dict[str, Any] = None, save: str = None, **_):
    """
    运行宏：从注册表读取 → 绑定参数 → 约束校验 → 展开为 MicroPlan → 交给 plan.execute。
    """
    macro = REGISTRY.get(name)  # MacroDef: {params, constraints, microplan}
    if not macro:
        raise ValidationError(f"macro not found: {name}")

    args = args or {}
    # 绑定参数
    bound_steps = _bind_params(macro["microplan"]["steps"], ctx.vars, args)
    plan = {"steps": bound_steps}  # 与你的 MicroPlanV1 对齐（如果需要加 meta，可在此扩展）

    # 约束校验（再次）
    _enforce_constraints(macro.get("constraints"), ctx.vars.get("ps"))

    # 安全：由执行器进行白名单与来源校验（bbox/rect 必须源自 @ps 或前序 save）
    # 注意 Python 保留字：把 from 参数改名为 from_plan 传入
    res = ctx.actions["plan.execute"](ctx, from_plan=plan, policy={
        "allowed": ["click_coordinates", "wheel_coordinates", "ext.extract", "wait_for"],
        "per_step_timeout_ms": 5000,
        "max_runtime_ms": 15000
    })

    if save:
        ctx.vars[save] = res
    ctx.events.log("macro.run.end", {"name": name, "ok": bool(res.get("ok"))})
    return res
```

> 说明
>
> * `REGISTRY.get(name)`：来自宏注册表（见 Sprint J 设计），安装 `.wfpack.tgz` 后热加载。
> * `from_plan`：避免与 Python 关键字冲突；你的 `plan.execute` 若固定用 `from`，就在执行器里同时接受 `from_plan` 合并。
> * 最终安全仍由 **plan.execute 的白名单 + 参数来源校验** 把关。

---

# 3) 频繁子序列挖掘骨架（PrefixSpan 简化）

`jobs/skills/mine_subsequences.py`

```python
# -*- coding: utf-8 -*-
"""
从 plans_history/plan_steps 中抽取“动作签名序列”，用简化 PrefixSpan 挖频繁子序列，
生成候选宏（YAML）。真实环境建议接 PG；这里提供最小骨架。
"""
import yaml
from collections import defaultdict, Counter
from typing import List, Tuple

MIN_SUP = 10         # 最小支持度
MAX_LEN = 5          # 子序列最大长度

def load_sequences() -> List[List[str]]:
    # TODO: 替换为从 Postgres 拉取成功 runs 的签名序列
    # 结构示例：["wheel@leftPane(-600)","click@list[i]","wait@quiet","extract@apply"]
    return []

def prefixspan(seqs: List[List[str]], min_sup: int, max_len: int) -> List[Tuple[List[str], int]]:
    results = []
    # 频繁一项
    counter = Counter()
    for s in seqs:
        counter.update(set(s))  # 去重计一次出现
    freq_items = [( [a], c ) for a,c in counter.items() if c >= min_sup]
    results.extend(freq_items)

    # 递归扩展
    def project(db: List[List[str]], pattern: List[str]) -> List[List[str]]:
        proj = []
        for s in db:
            try:
                # 找到 pattern 在 s 中的最后一个元素位置
                idx = 0
                for p in pattern:
                    idx = s.index(p, idx) + 1
                proj.append(s[idx:])  # 取剩余尾巴
            except ValueError:
                continue
        return proj

    def grow(db, pattern):
        if len(pattern) >= max_len:
            return
        # 统计可扩展项
        cand = Counter()
        for s in db:
            cand.update(set(s))  # 简化：去重
        for a, c in cand.items():
            if c < min_sup: 
                continue
            new_pat = pattern + [a]
            results.append((new_pat, c))
            grow(project(db, [a]), new_pat)

    # 对每个频繁一项尝试扩展
    for base, sup in freq_items:
        db_proj = project(seqs, base)
        grow(db_proj, base)

    # 去重 & 排序
    uniq = {}
    for pat, sup in results:
        uniq[tuple(pat)] = max(uniq.get(tuple(pat), 0), sup)
    out = sorted([(list(k), v) for k,v in uniq.items()], key=lambda x: (-x[1], -len(x[0])))
    return out

def to_macro_yaml(pat: List[str], host="ca.indeed.com") -> str:
    # 将签名模板化为 MicroPlan 片段（极简映射示例）
    steps = []
    for sig in pat:
        if sig.startswith("wheel@leftPane("):
            steps.append({ "do": "wheel_coordinates", "args": { "at_bbox": "@ps.panes.left.rect", "amount": -600 }})
        elif sig.startswith("click@list[i"):
            steps.append({ "do": "click_coordinates", "args": { "bbox": "@ps.lists[0].itemRects[@i + @index_offset]" }})
        elif sig == "wait@quiet":
            steps.append({ "do": "wait_for", "args": { "until": { "type": "ext.wait_quiet", "timeout_ms": 6000 }}})
        elif sig.startswith("extract@apply"):
            steps.append({ "do": "ext.extract", "args": { "mode": "find_button_bbox", "text_any_of": "@apply_texts" }})
        # 其他规则按需补充

    macro = {
      "name": "apply_click_flow",
      "version": "1.0.0",
      "host": host,
      "title": "Auto-generated macro",
      "description": "Mined from successful trajectories",
      "params": {
        "index_offset": { "type": "integer", "default": 0, "min": -2, "max": 2 },
        "apply_texts":  { "type": "array", "default": ["Apply","Quick Apply","立即申请"], "items": { "type": "string" } }
      },
      "constraints": { "must_stay_in_host": "indeed.com", "no_dom_click": True, "max_steps": len(steps) },
      "microplan": { "steps": steps }
    }
    return yaml.safe_dump(macro, sort_keys=False, allow_unicode=True)

def main():
    seqs = load_sequences()
    freq = prefixspan(seqs, MIN_SUP, MAX_LEN)
    if not freq:
        print("No frequent subsequences.")
        return
    pat, sup = freq[0]
    print(f"# Top pattern (support={sup}):", pat)
    yml = to_macro_yaml(pat)
    with open("skills/defs/_auto.apply_click_flow.yaml", "w", encoding="utf-8") as f:
        f.write(yml)
    print("Generated skills/defs/_auto.apply_click_flow.yaml")

if __name__ == "__main__":
    main()
```

---

## 建议下一步（超精简待办）

1. 把三份文件落到对应目录；
2. 在客户端启动时加载宏注册表（`REGISTRY.load_from_wfpack()` 或直接读 `skills/defs/*.yaml`）；
3. 在 Indeed 工作流里替换一处为 `{"do":"macro.run","name":"apply_click_flow"}`；
4. 跑一遍 E2E，确认事件里出现 `macro.run.end`，并且成功率与时延达标；
5. 然后再接 `.wfpack.tgz` 打包与签名、安装/回滚接口（按你现有市场打包规范）。

