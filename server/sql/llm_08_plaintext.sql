-- server/sql/llm_08_plaintext.sql
-- Stage 8: 多LLM路由 + 用户API Key（支持明文存储 + 管理后台可见）

-- 用户API密钥表（支持明文和加密两种模式）
create table if not exists user_api_keys (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  provider text not null,                     -- 'openai', 'gemini', 'deepseek', etc.
  name text,                                  -- 用户自定义名称
  mode text not null default 'ENCRYPTED',    -- 'PLAINTEXT' | 'ENCRYPTED'
  plaintext_key text,                         -- 明文密钥（仅PLAINTEXT模式）
  enc_key text,                              -- 加密后的密钥（base64）
  iv text,                                   -- 加密IV（base64）
  tag text,                                  -- 加密TAG（base64）
  last4 text not null,                       -- 后4位用于显示
  created_by uuid references users(id),      -- 创建者
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- 审计：管理员查看/导出密钥记录
create table if not exists admin_secret_audit (
  id uuid primary key default uuid_generate_v4(),
  admin_user_id uuid references users(id),
  action text not null,                       -- 'REVEAL' | 'EXPORT' | 'LIST_REVEAL'
  target_table text not null default 'user_api_keys',
  target_id uuid not null,                    -- 对应的 key id
  reason text,
  ip text,
  ua text,
  created_at timestamptz default now()
);

-- 添加用户角色字段（简单RBAC）
alter table users add column if not exists role text not null default 'user'; -- 'user' | 'admin'

-- LLM任务提交记录
create table if not exists llm_jobs (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  device_id uuid references devices(id),
  job_type text not null,                     -- 'chat_reply', 'code_gen', etc.
  provider text not null,                     -- 实际使用的提供商
  model text not null,                        -- 实际使用的模型
  prompt_pack_key text,                       -- 使用的prompt pack
  schema_key text,                            -- 使用的schema
  input_tokens int default 0,
  output_tokens int default 0,
  cost_cents bigint default 0,                -- 成本（分）
  status text default 'pending',              -- pending|completed|failed
  created_at timestamptz default now(),
  completed_at timestamptz
);

-- LLM使用量统计
create table if not exists llm_usage (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  provider text not null,
  model text not null,
  date date not null,
  total_input_tokens bigint default 0,
  total_output_tokens bigint default 0,
  total_cost_cents bigint default 0,
  job_count int default 0,
  unique(user_id, provider, model, date)
);

-- Prompt包管理
create table if not exists prompt_packs (
  id uuid primary key default uuid_generate_v4(),
  key text not null,                          -- 'wechat.sales.reply.v1'
  revision int not null default 1,
  content text not null,                      -- prompt模板
  variables jsonb default '[]'::jsonb,        -- 变量定义
  created_at timestamptz default now(),
  unique(key, revision)
);

-- JSON Schema管理
create table if not exists llm_schemas (
  id uuid primary key default uuid_generate_v4(),
  key text not null,                          -- 'WeChatReplyV1'
  revision int not null default 1,
  schema jsonb not null,                      -- JSON Schema
  created_at timestamptz default now(),
  unique(key, revision)
);

-- 路由策略配置
create table if not exists llm_policies (
  id uuid primary key default uuid_generate_v4(),
  job_type text not null unique,              -- 'chat_reply', 'code_gen', etc.
  strategy text not null,                     -- 'AUTO', 'FORCE:openai', 'FALLBACK:gemini,openai'
  updated_at timestamptz default now()
);

-- 创建管理员用户（如果不存在）
insert into users (email, password_hash, role)
  values ('admin@acme.com', '$2b$10$vI/D.iJuS.6z.wN.qbT.iuwNqzFz8D2K.HwP4J3K8Wt4sOzKHSJ2', 'admin')
  on conflict (email) do update set role = 'admin';

-- 插入默认订阅（如果不存在）
insert into subscriptions (user_id, plan, device_limit, hp_concurrency)
  select id, 'pro', 5, 3 from users where email='admin@acme.com'
  on conflict do nothing;

-- 插入示例路由策略
insert into llm_policies (job_type, strategy)
  values
    ('chat_reply', 'AUTO'),
    ('code_gen', 'FALLBACK:openai,gemini'),
    ('translate', 'FORCE:gemini')
  on conflict (job_type) do update set
    strategy = excluded.strategy,
    updated_at = now();

-- 插入示例Prompt Pack
insert into prompt_packs (key, revision, content, variables)
  values
    ('wechat.sales.reply.v1', 1, '你是销售助手。根据客户消息生成回复。\n\n客户消息：{{customer_message}}\n客户信息：{{customer_info}}\n\n请生成专业、友好的回复：', '["customer_message", "customer_info"]'::jsonb),
    ('code.review.v1', 1, '请审查以下代码并提供改进建议：\n\n```{{language}}\n{{code}}\n```\n\n重点关注：\n1. 性能优化\n2. 安全问题\n3. 代码风格\n4. 最佳实践', '["language", "code"]'::jsonb)
  on conflict (key, revision) do nothing;

-- 插入示例JSON Schema
insert into llm_schemas (key, revision, schema)
  values
    ('WeChatReplyV1', 1, '{
      "type": "object",
      "required": ["contact_name", "reply_text", "tone"],
      "properties": {
        "contact_name": {"type": "string", "description": "客户姓名"},
        "reply_text": {"type": "string", "description": "回复内容"},
        "tone": {"type": "string", "enum": ["professional", "friendly", "urgent"], "description": "回复语调"}
      }
    }'::jsonb),
    ('CodeReviewV1', 1, '{
      "type": "object",
      "required": ["overall_score", "issues", "suggestions"],
      "properties": {
        "overall_score": {"type": "integer", "minimum": 1, "maximum": 10, "description": "代码整体评分"},
        "issues": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "type": {"type": "string", "enum": ["performance", "security", "style", "logic"]},
              "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
              "description": {"type": "string"},
              "line_number": {"type": "integer"}
            }
          }
        },
        "suggestions": {
          "type": "array",
          "items": {"type": "string"}
        }
      }
    }'::jsonb)
  on conflict (key, revision) do nothing;