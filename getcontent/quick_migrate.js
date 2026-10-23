// Quick migration for testing
import pkg from 'pg';
const { Pool } = pkg;

const pool = new Pool({
  connectionString: 'postgresql://postgres:postgres@localhost:5432/postgres'
});

async function createTables() {
  try {
    console.log('🚀 Creating workflow tables...');
    
    await pool.query(`
      CREATE TABLE IF NOT EXISTS workflow_runs (
        id UUID PRIMARY KEY,
        workflow_name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'running',
        created_at TIMESTAMPTZ DEFAULT NOW(),
        finished_at TIMESTAMPTZ
      )
    `);
    
    await pool.query(`
      CREATE TABLE IF NOT EXISTS run_steps (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        run_id UUID REFERENCES workflow_runs(id),
        idx INTEGER NOT NULL,
        action JSONB NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        output JSONB,
        error TEXT,
        started_at TIMESTAMPTZ DEFAULT NOW(),
        finished_at TIMESTAMPTZ
      )
    `);
    
    await pool.query(`
      CREATE TABLE IF NOT EXISTS artifacts (
        id BIGSERIAL PRIMARY KEY,
        run_id UUID REFERENCES workflow_runs(id),
        kind TEXT,
        path TEXT,
        payload TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
      )
    `);
    
    console.log('✅ Tables created successfully!');
    await pool.end();
    
  } catch (error) {
    console.error('❌ Migration failed:', error.message);
    process.exit(1);
  }
}

createTables();