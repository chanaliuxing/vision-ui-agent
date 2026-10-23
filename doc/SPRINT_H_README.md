# Sprint H: RAG轨迹检索 + 在线Reflexion

基于upgrade2.md的完整实现，为UI自动化系统增加RAG轨迹检索和在线反思功能。

## 🎯 功能概览

### 核心特性
- **RAG轨迹检索**: 在生成计划前检索历史成功轨迹作为参考
- **在线Reflexion**: 执行失败或奖励低时自动生成反思短评
- **向量化存储**: 使用pgvector存储指纹和轨迹的嵌入向量
- **多Provider支持**: 支持OpenAI、SentenceTransformers等嵌入提供商

### 技术架构
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   工作流执行    │───▶│  RAG轨迹检索     │───▶│   LLM规划       │
│                 │    │ (mem.recall)     │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                                               │
         │              ┌──────────────────┐             │
         └─────────────▶│  在线反思        │◀────────────┘
                        │ (plan.reflect)   │
                        └──────────────────┘
```

## 📁 文件结构

```
Sprint H 实现文件:
├── db/migrations/
│   └── sprint_h_rag_reflexion.sql          # 数据库迁移脚本
├── server/services/
│   └── embeddings.py                       # 嵌入服务
├── server/routes/
│   └── plans_recall.py                     # 检索API
├── runtime/actions/
│   ├── mem_recall.py                       # mem.recall动作
│   └── plan_reflect.py                     # plan.reflect动作
├── jobs/
│   └── backfill_embeddings.py              # 嵌入回填脚本
├── tools/
│   └── wf_sprint_h.py                      # CLI工具
├── flows/
│   └── sprint_h_example.json               # 示例工作流
├── test_sprint_h.py                        # 测试脚本
└── SPRINT_H_README.md                      # 本文档
```

## 🚀 快速开始

### 1. 数据库迁移

```bash
# 确保已安装pgvector扩展
psql -h localhost -U your_user -d your_db -f db/migrations/sprint_h_rag_reflexion.sql
```

### 2. 配置嵌入服务

```bash
# 设置OpenAI API密钥（推荐）
export OPENAI_API_KEY="your-api-key"

# 或安装本地模型
pip install sentence-transformers
```

### 3. 启动服务

```bash
# 启动Recall API
uvicorn server.routes.plans_recall:app --host 0.0.0.0 --port 8003

# 回填历史数据的嵌入向量
python jobs/backfill_embeddings.py --since=30d --batch-size=50
```

### 4. 运行示例

```bash
# 测试嵌入服务
python tools/wf_sprint_h.py embedding --text "Click apply button"

# 检索相似轨迹
python tools/wf_sprint_h.py recall --host ca.indeed.com --goal "apply job" --k 5

# 运行完整测试
python test_sprint_h.py
```

## 🔧 API参考

### mem.recall 动作

检索相似的历史成功轨迹供LLM参考。

```json
{
  "do": "mem.recall",
  "goal": "apply current item",
  "fingerprint": "@fingerprint(@ps)",
  "k": 5,
  "min_reward": 0.5,
  "since": "90d",
  "save": "refs"
}
```

**参数说明:**
- `goal`: 目标描述
- `fingerprint`: 页面指纹（可选，优先级高）
- `k`: 返回的引用数量（1-20）
- `min_reward`: 最小奖励阈值（0.0-2.0）
- `since`: 时间范围（如30d, 7d, 24h）
- `save`: 保存结果的变量名

### plan.reflect 动作

在执行失败或奖励低时生成反思短评。

```json
{
  "do": "plan.reflect",
  "when": "@res['ok']==false || @res['reward'] < 0.5",
  "max_len": 300,
  "save": "reflection"
}
```

**参数说明:**
- `when`: 触发条件表达式
- `max_len`: 反思文本最大长度
- `provider`: LLM提供商（可选）
- `save`: 保存结果的变量名

### REST API

#### GET /plans/recall
检索相似轨迹

```bash
curl "http://localhost:8003/plans/recall?host=ca.indeed.com&k=5&min_reward=0.5"
```

#### POST /plans/reflect
创建反思记录

```bash
curl -X POST "http://localhost:8003/plans/reflect" \
  -H "Content-Type: application/json" \
  -d '{
    "history_id": 123,
    "critique": "执行失败，需要改进动作序列",
    "reward_before": 0.3
  }'
