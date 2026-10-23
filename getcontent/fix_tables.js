// Fix database tables for testing
import pkg from 'pg';
const { Pool } = pkg;

const pool = new Pool({
  connectionString: 'postgresql://postgres:postgres@localhost:5432/postgres'
});

async function fixTables() {
  try {
    console.log('🔧 Fixing database table structure...');
    
    // Drop and recreate tables with correct structure
    await pool.query('DROP TABLE IF EXISTS artifacts CASCADE');
    await pool.query('DROP TABLE IF EXISTS run_steps CASCADE');
    await pool.query('DROP TABLE IF EXISTS workflow_runs CASCADE');
    
    console.log('🗑️ Dropped existing tables');
    
    // Recreate with correct structure
    await pool.query(`
      CREATE TABLE workflow_runs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        workflow_name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'running',
        created_at TIMESTAMPTZ DEFAULT NOW(),
        finished_at TIMESTAMPTZ
      )
    `);
    
    await pool.query(`
      CREATE TABLE run_steps (
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
      CREATE TABLE artifacts (
        id BIGSERIAL PRIMARY KEY,
        run_id UUID REFERENCES workflow_runs(id),
        kind TEXT,
        path TEXT,
        payload TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
      )
    `);
    
    console.log('✅ Tables recreated with correct structure');
    
    // Test insert to verify
    const testRunId = await pool.query(`
      INSERT INTO workflow_runs (workflow_name, status) 
      VALUES ('test', 'running') 
      RETURNING id
    `);
    
    await pool.query(`
      INSERT INTO run_steps (run_id, idx, action, status)
      VALUES ($1, 1, '{"do": "test"}', 'pending')
    `, [testRunId.rows[0].id]);
    
    console.log('✅ Test data inserted successfully');
    
    // Clean up test data
    await pool.query('DELETE FROM workflow_runs WHERE workflow_name = $1', ['test']);
    
    await pool.end();
    console.log('🎯 Database structure fixed and ready for testing!');
    
  } catch (error) {
    console.error('❌ Fix failed:', error.message);
    process.exit(1);
  }
}

fixTables();