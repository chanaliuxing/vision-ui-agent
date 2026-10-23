-- Stage 10: Workflow Marketplace Database Schema
-- Workflow 市场（上架/购买/授权/安装/更新）

-- Publishers and revenue sharing
create table if not exists publishers (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  name text not null,
  contact_email text,
  stripe_account_id text,                    -- Stripe Connect account for revenue sharing
  status text not null default 'active',
  revenue_share_percent decimal(5,2) default 70.00,  -- Publisher's share (70%)
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Workflow listings in the marketplace
create table if not exists marketplace_listings (
  id uuid primary key default uuid_generate_v4(),
  publisher_id uuid references publishers(id),
  key text not null,                         -- unique identifier like "xhs.crawler.v1"
  title text not null,
  summary text,
  description text,
  category text,                             -- chat-automation / scraping / sales-assist
  price_cents bigint not null default 0,    -- in cents
  currency text not null default 'usd',
  visibility text not null default 'public', -- public/private/unlisted
  latest_version text,                       -- semver like "1.2.0"
  download_count bigint not null default 0,
  rating_avg decimal(3,2) default 0.00,
  rating_count int default 0,
  featured boolean default false,
  status text not null default 'active',    -- active/suspended/removed
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  unique (publisher_id, key)
);

-- Version history and package metadata
create table if not exists marketplace_versions (
  id uuid primary key default uuid_generate_v4(),
  listing_id uuid references marketplace_listings(id) on delete cascade,
  version text not null,                     -- semver
  engine_min text,                          -- minimum compatible engine version
  engine_max text,                          -- maximum compatible engine version
  sha256 text not null,                     -- package body hash
  size_bytes bigint not null,
  storage_url text not null,                -- S3/local object storage URL
  manifest jsonb not null,                  -- workflow manifest and metadata
  signature text not null,                  -- base64(ed25519 signature)
  changelog text,                           -- what's new in this version
  is_prerelease boolean default false,
  created_at timestamptz default now(),
  unique (listing_id, version)
);

-- Purchase orders
create table if not exists marketplace_orders (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  listing_id uuid references marketplace_listings(id),
  version text,                             -- purchased version (null = always latest)
  quantity int not null default 1,          -- seat count
  amount_cents bigint not null,
  currency text not null default 'usd',
  provider text not null default 'stripe',
  external_order_id text,                   -- stripe checkout/payment intent id
  status text not null default 'pending',   -- pending|paid|refunded|canceled
  refund_reason text,
  created_at timestamptz default now(),
  paid_at timestamptz,
  refunded_at timestamptz
);

-- Extend existing marketplace_entitlements table (from Stage 7)
alter table marketplace_entitlements
  add column if not exists listing_id uuid references marketplace_listings(id),
  add column if not exists version text,     -- entitlement version constraint like "~1.2"
  add column if not exists seats int not null default 1,
  add column if not exists device_bound boolean not null default true,
  add column if not exists created_via_order uuid references marketplace_orders(id);

-- Device installations tracking
create table if not exists marketplace_installs (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  device_id uuid references devices(id),
  listing_id uuid references marketplace_listings(id),
  version text not null,                    -- installed version
  status text not null default 'installed', -- installed|revoked|pending_update
  auto_update boolean default true,
  last_used_at timestamptz,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  unique (device_id, listing_id)
);

-- Reviews and ratings
create table if not exists marketplace_reviews (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  listing_id uuid references marketplace_listings(id),
  rating int not null check (rating >= 1 and rating <= 5),
  title text,
  comment text,
  version text,                             -- version reviewed
  helpful_count int default 0,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  unique (user_id, listing_id)
);

-- Usage analytics for marketplace
create table if not exists marketplace_analytics (
  id uuid primary key default uuid_generate_v4(),
  listing_id uuid references marketplace_listings(id),
  user_id uuid references users(id),
  device_id uuid references devices(id),
  event_type text not null,                 -- view|download|install|uninstall|usage
  version text,
  metadata jsonb default '{}'::jsonb,
  ip_address inet,
  user_agent text,
  created_at timestamptz default now()
);

-- Revenue tracking and payouts
create table if not exists marketplace_payouts (
  id uuid primary key default uuid_generate_v4(),
  publisher_id uuid references publishers(id),
  period_start timestamptz not null,
  period_end timestamptz not null,
  gross_revenue_cents bigint not null,
  platform_fee_cents bigint not null,
  publisher_share_cents bigint not null,
  stripe_transfer_id text,                  -- Stripe Connect transfer ID
  status text not null default 'pending',   -- pending|processing|completed|failed
  created_at timestamptz default now(),
  paid_at timestamptz
);

-- Categories for organization
create table if not exists marketplace_categories (
  id uuid primary key default uuid_generate_v4(),
  name text not null unique,
  description text,
  icon text,
  sort_order int default 0,
  active boolean default true,
  created_at timestamptz default now()
);

-- Insert default categories
insert into marketplace_categories (name, description, icon, sort_order) values
  ('Chat Automation', 'Workflows for social media and messaging automation', '💬', 1),
  ('Web Scraping', 'Data extraction and web automation workflows', '🕷️', 2),
  ('Sales & Marketing', 'Lead generation and sales automation', '📈', 3),
  ('Data Processing', 'Data transformation and analysis workflows', '📊', 4),
  ('Productivity', 'General productivity and task automation', '⚡', 5),
  ('Developer Tools', 'Development and testing automation', '🛠️', 6)
on conflict (name) do nothing;

-- Publisher verification and badges
create table if not exists publisher_badges (
  id uuid primary key default uuid_generate_v4(),
  publisher_id uuid references publishers(id),
  badge_type text not null,                 -- verified|featured|top_seller|new
  granted_at timestamptz default now(),
  expires_at timestamptz,
  unique (publisher_id, badge_type)
);

-- Workflow dependencies (for complex workflows that depend on others)
create table if not exists marketplace_dependencies (
  id uuid primary key default uuid_generate_v4(),
  listing_id uuid references marketplace_listings(id),
  required_listing_id uuid references marketplace_listings(id),
  min_version text,
  max_version text,
  optional boolean default false,
  created_at timestamptz default now(),
  unique (listing_id, required_listing_id)
);

-- Create indexes for performance
create index if not exists idx_marketplace_listings_category on marketplace_listings(category);
create index if not exists idx_marketplace_listings_featured on marketplace_listings(featured) where featured = true;
create index if not exists idx_marketplace_listings_status on marketplace_listings(status);
create index if not exists idx_marketplace_versions_listing on marketplace_versions(listing_id);
create index if not exists idx_marketplace_orders_user on marketplace_orders(user_id);
create index if not exists idx_marketplace_orders_status on marketplace_orders(status);
create index if not exists idx_marketplace_installs_device on marketplace_installs(device_id);
create index if not exists idx_marketplace_installs_user on marketplace_installs(user_id);
create index if not exists idx_marketplace_analytics_listing on marketplace_analytics(listing_id);
create index if not exists idx_marketplace_analytics_event on marketplace_analytics(event_type);
create index if not exists idx_marketplace_reviews_listing on marketplace_reviews(listing_id);
create index if not exists idx_marketplace_reviews_rating on marketplace_reviews(rating);

-- Functions for rating calculations
create or replace function update_listing_rating()
returns trigger as $$
begin
  update marketplace_listings
  set
    rating_avg = (
      select avg(rating)::decimal(3,2)
      from marketplace_reviews
      where listing_id = new.listing_id
    ),
    rating_count = (
      select count(*)
      from marketplace_reviews
      where listing_id = new.listing_id
    )
  where id = new.listing_id;
  return new;
end;
$$ language plpgsql;

-- Trigger to automatically update ratings
drop trigger if exists trigger_update_listing_rating on marketplace_reviews;
create trigger trigger_update_listing_rating
  after insert or update or delete on marketplace_reviews
  for each row execute function update_listing_rating();

-- Function to update download counts
create or replace function increment_download_count()
returns trigger as $$
begin
  if new.event_type = 'download' then
    update marketplace_listings
    set download_count = download_count + 1
    where id = new.listing_id;
  end if;
  return new;
end;
$$ language plpgsql;

-- Trigger for download tracking
drop trigger if exists trigger_increment_download_count on marketplace_analytics;
create trigger trigger_increment_download_count
  after insert on marketplace_analytics
  for each row execute function increment_download_count();

-- Ensure UUID extension is available
create extension if not exists "uuid-ossp";

-- Sample data for testing
insert into publishers (id, user_id, name, contact_email, status)
select
  'b8d4e2a1-3c5f-4d7e-9b2a-1c3d5e7f9a0b'::uuid,
  u.id,
  'AutoFlow Solutions',
  'contact@autoflow.dev',
  'active'
from users u
where u.username = 'test'
on conflict (id) do nothing;

-- Sample marketplace listing
insert into marketplace_listings (
  id,
  publisher_id,
  key,
  title,
  summary,
  description,
  category,
  price_cents,
  latest_version,
  featured
) values (
  '550e8400-e29b-41d4-a716-446655440000'::uuid,
  'b8d4e2a1-3c5f-4d7e-9b2a-1c3d5e7f9a0b'::uuid,
  'xhs.content.scraper',
  'XHS Content Scraper Pro',
  'Professional tool for extracting content from XHS (Little Red Book)',
  'A comprehensive workflow for scraping posts, comments, and user data from XHS platform with built-in rate limiting and anti-detection measures.',
  'Web Scraping',
  2999,  -- $29.99
  '1.0.0',
  true
) on conflict (publisher_id, key) do nothing;

-- Sample version
insert into marketplace_versions (
  listing_id,
  version,
  engine_min,
  sha256,
  size_bytes,
  storage_url,
  manifest,
  signature,
  changelog
) values (
  '550e8400-e29b-41d4-a716-446655440000'::uuid,
  '1.0.0',
  '0.4.0',
  'a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456',
  1048576,  -- 1MB
  '/workflows/packages/xhs-content-scraper-1.0.0.zip',
  '{"name": "XHS Content Scraper", "entry": "main.json", "actions": ["scrape", "extract", "save"], "permissions": ["network", "filesystem"]}',
  'mock_ed25519_signature_base64_encoded_string_would_go_here',
  'Initial release with core scraping functionality'
) on conflict (listing_id, version) do nothing;