```

## 🔬 工作流集成

### 基本用法

```json
{
  "version": "1.2",
  "features": {
    "planner": {
      "strategy": "agentq",
      "memory": {
        "rag": true,
        "k": 5,
        "use_reflexion": true,
        "reward_threshold": 0.5
      }
    }
  },
  "states": {
    "main": {
      "actions": [
        {"do": "ext.get_pagestate", "save": "ps"},
        {"do": "mem.recall", "goal": "@goal", "fingerprint": "@fingerprint(@ps)", "save": "refs"},
        {"do": "llm.plan", "references": "@refs", "save": "cands"},
        {"do": "plan.execute", "from": "@choice['plan']", "save": "res"},
        {"do": "plan.reflect", "when": "@res['ok']==false || @res['reward'] < 0.5"}
      ]
    }
  }
}
```

### 高级特性

- **智能回退**: 检索失败时自动降级为基于host的过滤
- **向量相似度**: 基于cosine距离的精确匹配
- **结构化建议**: 从反思文本中自动提取可执行建议
- **事件记录**: 完整的可观测性支持

## 🛠️ CLI工具

Sprint H提供了强大的命令行工具：

```bash
# 查看系统状态
python tools/wf_sprint_h.py status

# 检索相似轨迹
python tools/wf_sprint_h.py recall --host ca.indeed.com --goal "apply job"

# 创建反思
python tools/wf_sprint_h.py reflect --run-id 123 --critique "需要改进点击精度"

# 测试嵌入服务
python tools/wf_sprint_h.py embedding --text "your test text"

# 回填历史数据
python tools/wf_sprint_h.py backfill --since 30d --batch-size 50
```

## 📊 性能指标

### 目标指标
- **成功率提升**: 相对基线 ≥3%
- **Token节省**: LLM计划token平均下降
- **检索延迟**: <100ms (p95)
- **反思生成**: <2s

### 监控事件
- `mem.recall.start/end`: 检索过程
- `plan.reflect.start/end`: 反思生成
- `vector.similarity`: 向量相似度计算

## 🔒 安全考虑

- **参数验证**: 所有API输入严格验证
- **来源校验**: 坐标和选择器必须来自可信源
- **表达式安全**: 条件表达式仅允许安全操作
- **隐私保护**: 仅存储结构化动作签名，不含截图

## 🐛 故障排除

### 常见问题

1. **嵌入服务不可用**
   ```bash
   # 检查API密钥
   echo $OPENAI_API_KEY

   # 或安装本地模型
   pip install sentence-transformers
   ```

2. **向量索引错误**
   ```sql
   -- 删除并重建索引
   DROP INDEX IF EXISTS idx_ph_fpvec;
   CREATE INDEX idx_ph_fpvec ON plans_history USING hnsw (fingerprint_embed vector_cosine_ops);
   ```

3. **检索结果为空**
   ```bash
   # 检查数据是否已回填
   python jobs/backfill_embeddings.py --dry-run --since 7d
   ```

### 调试技巧

- 使用 `--verbose` 标志查看详细日志
- 检查 `out/logs/` 目录中的事件日志
- 使用 `mock` provider进行离线测试

## 🔄 升级路径

Sprint H为后续Sprint奠定基础：

- **Sprint I**: 将收集偏好对数据用于DPO训练
- **Sprint J**: 基于高频轨迹生成可复用宏动作
- **集成**: 与现有AgentQ/MCTS策略无缝配合

## 📝 开发指南

### 添加新的嵌入提供商

```python
class CustomEmbeddingProvider(EmbeddingProvider):
    async def embed(self, texts: List[str]) -> List[List[float]]:
        # 实现你的嵌入逻辑
        pass

# 在embeddings.py中注册
embedding_service.providers["custom"] = CustomEmbeddingProvider(config)
```

### 扩展反思模板

修改 `plan_reflect.py` 中的 `_build_critique_prompt` 方法来自定义反思提示。

### 自定义向量检索

实现自己的检索逻辑，替换 `plans_recall.py` 中的查询逻辑。

## 📊 测试覆盖

运行完整测试套件：

```bash
python test_sprint_h.py
```

测试包括：
- ✅ 嵌入服务多provider支持
- ✅ 记忆回想动作
- ✅ 计划反思动作
- ✅ 端到端集成测试

## 🎉 总结

Sprint H成功实现了RAG轨迹检索和在线反思功能，为UI自动化系统增加了智能记忆和自我改进能力。通过历史成功案例的引导和失败经验的反思，系统能够持续优化执行策略，提升自动化任务的成功率。