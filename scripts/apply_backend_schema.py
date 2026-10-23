#!/usr/bin/env python
"""
Apply minimal backend schema (users/devices/commands/workflow tables) with safe IF NOT EXISTS guards.
Uses DATABASE/POSTGRES_DSN from environment, defaults to local postgres://postgres:postgres@localhost:5432/postgres.
"""

import os
import psycopg2

DSN = os.getenv("DATABASE") or os.getenv("POSTGRES_DSN") or "postgresql://postgres:postgres@localhost:5432/postgres"

stmts = [
    # Ensure cmd_status enum exists
    """
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cmd_status') THEN
        CREATE TYPE cmd_status AS ENUM ('pending','claimed','running','succeeded','failed');
      END IF;
    END$$;
    """,
    # Users / sessions / brute_force / events
    """
    CREATE TABLE IF NOT EXISTS users (
      account_id TEXT PRIMARY KEY,
      username CITEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      is_active BOOLEAN NOT NULL DEFAULT TRUE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
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
    """,
    "CREATE INDEX IF NOT EXISTS sessions_exp_idx ON sessions (exp);",
    """
    CREATE TABLE IF NOT EXISTS brute_force (
      username_lower TEXT PRIMARY KEY,
      streak INT NOT NULL DEFAULT 0,
      exponent INT NOT NULL DEFAULT 0,
      lock_until TIMESTAMPTZ
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
      id BIGSERIAL PRIMARY KEY,
      account_id TEXT,
      type TEXT,
      host TEXT,
      payload JSONB,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    "CREATE INDEX IF NOT EXISTS events_type_created_idx ON events (type, created_at DESC);",
    # Workflow tables
    """
    CREATE TABLE IF NOT EXISTS workflow_runs (
        id UUID PRIMARY KEY,
        workflow_name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'running',
        params JSONB DEFAULT '{}',
        created_at TIMESTAMPTZ DEFAULT NOW(),
        finished_at TIMESTAMPTZ
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status);",
    "CREATE INDEX IF NOT EXISTS idx_workflow_runs_created_at ON workflow_runs(created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_workflow_runs_name ON workflow_runs(workflow_name);",
    """
    CREATE TABLE IF NOT EXISTS run_steps (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        run_id UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
        idx INTEGER NOT NULL,
        action JSONB NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        input JSONB DEFAULT '{}',
        output JSONB,
        error TEXT,
        started_at TIMESTAMPTZ DEFAULT NOW(),
        finished_at TIMESTAMPTZ,
        UNIQUE(run_id, idx)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_run_steps_run_id ON run_steps(run_id);",
    "CREATE INDEX IF NOT EXISTS idx_run_steps_status ON run_steps(status);",
    "CREATE INDEX IF NOT EXISTS idx_run_steps_run_id_idx ON run_steps(run_id, idx);",
    """
    CREATE TABLE IF NOT EXISTS artifacts (
        id BIGSERIAL PRIMARY KEY,
        run_id UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
        kind TEXT NOT NULL DEFAULT 'text',
        path TEXT,
        payload TEXT,
        metadata JSONB DEFAULT '{}',
        size_bytes INTEGER,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_artifacts_run_id ON artifacts(run_id);",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_kind ON artifacts(kind);",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_path ON artifacts(path);",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_created_at ON artifacts(created_at DESC);",
    # Devices / commands
    """
    CREATE TABLE IF NOT EXISTS devices (
      device_id TEXT PRIMARY KEY,
      account_id TEXT NOT NULL,
      last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      ua TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS commands (
      id BIGSERIAL PRIMARY KEY,
      account_id TEXT NOT NULL,
      device_id TEXT NOT NULL,
      type TEXT NOT NULL,
      url TEXT,
      scope TEXT,
      vars JSONB,
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
    """,
    "CREATE INDEX IF NOT EXISTS commands_device_idx ON commands(device_id, status, created_at);",
    "CREATE INDEX IF NOT EXISTS commands_run_after_idx ON commands(run_after);",
    # Stats function (best-effort; requires plpgsql)
    """
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_language WHERE lanname='plpgsql') THEN
        CREATE LANGUAGE plpgsql;
      END IF;
    END$$;
    """,
    """
    CREATE OR REPLACE FUNCTION get_workflow_stats(run_id_param UUID)
    RETURNS TABLE(
        total_steps INTEGER,
        completed_steps INTEGER,
        failed_steps INTEGER,
        pending_steps INTEGER,
        total_artifacts INTEGER,
        run_duration_seconds INTEGER
    ) AS $$
    BEGIN
        RETURN QUERY
        SELECT 
            COUNT(rs.id)::INTEGER AS total_steps,
            COUNT(CASE WHEN rs.status IN ('success', 'skipped') THEN 1 END)::INTEGER AS completed_steps,
            COUNT(CASE WHEN rs.status = 'failed' THEN 1 END)::INTEGER AS failed_steps,
            COUNT(CASE WHEN rs.status IN ('pending', 'running') THEN 1 END)::INTEGER AS pending_steps,
            COUNT(a.id)::INTEGER AS total_artifacts,
            EXTRACT(EPOCH FROM (COALESCE(wr.finished_at, NOW()) - wr.created_at))::INTEGER AS run_duration_seconds
        FROM workflow_runs wr
        LEFT JOIN run_steps rs ON wr.id = rs.run_id
        LEFT JOIN artifacts a ON wr.id = a.run_id
        WHERE wr.id = run_id_param
        GROUP BY wr.id, wr.created_at, wr.finished_at;
    END;
    $$ LANGUAGE plpgsql;
    """,
]

def main():
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()
    for stmt in stmts:
        try:
            cur.execute(stmt)
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"⚠️  Failed statement: {e}")
    cur.close()
    conn.close()
    print("✅ Backend schema applied (best-effort)")

if __name__ == "__main__":
    main()
