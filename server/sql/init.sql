-- server/sql/init.sql
create extension if not exists "uuid-ossp";

create table if not exists users(
  id uuid primary key default uuid_generate_v4(),
  email text unique not null,
  password_hash text not null,
  created_at timestamptz default now(),
  status int default 1
);

create table if not exists subscriptions(
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  plan text not null,            -- free/pro/team
  device_limit int not null,
  hp_concurrency int not null default 1,
  status text not null default 'active',
  started_at timestamptz default now(),
  ends_at timestamptz
);

create table if not exists devices(
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  machine_code text not null unique,
  name text,
  status int default 1,
  capabilities jsonb default '{}'::jsonb,
  last_seen timestamptz,
  created_at timestamptz default now()
);

-- 演示用：一条默认订阅
insert into users (email, password_hash)
  values ('demo@acme.com', '$2b$10$ZV8b5/Q5O3l5Z5E5Y5Y5YO4g7J7l7t7t7t7t7t7t7t7t7t7t7t7t7t')
  on conflict do nothing; -- 'demo123'的bcrypt hash

insert into subscriptions (user_id, plan, device_limit, hp_concurrency)
  select id, 'pro', 3, 2 from users where email='demo@acme.com'
  on conflict do nothing;