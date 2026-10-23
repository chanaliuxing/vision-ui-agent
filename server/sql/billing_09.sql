-- server/sql/billing_09.sql
-- Stage 9: 结算与账单（订阅 + 用量计费 + 多渠道支付）

-- 价格与产品
create table if not exists plan_products (
  id uuid primary key default uuid_generate_v4(),
  key text unique not null,                 -- 'free', 'pro', 'team'
  name text not null,
  description text,
  device_limit int not null,
  hp_concurrency int not null,
  monthly_price_usd numeric(12,2) not null,
  yearly_price_usd numeric(12,2) not null,
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);

-- 扩展订阅表
alter table subscriptions add column if not exists external_sub_id text; -- stripe subscription id
alter table subscriptions add column if not exists currency text default 'usd';
alter table subscriptions add column if not exists billing_cycle_start timestamptz;
alter table subscriptions add column if not exists billing_cycle_end timestamptz;

-- 扩展用户表
alter table users add column if not exists stripe_customer_id text;

-- 钱包（可选）
create table if not exists wallets (
  user_id uuid primary key references users(id),
  balance_cents bigint not null default 0,  -- 以分计价，避免浮点
  currency text not null default 'usd',
  updated_at timestamptz default now()
);

create table if not exists wallet_txns (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  type text not null,                        -- 'topup' | 'debit' | 'refund' ...
  amount_cents bigint not null,
  currency text not null default 'usd',
  ref text,                                  -- 对应的invoice/payment id等
  created_at timestamptz default now()
);

-- 发票与行
create table if not exists invoices (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  period_start timestamptz not null,
  period_end timestamptz not null,
  currency text not null default 'usd',
  subtotal_cents bigint not null default 0,
  tax_cents bigint not null default 0,
  total_cents bigint not null default 0,
  status text not null default 'draft',      -- draft|open|paid|void|uncollectible
  external_invoice_id text,                  -- stripe invoice id
  created_at timestamptz default now(),
  finalized_at timestamptz,
  paid_at timestamptz
);

create table if not exists invoice_lines (
  id uuid primary key default uuid_generate_v4(),
  invoice_id uuid references invoices(id) on delete cascade,
  kind text not null,                        -- 'subscription' | 'usage' | 'marketplace' | 'credit'
  description text,
  quantity int,
  unit_amount_cents bigint,                  -- 单价（分）
  amount_cents bigint not null,              -- 行金额（分）
  meta jsonb default '{}'::jsonb
);

-- 用量聚合（由 llm_usage 汇总写入）
create table if not exists usage_rollups (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  period_start timestamptz not null,
  period_end timestamptz not null,
  provider text not null,
  model text not null,
  prompt_tokens bigint not null,
  completion_tokens bigint not null,
  amount_cents bigint not null,
  currency text not null default 'usd',
  created_at timestamptz default now(),
  unique(user_id, period_start, period_end, provider, model)
);

-- 支付流水
create table if not exists payments (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  invoice_id uuid references invoices(id),
  provider text not null,                    -- stripe|wxpay|alipay...
  external_payment_id text,
  currency text not null default 'usd',
  amount_cents bigint not null,
  status text not null,                      -- succeeded|failed|pending|refunded
  created_at timestamptz default now()
);

-- 发票阈值/信用限额
create table if not exists billing_limits (
  user_id uuid primary key references users(id),
  soft_cap_cents bigint not null default 1000,  -- 超过发提醒
  hard_cap_cents bigint not null default 2000   -- 超过限流/停止
);

-- 市场 workflow 购买与授权（预留给阶段10）
create table if not exists marketplace_entitlements (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  workflow_key text not null,
  seats int not null default 1,
  expires_at timestamptz,
  created_at timestamptz default now(),
  unique(user_id, workflow_key)
);

-- 插入示例产品计划
insert into plan_products (key, name, description, device_limit, hp_concurrency, monthly_price_usd, yearly_price_usd, metadata)
values
  ('free', 'Free Plan', 'Basic automation with limited features', 1, 1, 0.00, 0.00, '{"features": ["basic_automation", "1_device"]}'),
  ('pro', 'Pro Plan', 'Advanced automation for professionals', 3, 2, 29.99, 299.99, '{"features": ["advanced_automation", "3_devices", "priority_support"]}'),
  ('team', 'Team Plan', 'Enterprise automation for teams', 10, 5, 99.99, 999.99, '{"features": ["enterprise_automation", "10_devices", "team_management", "premium_support"]}')
on conflict (key) do update set
  name = excluded.name,
  description = excluded.description,
  device_limit = excluded.device_limit,
  hp_concurrency = excluded.hp_concurrency,
  monthly_price_usd = excluded.monthly_price_usd,
  yearly_price_usd = excluded.yearly_price_usd,
  metadata = excluded.metadata;

-- 为现有用户设置默认计费限制
insert into billing_limits (user_id, soft_cap_cents, hard_cap_cents)
select id, 5000, 10000 from users
on conflict (user_id) do nothing;

-- 为现有用户创建钱包
insert into wallets (user_id, balance_cents)
select id, 0 from users
on conflict (user_id) do nothing;