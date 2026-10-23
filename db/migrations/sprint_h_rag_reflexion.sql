-- Sprint H: RAG轨迹检索 + 在线Reflexion 数据库迁移
-- 运行: psql -h localhost -U your_user -d your_db -f db/migrations/sprint_h_rag_reflexion.sql

-- 1) 启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 2) 在 plans_history 上增加两列：指纹向量与轨迹向量
-- 统一使用 1024 维，若嵌入返回维度不同，客户端做 pad/trunc
ALTER TABLE plans_history ADD COLUMN IF NOT EXISTS fingerprint_embed vector(1024);
ALTER TABLE plans_history ADD COLUMN IF NOT EXISTS trajectory_embed  vector(1024);

-- 4) 创建向量索引 (IVFFLAT)
-- lists参数根据数据量调整，这里使用100作为默认值
CREATE INDEX IF NOT EXISTS idx_ph_fpvec
ON plans_history USING ivfflat (fingerprint_embed vector_cosine_ops)
WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_ph_trvec
ON plans_history USING ivfflat (trajectory_embed vector_cosine_ops)
WITH (lists = 100);

-- 5) 创建反思表
CREATE TABLE IF NOT EXISTS plan_reflections (
  id BIGSERIAL PRIMARY KEY,
  history_id BIGINT REFERENCES plans_history(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT now(),
  critique TEXT NOT NULL,           -- 简短可读的反思
  suggestions JSONB,                -- 结构化的修正建议
  reward_before DOUBLE PRECISION,   -- 反思前的奖励值
  tags TEXT[]                       -- 标签：auto, manual, reviewed等
);

-- 6) 创建常用索引
CREATE INDEX IF NOT EXISTS idx_plans_history_host_goal
ON plans_history(host, goal_hash);

CREATE INDEX IF NOT EXISTS idx_plans_history_fingerprint
ON plans_history(fingerprint);

CREATE INDEX IF NOT EXISTS idx_plans_history_reward
ON plans_history(reward DESC);

CREATE INDEX IF NOT EXISTS idx_plans_history_created_at
ON plans_history(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_plan_reflections_hist
ON plan_reflections(history_id);

CREATE INDEX IF NOT EXISTS idx_plan_reflections_created_at
ON plan_reflections(created_at DESC);

-- 7) 添加触发器更新 updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_plans_history_updated_at ON plans_history;
CREATE TRIGGER update_plans_history_updated_at
    BEFORE UPDATE ON plans_history
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 8) 创建计划候选表（如果不存在）- 用于DPO训练
CREATE TABLE IF NOT EXISTS plan_candidates (
  id BIGSERIAL PRIMARY KEY,
  history_id BIGINT REFERENCES plans_history(id) ON DELETE CASCADE,
  candidate_idx INTEGER NOT NULL,   -- 候选序号
  microplan JSONB NOT NULL,         -- MicroPlanV1 JSON
  score DOUBLE PRECISION,           -- 候选评分
  selected BOOLEAN DEFAULT FALSE,   -- 是否被选中执行
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_plan_candidates_history
ON plan_candidates(history_id);

CREATE INDEX IF NOT EXISTS idx_plan_candidates_selected
ON plan_candidates(selected, score DESC);

-- 9) 创建嵌入配置表
CREATE TABLE IF NOT EXISTS embedding_configs (
  id BIGSERIAL PRIMARY KEY,
  provider TEXT NOT NULL,           -- openai, sentence_transformers, etc
  model_name TEXT NOT NULL,         -- text-embedding-3-large, etc
  dimension INTEGER NOT NULL,       -- 模型输出维度
  is_active BOOLEAN DEFAULT FALSE,  -- 当前使用的配置
  created_at TIMESTAMPTZ DEFAULT now()
);

-- 插入默认配置
INSERT INTO embedding_configs (provider, model_name, dimension, is_active)
VALUES ('openai', 'text-embedding-3-large', 1536, TRUE)
ON CONFLICT DO NOTHING;

-- 10) 创建向量检索统计表
CREATE TABLE IF NOT EXISTS vector_recall_stats (
  date DATE PRIMARY KEY,
  total_queries INTEGER DEFAULT 0,
  avg_recall_time_ms DOUBLE PRECISION DEFAULT 0,
  top_k_hit_rate DOUBLE PRECISION DEFAULT 0,
  vector_quality_score DOUBLE PRECISION DEFAULT 0
);

COMMENT ON TABLE plans_history IS 'Sprint H: 计划历史表，增加向量嵌入字段用于RAG检索';
COMMENT ON TABLE plan_reflections IS 'Sprint H: 计划反思表，存储在线生成的反思短评';
COMMENT ON TABLE plan_candidates IS 'Sprint I: 计划候选表，用于DPO偏好对训练';
COMMENT ON TABLE embedding_configs IS 'Sprint H: 嵌入模型配置表';
COMMENT ON TABLE vector_recall_stats IS 'Sprint H: 向量检索统计表';