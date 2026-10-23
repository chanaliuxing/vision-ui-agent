-- 005_events_fix.sql
-- Fix missing columns in events table and ensure compatibility

-- Ensure events table exists with all required columns
CREATE TABLE IF NOT EXISTS events (
  id          BIGSERIAL PRIMARY KEY,
  account_id  TEXT,
  type        TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Add missing columns (idempotent)
ALTER TABLE events
  ADD COLUMN IF NOT EXISTS domain     TEXT,
  ADD COLUMN IF NOT EXISTS path       TEXT,
  ADD COLUMN IF NOT EXISTS ua         TEXT,
  ADD COLUMN IF NOT EXISTS host       TEXT,
  ADD COLUMN IF NOT EXISTS payload    JSONB;

-- Ensure brute_force table has updated_at column
ALTER TABLE brute_force
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- Add useful indexes
CREATE INDEX IF NOT EXISTS events_account_created_idx ON events (account_id, created_at DESC);
CREATE INDEX IF NOT EXISTS events_type_created_idx    ON events (type, created_at DESC);
CREATE INDEX IF NOT EXISTS events_host_created_idx    ON events (host, created_at DESC);