-- Workflow execution tables for Orchestrator MVP
-- Migration 001: Core workflow execution schema

BEGIN;

-- Workflow runs table: tracks overall workflow execution
CREATE TABLE IF NOT EXISTS workflow_runs (
    id UUID PRIMARY KEY,
    workflow_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    params JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_created_at ON workflow_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_name ON workflow_runs(workflow_name);

-- Run steps table: tracks individual action execution within workflows
CREATE TABLE IF NOT EXISTS run_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    action JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'success', 'failed', 'skipped')),
    input JSONB DEFAULT '{}',
    output JSONB,
    error TEXT,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    
    -- Ensure unique step ordering within each run
    UNIQUE(run_id, idx)
);

CREATE INDEX IF NOT EXISTS idx_run_steps_run_id ON run_steps(run_id);
CREATE INDEX IF NOT EXISTS idx_run_steps_status ON run_steps(status);
CREATE INDEX IF NOT EXISTS idx_run_steps_run_id_idx ON run_steps(run_id, idx);

-- Artifacts table: stores workflow outputs and intermediate results  
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

CREATE INDEX IF NOT EXISTS idx_artifacts_run_id ON artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_kind ON artifacts(kind);
CREATE INDEX IF NOT EXISTS idx_artifacts_path ON artifacts(path);
CREATE INDEX IF NOT EXISTS idx_artifacts_created_at ON artifacts(created_at DESC);

-- Add missing columns to existing commands table if it exists
DO $$
BEGIN
    -- Check if commands table exists and add status column if missing
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'commands') THEN
        -- Add status column if it doesn't exist
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'commands' AND column_name = 'status') THEN
            ALTER TABLE commands ADD COLUMN status TEXT DEFAULT 'pending';
        END IF;
        
        -- Add index on status if not exists
        IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_commands_status') THEN
            CREATE INDEX idx_commands_status ON commands(status);
        END IF;
        
        -- Add index on queue if not exists  
        IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_commands_queue') THEN
            CREATE INDEX idx_commands_queue ON commands(queue);
        END IF;
    END IF;
END $$;

-- Create helper function to get workflow run statistics
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

COMMIT;

-- Grant permissions (adjust as needed for your setup)
-- GRANT ALL PRIVILEGES ON workflow_runs, run_steps, artifacts TO your_app_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO your_app_user;
