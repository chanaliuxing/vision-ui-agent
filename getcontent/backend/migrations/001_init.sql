-- Enable useful extensions (optional & safe if already exists)
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Migration bookkeeping
CREATE TABLE IF NOT EXISTS schema_migrations (
  id SERIAL PRIMARY KEY,
  filename TEXT UNIQUE NOT NULL,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Users
CREATE TABLE IF NOT EXISTS users (
  account_id TEXT PRIMARY KEY,
  username CITEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Sessions (DB-backed so it works across replicas)
CREATE TABLE IF NOT EXISTS sessions (
  sid TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES users(account_id) ON DELETE CASCADE,
  username TEXT NOT NULL,
  exp TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ip TEXT,
  ua TEXT
);
CREATE INDEX IF NOT EXISTS sessions_exp_idx ON sessions (exp);

-- Brute-force lock state (per username, shared across instances)
CREATE TABLE IF NOT EXISTS brute_force (
  username_lower TEXT PRIMARY KEY,
  streak INT NOT NULL DEFAULT 0,
  exponent INT NOT NULL DEFAULT 0,
  lock_until TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS brute_force_lock_idx ON brute_force (lock_until);

-- Minimal events audit
CREATE TABLE IF NOT EXISTS events (
  id BIGSERIAL PRIMARY KEY,
  account_id TEXT,
  type TEXT,
  host TEXT,
  payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS events_type_created_idx ON events (type, created_at DESC);