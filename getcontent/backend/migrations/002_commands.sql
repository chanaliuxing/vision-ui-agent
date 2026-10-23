DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cmd_status') THEN
    CREATE TYPE cmd_status AS ENUM ('pending','claimed','running','succeeded','failed');
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS devices (
  device_id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL,
  last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ua TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS commands (
  id BIGSERIAL PRIMARY KEY,
  account_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  type TEXT NOT NULL,             -- e.g. xhs_reply, indeed_apply
  url TEXT,                       -- destination page
  scope TEXT,                     -- e.g. task:xhs_auto_reply
  vars JSONB,                     -- variables (e.g., target_name, reply_text)
  status cmd_status NOT NULL DEFAULT 'pending',
  run_after TIMESTAMPTZ,
  claimed_at TIMESTAMPTZ,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  result JSONB,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS commands_device_idx ON commands(device_id, status, created_at);
CREATE INDEX IF NOT EXISTS commands_run_after_idx ON commands(run_after);
