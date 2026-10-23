-- Sprint I: DPO/RLAIF 离线训练与上线 数据库扩展
-- 运行: psql -h localhost -U your_user -d your_db -f db/migrations/sprint_i_dpo_rlaif.sql

-- 1) 计划候选表 (如果Sprint H未创建)
CREATE TABLE IF NOT EXISTS plan_candidates (
  id BIGSERIAL PRIMARY KEY,
  history_id BIGINT REFERENCES plans_history(id) ON DELETE CASCADE,
  candidate_idx INTEGER NOT NULL,   -- 候选序号
  microplan JSONB NOT NULL,         -- MicroPlanV1 JSON
  score DOUBLE PRECISION,           -- 候选评分
  selected BOOLEAN DEFAULT FALSE,   -- 是否被选中执行
  simulation_reward DOUBLE PRECISION, -- 模拟奖励
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_plan_candidates_history ON plan_candidates(history_id);
CREATE INDEX IF NOT EXISTS idx_plan_candidates_selected ON plan_candidates(selected, score DESC);
CREATE INDEX IF NOT EXISTS idx_plan_candidates_reward ON plan_candidates(simulation_reward DESC);

-- 2) 偏好对表 - 存储训练数据
CREATE TABLE IF NOT EXISTS preference_pairs (
  id BIGSERIAL PRIMARY KEY,
  fingerprint_hash TEXT NOT NULL,    -- 指纹哈希，用于分组
  host TEXT NOT NULL,
  goal_hash TEXT,

  -- 上下文信息
  context JSONB NOT NULL,            -- { page_state_meta, references, constraints }

  -- 偏好对
  preferred_plan JSONB NOT NULL,     -- 获胜的计划
  rejected_plan JSONB NOT NULL,      -- 失败的计划

  -- 元数据
  reward_preferred DOUBLE PRECISION NOT NULL,
  reward_rejected DOUBLE PRECISION NOT NULL,
  reward_margin DOUBLE PRECISION NOT NULL,   -- preferred - rejected

  -- 来源信息
  source_type TEXT NOT NULL,         -- 'candidates' | 'trajectories' | 'synthetic'
  preferred_history_id BIGINT REFERENCES plans_history(id),
  rejected_history_id BIGINT REFERENCES plans_history(id),

  -- 质量控制
  quality_score DOUBLE PRECISION,    -- 偏好对质量评分
  teacher_verified BOOLEAN DEFAULT FALSE,

  created_at TIMESTAMPTZ DEFAULT now(),
  dataset_split TEXT DEFAULT 'train' -- 'train' | 'val' | 'test'
);

CREATE INDEX IF NOT EXISTS idx_preference_pairs_fingerprint ON preference_pairs(fingerprint_hash);
CREATE INDEX IF NOT EXISTS idx_preference_pairs_host_goal ON preference_pairs(host, goal_hash);
CREATE INDEX IF NOT EXISTS idx_preference_pairs_margin ON preference_pairs(reward_margin DESC);
CREATE INDEX IF NOT EXISTS idx_preference_pairs_quality ON preference_pairs(quality_score DESC);
CREATE INDEX IF NOT EXISTS idx_preference_pairs_split ON preference_pairs(dataset_split);

