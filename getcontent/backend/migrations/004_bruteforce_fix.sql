-- 004_bruteforce_fix.sql

-- Create table if not present
CREATE TABLE IF NOT EXISTS brute_force (
  username_lower TEXT PRIMARY KEY
);

-- Add missing columns safely
ALTER TABLE brute_force
  ADD COLUMN IF NOT EXISTS streak     INTEGER      NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS exponent   INTEGER      NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS lock_until TIMESTAMPTZ  NULL,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW();

-- Optional: make sure defaults are sane (in case of old rows)
UPDATE brute_force
   SET streak     = COALESCE(streak, 0),
       exponent   = COALESCE(exponent, 0),
       updated_at = COALESCE(updated_at, NOW());