-- 3) Planner版本管理表
CREATE TABLE IF NOT EXISTS planner_versions (
  id BIGSERIAL PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  version TEXT NOT NULL,
  type TEXT NOT NULL,               -- "prompt" | "lora" | "fine_tuned"

  -- 模型信息
  base_provider TEXT NOT NULL,      -- "claude-3.5" | "gpt-4o-mini" | "llama-3-8b"
  base_model TEXT NOT NULL,
  model_path TEXT,                  -- 存储路径或模型ID

  -- 配置
  config JSONB,                     -- 模型配置参数
  prompt_template TEXT,             -- Prompt模板（如果是prompt类型）

  -- 性能指标
  training_metrics JSONB,           -- 训练指标
  eval_metrics JSONB,               -- 评估指标

  -- 状态管理
  status TEXT NOT NULL DEFAULT 'training',  -- 'training' | 'staging' | 'prod' | 'deprecated' | 'rollback'
  notes TEXT,

  created_at TIMESTAMPTZ DEFAULT now(),
  deployed_at TIMESTAMPTZ,
  deprecated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_planner_versions_status ON planner_versions(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_planner_versions_type ON planner_versions(type, status);

-- 4) A/B测试分配表
CREATE TABLE IF NOT EXISTS ab_assignments (
  id BIGSERIAL PRIMARY KEY,
  host TEXT NOT NULL,
  strategy TEXT NOT NULL,           -- agentq | mcts-full | custom
  planner_version_id BIGINT REFERENCES planner_versions(id),

  -- 流量控制
  traffic_pct SMALLINT NOT NULL DEFAULT 20,  -- 流量百分比
  enabled BOOLEAN DEFAULT TRUE,

  -- 条件过滤
  user_filters JSONB,               -- 用户条件过滤
  device_filters JSONB,             -- 设备条件过滤

  -- 监控阈值
  failure_threshold DOUBLE PRECISION DEFAULT 0.1,    -- 失败率阈值
  cost_threshold DOUBLE PRECISION DEFAULT 1.3,       -- 成本阈值倍数

  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ab_assignments_host ON ab_assignments(host, enabled);
CREATE INDEX IF NOT EXISTS idx_ab_assignments_version ON ab_assignments(planner_version_id);

-- 5) Teacher评分表 (RLAIF)
CREATE TABLE IF NOT EXISTS teacher_judgments (
  id BIGSERIAL PRIMARY KEY,
  fingerprint_hash TEXT NOT NULL,
  context JSONB NOT NULL,           -- 评分上下文

  -- 候选信息
  candidates JSONB NOT NULL,        -- 候选计划列表

  -- Teacher评分
  scores DOUBLE PRECISION[] NOT NULL,     -- 各候选的评分
  preference_ranking INTEGER[] NOT NULL,  -- 偏好排序
  rationales TEXT[],                      -- 评分理由

  -- Teacher配置
  teacher_provider TEXT NOT NULL,   -- 使用的Teacher模型
  teacher_model TEXT NOT NULL,
  teacher_version TEXT,

  -- 质量控制
  confidence_score DOUBLE PRECISION,
  cache_hit BOOLEAN DEFAULT FALSE,  -- 是否命中缓存

  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_teacher_judgments_fingerprint ON teacher_judgments(fingerprint_hash);
CREATE INDEX IF NOT EXISTS idx_teacher_judgments_teacher ON teacher_judgments(teacher_provider, teacher_model);
CREATE INDEX IF NOT EXISTS idx_teacher_judgments_confidence ON teacher_judgments(confidence_score DESC);

-- 6) 训练任务表
CREATE TABLE IF NOT EXISTS training_jobs (
  id BIGSERIAL PRIMARY KEY,
  job_name TEXT UNIQUE NOT NULL,
  job_type TEXT NOT NULL,           -- 'prompt_tuning' | 'dpo_training' | 'evaluation'

  -- 输入数据
  dataset_config JSONB NOT NULL,    -- 数据集配置
  training_config JSONB NOT NULL,   -- 训练配置

  -- 状态跟踪
  status TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  progress DOUBLE PRECISION DEFAULT 0,     -- 进度百分比

  -- 输出
  output_path TEXT,                 -- 输出路径
  metrics JSONB,                    -- 训练指标
  logs TEXT,                        -- 训练日志

  -- 时间戳
  created_at TIMESTAMPTZ DEFAULT now(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,

  -- 资源使用
  compute_resources JSONB,          -- 计算资源配置
  estimated_cost DOUBLE PRECISION,
  actual_cost DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_training_jobs_status ON training_jobs(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_training_jobs_type ON training_jobs(job_type, status);

-- 7) 性能监控表
CREATE TABLE IF NOT EXISTS planner_performance (
  date DATE,
  planner_version_id BIGINT REFERENCES planner_versions(id),
  host TEXT,

  -- 核心指标
  total_runs INTEGER DEFAULT 0,
  successful_runs INTEGER DEFAULT 0,
  avg_reward DOUBLE PRECISION DEFAULT 0,
  avg_steps DOUBLE PRECISION DEFAULT 0,
  avg_tokens DOUBLE PRECISION DEFAULT 0,
  avg_latency_ms INTEGER DEFAULT 0,

  -- 成本指标
  total_cost DOUBLE PRECISION DEFAULT 0,
  cost_per_success DOUBLE PRECISION DEFAULT 0,

  -- 错误统计
  error_count INTEGER DEFAULT 0,
  timeout_count INTEGER DEFAULT 0,

  PRIMARY KEY(date, planner_version_id, host)
);

CREATE INDEX IF NOT EXISTS idx_planner_performance_date ON planner_performance(date DESC);
CREATE INDEX IF NOT EXISTS idx_planner_performance_version ON planner_performance(planner_version_id, date DESC);

-- 8) 创建触发器
CREATE OR REPLACE FUNCTION update_ab_assignments_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_ab_assignments_updated_at ON ab_assignments;
CREATE TRIGGER update_ab_assignments_updated_at
    BEFORE UPDATE ON ab_assignments
    FOR EACH ROW EXECUTE FUNCTION update_ab_assignments_updated_at();

-- 9) 数据集分割函数
CREATE OR REPLACE FUNCTION split_preference_pairs()
RETURNS void AS $$
BEGIN
    -- 按80/10/10分割数据集
    UPDATE preference_pairs
    SET dataset_split = CASE
        WHEN random() < 0.8 THEN 'train'
        WHEN random() < 0.9 THEN 'val'
        ELSE 'test'
    END
    WHERE dataset_split = 'train';
END;
$$ language 'plpgsql';

-- 10) 插入默认配置
INSERT INTO planner_versions (name, version, type, base_provider, base_model, status, notes)
VALUES
    ('baseline_agentq', '1.0.0', 'prompt', 'claude-3.5', 'claude-3-5-sonnet-20241022', 'prod', 'Baseline AgentQ planner'),
    ('baseline_mcts', '1.0.0', 'prompt', 'gpt-4o', 'gpt-4o-mini', 'staging', 'Baseline MCTS planner')
ON CONFLICT (name) DO NOTHING;

COMMENT ON TABLE preference_pairs IS 'Sprint I: 偏好对训练数据，支持DPO/RLAIF训练';
COMMENT ON TABLE planner_versions IS 'Sprint I: Planner版本管理，支持Prompt和模型版本';
COMMENT ON TABLE ab_assignments IS 'Sprint I: A/B测试流量分配和灰度发布';
COMMENT ON TABLE teacher_judgments IS 'Sprint I: Teacher模型评分，支持RLAIF数据生成';
COMMENT ON TABLE training_jobs IS 'Sprint I: 训练任务管理和监控';
COMMENT ON TABLE planner_performance IS 'Sprint I: Planner性能监控和A/B分析';